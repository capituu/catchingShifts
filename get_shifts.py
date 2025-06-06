import os
import json
import base64
import requests
from config import get_last_user_id, AUTH_DIR

# ——————————————————————————————————————————————————————
# 1) Obtém o último USER_ID salvo em last_user.txt
# ——————————————————————————————————————————————————————
USER_ID = get_last_user_id()
if not USER_ID:
    print("❌ Nenhum USER_ID encontrado. Execute auth_code_capture.py + token_exchange.py primeiro.")
    exit(1)

# Caminho completo para o arquivo de tokens desse usuário
TOKEN_FILE = os.path.join(AUTH_DIR, f"tokens_user_{USER_ID}.json")

# ——————————————————————————————————————————————————————
# 2) Lê o arquivo de tokens do usuário
# ——————————————————————————————————————————————————————
try:
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)
except FileNotFoundError:
    print(f"❌ Arquivo não encontrado: {TOKEN_FILE}")
    exit(1)
except json.JSONDecodeError:
    print(f"❌ Falha ao decodificar JSON em: {TOKEN_FILE}")
    exit(1)

access_token = token_data.get("access_token")
if not access_token:
    print("❌ access_token não encontrado em token_data.")
    exit(1)

# ——————————————————————————————————————————————————————
# 3) Decodifica o payload do access_token (JWT) para extrair claims
# ——————————————————————————————————————————————————————
def decode_jwt_payload(token: str) -> dict:
    """
    Recebe um JWT (x.y.z) e retorna o dicionário com as claims do payload.
    """
    try:
        # Pega a parte “y” (payload)
        payload_b64 = token.split(".")[1]
        # Ajusta o padding (múltiplo de 4) para Base64
        payload_b64 += "=" * (-len(payload_b64) % 4)
        # Decodifica
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload_json = payload_bytes.decode("utf-8")
        return json.loads(payload_json)
    except Exception as e:
        print(f"❌ Erro ao decodificar JWT: {e}")
        return {}

claims = decode_jwt_payload(access_token)

courier_id = claims.get("courier_id")
if not courier_id:
    print("❌ Não foi possível extrair courier_id do access_token.")
    exit(1)

print(f"🚚 Courier ID extraído: {courier_id}")

# Opcional: salvar courier_id de volta no arquivo, caso ainda não exista
if token_data.get("courier_id") != courier_id:
    token_data["courier_id"] = courier_id
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    print(f"ℹ️ courier_id salvo em {TOKEN_FILE}")

# ——————————————————————————————————————————————————————
# 4) Monta a URL e os parâmetros para “shifts scheduled”
# ——————————————————————————————————————————————————————
base_url = "https://api-courier-produk.skipthedishes.com/v2/couriers"
endpoint = f"{base_url}/{courier_id}/shifts/scheduled"

params = {
    "includeAvailable": "true",
    "timezone": "Europe/London",
    "hasCourierRefreshedOpenShifts": "true"
}

# ——————————————————————————————————————————————————————
# 5) Prepara os headers necessários (sem App-Token nem Tenant-Id)
# ——————————————————————————————————————————————————————
headers = {
    # Autenticação via Bearer token
    "Authorization": f"Bearer {access_token}",

    # Outros cabeçalhos observados no tráfego real
    "Accept-Encoding":   "gzip;q=1.0, compress;q=0.5",
    "Platform":          "iOS",
    "Accept-Language":   "en-GB;q=1.0, pt-GB;q=0.9",
    "User-Agent":        "SkipTheDishes-COURAPP-Just Eat / (iOS)",

    "Connection":        "keep-alive",
    "Content-Type":      "application/json",
    "Accept":            "application/json"
}

# ——————————————————————————————————————————————————————
# 6) Faz a requisição GET e trata a resposta
# ——————————————————————————————————————————————————————
print("🛰️  Enviando requisição para agendamento de shifts…")
resp = requests.get(endpoint, headers=headers, params=params)

if resp.status_code != 200:
    print(f"❌ Falha ao obter shifts: HTTP {resp.status_code}")
    try:
        print("→ Response JSON:", json.dumps(resp.json(), indent=2))
    except:
        print("→ Response Text:", resp.text)
    exit(1)

shifts = resp.json()
print("✅ Resposta de SHIFTS:\n")
print(json.dumps(shifts, indent=2))
