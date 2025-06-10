import sys
import os
import asyncio
import base64
import json
import requests
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from pyppeteer import launch, errors
from pyppeteer.launcher import Launcher

# ────────────────────────────────────────────────────────────────────────────────
# 1) Ajusta o PYTHONPATH para importar config da pasta pai
# ────────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from config import get_last_user_id, AUTH_DIR

# ────────────────────────────────────────────────────────────────────────────────
# 2) Configuração de logs
# ────────────────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(AUTH_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "get_shifts.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# ────────────────────────────────────────────────────────────────────────────────
# 3) Constants e URLs de token
# ────────────────────────────────────────────────────────────────────────────────
TOKEN_URL    = "https://api-produk.skipthedishes.com/auth/realms/Courier/protocol/openid-connect/token"
CLIENT_ID    = "courier_mobile_jet_uk"
REDIRECT_URI = "courierapp://homepage"
HEADERS      = {"Content-Type": "application/x-www-form-urlencoded"}

USER_ID = get_last_user_id()
if not USER_ID:
    logging.error("Nenhum USER_ID encontrado. Execute auth_code_capture.py + token_exchange.py primeiro.")
    sys.exit(1)

TOKEN_FILE = os.path.join(AUTH_DIR, f"tokens_user_{USER_ID}.json")
AUTH_FILE  = os.path.join(AUTH_DIR, f"user_{USER_ID}.json")

# Carrega token_data (se existir)
try:
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        token_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    token_data = {}

def decode_jwt_payload(token: str) -> dict:
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return {}

access_token = token_data.get("access_token", "")
claims = decode_jwt_payload(access_token)
courier_id = claims.get("courier_id")
if not courier_id:
    logging.error("courier_id não encontrado no payload do access_token.")
    sys.exit(1)

# Se necessário, salva courier_id no JSON
if token_data.get("courier_id") != courier_id:
    token_data["courier_id"] = courier_id
    os.makedirs(AUTH_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

logging.info(f"🚚 Courier ID extraído: {courier_id}")

# ────────────────────────────────────────────────────────────────────────────────
# 4) Funções de validação e refresh de token
# ────────────────────────────────────────────────────────────────────────────────
def access_token_valido(data: dict, margin: int = 60) -> bool:
    if not data.get("access_token") or not data.get("expires_in") or not data.get("obtained_at"):
        return False
    try:
        obtido = datetime.fromisoformat(data["obtained_at"])
    except Exception:
        return False

    expira_em = obtido + timedelta(seconds=int(data["expires_in"]))
    agora = datetime.now(timezone.utc)
    return (expira_em - agora).total_seconds() > margin

def post_to_token_url(payload: dict) -> dict | None:
    resp = requests.post(TOKEN_URL, data=payload, headers=HEADERS)
    try:
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as err:
        logging.error(f"Erro ao chamar token endpoint: {err}")
        try:
            logging.error(f"→ Response JSON: {resp.json()}")
        except:
            logging.error(f"→ Response Text: {resp.text}")
        return None

def refresh_access_token(refresh_token: str) -> dict | None:
    payload = {
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     CLIENT_ID
    }
    logging.info("🔄 Tentando refresh do access_token com refresh_token existente…")
    data = post_to_token_url(payload)
    if not data:
        return None
    logging.info("✅ Refresh bem-sucedido, novos tokens recebidos.")
    return data

def exchange_code_for_tokens(code: str) -> dict | None:
    payload = {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID
    }
    logging.info("🔄 Exchanging auth code for tokens…")
    data = post_to_token_url(payload)
    if not data:
        return None
    logging.info("✅ Tokens recebidos pela troca de código.")
    return data

def garantir_token_atualizado():
    global token_data, access_token

    if access_token_valido(token_data):
        access_token = token_data["access_token"]
        logging.info("✅ Access token ainda válido, sem necessidade de refresh.")
        return

    if token_data.get("refresh_token"):
        atualizado = refresh_access_token(token_data["refresh_token"])
        if atualizado:
            atualizado["obtained_at"] = datetime.now(timezone.utc).isoformat()
            token_data.update(atualizado)
            access_token = token_data["access_token"]
            os.makedirs(AUTH_DIR, exist_ok=True)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            logging.info(f"📂 Tokens atualizados em: {TOKEN_FILE}")
            return
        else:
            logging.warning("⚠️ Refresh token falhou ou expirou. Tentando troca via authorization_code…")

    # Se chegou aqui, precisa usar authorization_code
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.error(f"❌ Falha ao ler auth file: {AUTH_FILE}")
        sys.exit(1)

    code = auth_data.get("code")
    if not code:
        logging.error("❌ ‘code’ não encontrado em auth_data. Execute auth_code_capture.py antes.")
        sys.exit(1)

    novo = exchange_code_for_tokens(code)
    if not novo:
        logging.error("❌ Não foi possível obter tokens via authorization_code. Abortando.")
        sys.exit(1)

    novo["obtained_at"] = datetime.now(timezone.utc).isoformat()
    token_data = novo
    access_token = token_data["access_token"]
    os.makedirs(AUTH_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)
    logging.info(f"📂 Tokens salvos em: {TOKEN_FILE}")

# ────────────────────────────────────────────────────────────────────────────────
# 5) Constantes para requisição de “shifts scheduled”
# ────────────────────────────────────────────────────────────────────────────────
base_url = "https://api-courier-produk.skipthedishes.com/v2/couriers"
query_params = {
    "includeAvailable": "true",
    "timezone":          "Europe/London",
    "hasCourierRefreshedOpenShifts": "true"
}

# ────────────────────────────────────────────────────────────────────────────────
# 6) Carrega filtros
# ────────────────────────────────────────────────────────────────────────────────
def load_filters(user_id: str) -> dict:
    path = os.path.join(AUTH_DIR, f"filters_{user_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.error(f"❌ Arquivo de filtros não encontrado ou inválido: {path}")
        return {}

filters = load_filters(USER_ID)

def shift_matches_filter(shift: dict) -> bool:
    ts_start_ms = shift["shiftTime"]["start"]
    dt_start = datetime.fromtimestamp(ts_start_ms / 1000, tz=ZoneInfo("Europe/London"))
    day_name = dt_start.strftime("%A")
    hour = dt_start.hour

    day_filter = filters.get(day_name)
    if not day_filter or not day_filter.get("enabled"):
        return False

    start_hour = int(day_filter.get("start", 0))
    end_hour   = int(day_filter.get("end", 24))
    return (hour >= start_hour) and (hour < end_hour)

# ────────────────────────────────────────────────────────────────────────────────
# 7) Função de confirmação de shift
# ────────────────────────────────────────────────────────────────────────────────
IPHONE_UA = "SkipTheDishes-COURAPP-Just Eat / (iOS - 6.0.3)"

def confirm_shift(shift_id: str):
    endpoint = f"{base_url}/{courier_id}/shifts/{shift_id}/confirm"
    headers = {
        "app-token":       "31983a5d-37b1-4390-bd1c-8184e855e5da",
        "tenant-id":       "uk",
        "cache-control":   "no-cache",
        "User-Agent":      IPHONE_UA,
        "content-length":  "0",
        "platform":        "iOS",
        "Authorization":   f"Bearer {access_token}",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept":          "application/json",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type":    "application/json",
        "app-version":     "6.0.3.6.0.5",
        "app-build":       "377"
    }
    try:
        resp = requests.post(endpoint, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Shift {shift_id} confirmado com sucesso.")
    except requests.exceptions.HTTPError as err:
        logging.error(f"❌ Falha ao confirmar shift {shift_id}: HTTP {resp.status_code} | {err}")
        try:
            logging.error(f"→ Response JSON: {resp.json()}")
        except:
            logging.error(f"→ Response Text: {resp.text}")

# ────────────────────────────────────────────────────────────────────────────────
# 8) Função assíncrona que busca shifts, filtra e confirma
# ────────────────────────────────────────────────────────────────────────────────
# Determine Chrome/Chromium path from environment or use a common default
CHROME_PATH = os.environ.get(
    "PUPPETEER_EXECUTABLE_PATH",
    r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
)
# Propagate path so pyppeteer picks it up
os.environ["PUPPETEER_EXECUTABLE_PATH"] = CHROME_PATH

IPHONE_VIEWPORT = {
    "width": 375,
    "height": 812,
    "deviceScaleFactor": 3,
    "isMobile": True,
    "hasTouch": True,
    "isLandscape": False
}

async def fetch_shifts_with_puppeteer():
    # 1) Garante token antes de abrir o navegador
    garantir_token_atualizado()

    # 2) Inicia o navegador
    browser = await launch(
        executablePath=CHROME_PATH,
        headless=True,
        ignoreDefaultArgs=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--browser-path=" + CHROME_PATH,
            "--no-default-browser-check",
            "--no-first-run"
        ],
        ignoreHTTPSErrors=True,
        product="chrome"
    )
    page = await browser.newPage()
    page.on("response", lambda response: logging.info(f"[Response] {response.url} – {response.status}"))

    # 3) Emula iPhone e configura cabeçalhos fixos
    await page.setUserAgent(IPHONE_UA)
    await page.setViewport(IPHONE_VIEWPORT)

    # 4) Antes de montar URL e enviar requisição, garante token atualizado
    garantir_token_atualizado()

    encoded = urlencode(query_params)
    shifts_url = f"{base_url}/{courier_id}/shifts/scheduled?{encoded}"
    logging.info(f"🔗 URL final de SHIFTS: {shifts_url}")

    await page.setExtraHTTPHeaders({
        "Authorization":   f"Bearer {access_token}",
        "Accept":          "application/json",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br"
    })

    # 5) Navega para a URL de SHIFTS
    logging.info("🌐 Navegando para a URL de SHIFTS (aguardando Cloudflare Turnstile)…")
    try:
        response = await page.goto(
            shifts_url,
            {"waitUntil": "networkidle2", "timeout": 45000}
        )
        status = response.status
        ctype  = response.headers.get("content-type", "")
        logging.info(f"→ HTTP status: {status} | content-type: {ctype}")
    except (errors.TimeoutError, errors.PageError) as e:
        logging.error(f"❌ Erro/timeout ao carregar a URL de SHIFTS: {e}")
        await page.screenshot({"path": "erro_shifts.png", "fullPage": True})
        await browser.close()
        return

    # 6) Detecta bloqueio Cloudflare (não JSON)
    if "application/json" not in ctype:
        logging.error("❌ Sem JSON (provável bloqueio Cloudflare). Salvando screenshot e abortando.")
        await page.screenshot({"path": "cf_blocked.png", "fullPage": True})
        html = await page.content()
        with open("cf_blocked.html", "w", encoding="utf-8") as f:
            f.write(html)
        await browser.close()
        return

    # 7) Parse do JSON
    body = await response.text()
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        logging.error(f"❌ JSON malformado: {e}")
        logging.error(f"Corpo bruto: {body[:200]}…")
        await browser.close()
        return

    if data.get("error"):
        logging.error(f"❌ Erro da API de SHIFTS: {data['error']}")
        await browser.close()
        return

    # 8) Filtra e confirma cada shift compatível
    available = data.get("availableShifts", [])
    if not available:
        logging.info("— Nenhum shift disponível no momento.")
    else:
        logging.info(f"🔍 {len(available)} shift(s) disponíveis. Aplicando filtros…")
        for shift in available:
            sid = shift.get("id")
            if not sid:
                logging.warning("⚠️ Shift sem ID detectado: %s", shift)
                continue

            if shift_matches_filter(shift):
                logging.info(f"✔️ Shift {sid} corresponde ao filtro. Confirmando…")
                confirm_shift(sid)
            else:
                ts = shift["shiftTime"]["start"]
                dt = datetime.fromtimestamp(ts / 1000, tz=ZoneInfo("Europe/London"))
                logging.info(f"⏭ Shift {sid} em {dt.strftime('%A %Y-%m-%d %H:%M')} fora do filtro.")

    await browser.close()

# ────────────────────────────────────────────────────────────────────────────────
# 9) Execução única (chamada pelo bot_manager)
# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    default_path = Launcher().executablePath
    logging.info(f"Default browser path (Pyppeteer): {default_path}")
    asyncio.run(fetch_shifts_with_puppeteer())
