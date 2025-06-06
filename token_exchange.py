import requests
import json
import os
from datetime import datetime, timedelta, timezone
from config import get_last_user_id, AUTH_DIR

# ==============================================================================
# 1) Identifica o USER_ID e define caminhos
# ==============================================================================
USER_ID = get_last_user_id()
if not USER_ID:
    print("❌ No recent user ID found. Please run auth_code_capture.py first.")
    exit(1)

print(f"🔑 Using User ID: {USER_ID}")

AUTH_FILE  = os.path.join(AUTH_DIR, f"user_{USER_ID}.json")
TOKEN_FILE = os.path.join(AUTH_DIR, f"tokens_user_{USER_ID}.json")

# ==============================================================================
# 2) Endpoint e parâmetros comuns
# ==============================================================================
TOKEN_URL    = "https://api-produk.skipthedishes.com/auth/realms/Courier/protocol/openid-connect/token"
CLIENT_ID    = "courier_mobile_jet_uk"
REDIRECT_URI = "courierapp://homepage"  # deve bater exatamente com auth_code_capture.py

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded"
}

# ==============================================================================
# 3) Carrega o JSON de tokens existente (se houver)
# ==============================================================================
token_data = {}
if os.path.exists(TOKEN_FILE):
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token_data = json.load(f)
    except Exception as e:
        print(f"⚠️ Falha ao ler {TOKEN_FILE}: {e}")
        token_data = {}

# ==============================================================================
# 4) Função de utilitário: verifica se o access_token está prestes a expirar
# ==============================================================================
def access_token_valido(data: dict, margin: int = 60) -> bool:
    """
    data deve conter:
      - "access_token", "expires_in" e "obtained_at".
    Se faltar algum ou já estiver dentro de margin segundos de expirar, retorna False.
    """
    if not data.get("access_token") or not data.get("expires_in") or not data.get("obtained_at"):
        return False
    try:
        obtido = datetime.fromisoformat(data["obtained_at"])
    except Exception:
        return False

    expira_em = obtido + timedelta(seconds=int(data["expires_in"]))
    agora = datetime.now(timezone.utc)
    return (expira_em - agora).total_seconds() > margin

# ==============================================================================
# 5) Função: refresh token
# ==============================================================================
def refresh_access_token(refresh_token: str) -> dict | None:
    """
    Faz POST grant_type=refresh_token. Se der certo, retorna o JSON com novos tokens.
    Caso contrário, retorna None.
    """
    payload = {
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     CLIENT_ID
    }
    print("🔄 Tentando refresh do access_token com refresh_token existente...")
    resp = requests.post(TOKEN_URL, data=payload, headers=HEADERS)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"❌ Refresh token falhou: {err}")
        try:
            print("→ Response JSON:", resp.json())
        except:
            print("→ Response Text:", resp.text)
        return None

    novo = resp.json()
    print("✅ Refresh bem-sucedido, novos tokens recebidos:")
    print(json.dumps(novo, indent=2))
    return novo

# ==============================================================================
# 6) Função: exchange authorization_code → tokens
# ==============================================================================
def exchange_code_for_tokens(code: str) -> dict | None:
    """
    Faz POST grant_type=authorization_code para trocar code por tokens iniciais.
    Se bem-sucedido, retorna o JSON completo; senão, retorna None.
    """
    payload = {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID
    }
    print("🔄 Exchanging auth code for tokens...")
    resp = requests.post(TOKEN_URL, data=payload, headers=HEADERS)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"❌ Token exchange falhou: {err}")
        try:
            print("→ Response JSON:", resp.json())
        except:
            print("→ Response Text:", resp.text)
        return None

    data = resp.json()
    print("✅ Tokens recebidos pela troca de código:")
    print(json.dumps(data, indent=2))
    return data

# ==============================================================================
# 7) Fluxo principal:
#    a) Se o access_token ainda é válido, mantém tudo.
#    b) Se expirou ou perto de expirar:
#       b1) tenta refresh_token (se existir);
#       b2) se refresh falhar (ou não houver), usa authorization_code.
# ==============================================================================
def main():
    global token_data

    # Caso A: já existe token_data e access_token ainda válido → nada a fazer
    if access_token_valido(token_data):
        print("✅ Access token ainda válido. Nenhuma troca necessária.")
        return

    # Caso B: token_data existe mas expirou ou perto de expirar
    if token_data.get("refresh_token"):
        atualizado = refresh_access_token(token_data["refresh_token"])
        if atualizado:
            # marca timestamp de quando obtivemos esses tokens
            atualizado["obtained_at"] = datetime.now(timezone.utc).isoformat()
            token_data.update(atualizado)
            access_token = token_data["access_token"]
            os.makedirs(AUTH_DIR, exist_ok=True)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            print(f"📂 Tokens atualizados em: {TOKEN_FILE}")
            return
        else:
            print("⚠️ Refresh token falhou ou expirou. Tentando troca via authorization_code…")

    # Caso C: não há refresh_token ou ele falhou → usa authorization_code
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Auth file not found: {AUTH_FILE}")
        exit(1)
    except json.JSONDecodeError:
        print(f"❌ Failed to parse JSON in: {AUTH_FILE}")
        exit(1)

    if "code" not in auth_data:
        print("❌ ‘code’ não encontrado em auth_data. Execute auth_code_capture.py antes.")
        exit(1)

    code = auth_data["code"]
    novo = exchange_code_for_tokens(code)
    if not novo:
        print("❌ Não foi possível obter tokens via authorization_code. Abortando.")
        exit(1)

    novo["obtained_at"] = datetime.now(timezone.utc).isoformat()
    token_data = novo
    os.makedirs(AUTH_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)
    print(f"📂 Tokens salvos em: {TOKEN_FILE}")

if __name__ == "__main__":
    main()
