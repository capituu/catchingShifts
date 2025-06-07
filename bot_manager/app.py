
import sys
import uuid
import json
import threading
import subprocess
import logging
import time
import random
import requests
import os
from flask import Flask, render_template, jsonify, request, redirect
from urllib.parse import urlencode
from datetime import datetime, timezone
from threading import Lock

# ────────────────────────────────────────────────────────────────────────────────
# 1) Ajuste de PYTHONPATH para importar config da pasta pai (catchingShifts)
# ────────────────────────────────────────────────────────────────────────────────
def add_parent_to_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, os.pardir))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

add_parent_to_path()
from config import get_last_user_id, save_last_user_id, AUTH_DIR

# ────────────────────────────────────────────────────────────────────────────────
# 2) Configuração de logging (arquivo em catchingShifts/userauth/logs/app.log)
# ────────────────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(AUTH_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "app.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# ────────────────────────────────────────────────────────────────────────────────
# 3) OpenID / Keycloak (use variáveis de ambiente ou valores padrão)
# ────────────────────────────────────────────────────────────────────────────────
KEYCLOAK_AUTH_URL  = os.getenv(
    "KEYCLOAK_AUTH_URL",
    "https://api-produk.skipthedishes.com/auth/realms/Courier/protocol/openid-connect/auth"
)
KEYCLOAK_TOKEN_URL = os.getenv(
    "KEYCLOAK_TOKEN_URL",
    "https://api-produk.skipthedishes.com/auth/realms/Courier/protocol/openid-connect/token"
)
CLIENT_ID          = os.getenv("CLIENT_ID", "courier_mobile_jet_uk")
REDIRECT_URI       = os.getenv("REDIRECT_URI", "http://localhost:5000/callback")

# ────────────────────────────────────────────────────────────────────────────────
# 4) Configuração do Flask, definindo onde estão templates e estáticos
# ────────────────────────────────────────────────────────────────────────────────
# As pastas `templates/` e `static/` ficam dentro do próprio `bot_manager`.
base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(base_dir, "templates"),
    static_folder=os.path.join(base_dir, "static")
)

bot_running = False
bot_thread = None
bot_lock = Lock()
INTERVAL_SECONDS_MIN = 30
INTERVAL_SECONDS_MAX = 60

# Conjunto em memória para validar 'state' no OAuth
OAUTH_STATES = set()

# ────────────────────────────────────────────────────────────────────────────────
# 5) Função para verificar se o executável do Chromium existe e responde
# ────────────────────────────────────────────────────────────────────────────────
def launch_chromium_process():
    chrome_path = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if not chrome_path or not os.path.exists(chrome_path):
        logging.error(f"Chromium não encontrado em: {chrome_path}")
        return False
    try:
        proc = subprocess.run(
            [chrome_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            logging.info(f"Chromium version: {proc.stdout.strip()}")
            return True
        else:
            logging.error(f"Falha ao lançar Chromium: {proc.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logging.error("Chromium não respondeu em 5 segundos.")
        return False
    except Exception as e:
        logging.error(f"Erro na verificação do Chromium: {e}")
        return False

# ────────────────────────────────────────────────────────────────────────────────
# 6) Loop em background que chama get_shifts_puppeteer.py periodicamente
# ────────────────────────────────────────────────────────────────────────────────
def run_shifts_loop():
    global bot_running

    if not launch_chromium_process():
        logging.error("Não foi possível iniciar o bot: falha na verificação do Chromium")
        with bot_lock:
            bot_running = False
        return

    logging.info("🔄 Bot de Shifts iniciado (intervalo aleatório de 30 a 60 segundos)")
    while True:
        with bot_lock:
            if not bot_running:
                logging.info("🛑 Bot de Shifts parado.")
                return

        try:
            env = os.environ.copy()
            # Garante que PUPPETEER_EXECUTABLE_PATH esteja em env
            chrome_env = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
            if chrome_env:
                env["PUPPETEER_EXECUTABLE_PATH"] = chrome_env

            # Executa get_shifts_puppeteer.py dentro de catchingShifts/bot_manager
            script_dir = os.path.dirname(os.path.abspath(__file__))
            result = subprocess.run(
                [sys.executable, "get_shifts_puppeteer.py"],
                cwd=script_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            if result.returncode != 0:
                logging.error(
                    f"get_shifts_puppeteer retornou código {result.returncode}. "
                    f"STDERR: {result.stderr.decode(errors='ignore')}"
                )
        except Exception as e:
            logging.error(f"Erro ao executar get_shifts_puppeteer: {e}")
            with bot_lock:
                bot_running = False
            return

        sleep_seconds = random.randint(INTERVAL_SECONDS_MIN, INTERVAL_SECONDS_MAX)
        logging.info(f"⏱️ Aguardando {sleep_seconds}s até a próxima checagem…")
        for _ in range(sleep_seconds):
            with bot_lock:
                if not bot_running:
                    logging.info("🛑 Bot de Shifts parado.")
                    return
            time.sleep(1)

# ────────────────────────────────────────────────────────────────────────────────
# 7) Rotas do Flask: página principal, estado e toggle do bot
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/state")
def state():
    return jsonify({"running": bot_running}), 200

# Rota simples para verificar se existe algum usuário autenticado
@app.route("/auth_status")
def auth_status():
    user_id = get_last_user_id()
    if not user_id:
        return jsonify({"authenticated": False}), 200
    token_file = os.path.join(AUTH_DIR, f"tokens_user_{user_id}.json")
    return jsonify({"authenticated": os.path.exists(token_file)}), 200

@app.route("/toggle", methods=["POST"])
def toggle():
    global bot_running, bot_thread
    with bot_lock:
        if not bot_running:
            # Valida Chromium apenas ao ligar
            if not launch_chromium_process():
                return jsonify({"running": False, "error": "Falha na verificação do Chromium"}), 400
            bot_running = True
            bot_thread = threading.Thread(target=run_shifts_loop)
            bot_thread.start()
            logging.info("Bot ligado via /toggle")
        else:
            bot_running = False
            logging.info("Bot desligado via /toggle")
    return jsonify({"running": bot_running}), 200

# ────────────────────────────────────────────────────────────────────────────────
# 8) Rota de login: inicia fluxo OIDC no Keycloak/Just Eat
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/connect")
def connect():
    state = uuid.uuid4().hex
    OAUTH_STATES.add(state)
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid profile email offline_access",
        "response_mode": "query",
        "state":         state,
        "prompt":        "login"
    }
    url = KEYCLOAK_AUTH_URL + "?" + urlencode(params)
    logging.info(f"Redirecionando para Keycloak: state={state}")
    return redirect(url)

# ────────────────────────────────────────────────────────────────────────────────
# 9) Callback: recebe 'code' do Keycloak e troca por tokens
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/callback")
def callback():
    code  = request.args.get("code")
    state = request.args.get("state")
    session_state = request.args.get("session_state", "")

    if not code:
        return "❌ Parâmetro 'code' não retornado pelo Keycloak.", 400

    # Validação de state para prevenir CSRF
    if state not in OAUTH_STATES:
        logging.warning(f"State inválido recebido: {state}")
        return "❌ Estado inválido.", 400
    OAUTH_STATES.remove(state)

    existing_id = get_last_user_id()
    user_id = existing_id if existing_id else uuid.uuid4().hex[:8]

    auth_record = {
        "code":          code,
        "state":         state,
        "session_state": session_state,
        "timestamp":     datetime.now(timezone.utc).isoformat()
    }
    auth_file_path = os.path.join(AUTH_DIR, f"user_{user_id}.json")
    try:
        os.makedirs(AUTH_DIR, exist_ok=True)
        with open(auth_file_path, "w", encoding="utf-8") as f:
            json.dump(auth_record, f, indent=2)
        logging.info(f"Auth record salvo em: {auth_file_path}")
    except OSError as e:
        logging.error(f"Erro ao salvar auth_file: {e}")
        return "❌ Erro ao salvar dados de autenticação.", 500

    payload = {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(KEYCLOAK_TOKEN_URL, data=payload, headers=headers)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logging.error(f"Falha ao trocar code por tokens: {err} | {resp.text}")
        return f"❌ Falha ao trocar code por tokens: {err}", 500

    token_data = resp.json()
    token_data["obtained_at"] = datetime.now(timezone.utc).isoformat()

    token_file_path = os.path.join(AUTH_DIR, f"tokens_user_{user_id}.json")
    try:
        with open(token_file_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        logging.info(f"Tokens salvos em: {token_file_path}")
    except OSError as e:
        logging.error(f"Erro ao salvar token_file: {e}")
        return "❌ Erro ao salvar tokens.", 500

    save_last_user_id(user_id)
    return redirect("/")

# ────────────────────────────────────────────────────────────────────────────────
# 10) Rota de Filters (GET = exibe formulário, POST = salva JSON validado)
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/filters", methods=["GET", "POST"])
def filters():
    user_id = get_last_user_id()
    if not user_id:
        return "Nenhum usuário autenticado. Execute a autenticação antes.", 400

    filters_file = os.path.join(AUTH_DIR, f"filters_{user_id}.json")

    if request.method == "POST":
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "JSON inválido"}), 400

        required_days = [
            "Monday","Tuesday","Wednesday",
            "Thursday","Friday","Saturday","Sunday"
        ]
        try:
            for day in required_days:
                day_obj = data.get(day)
                if not isinstance(day_obj, dict):
                    raise ValueError(f"{day} deve ser um objeto")
                enabled = day_obj.get("enabled")
                start = day_obj.get("start")
                end = day_obj.get("end")
                if not isinstance(enabled, bool):
                    raise ValueError(f"{day}.enabled deve ser True/False")
                if not (isinstance(start, int) and 0 <= start < 24):
                    raise ValueError(f"{day}.start deve ser inteiro entre 0 e 23")
                if not (isinstance(end, int) and 1 <= end <= 24):
                    raise ValueError(f"{day}.end deve ser inteiro entre 1 e 24")
                if start >= end:
                    raise ValueError(f"{day}: start ({start}) deve ser menor que end ({end})")

            os.makedirs(AUTH_DIR, exist_ok=True)
            with open(filters_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logging.info(f"Filters salvos em: {filters_file}")
            return jsonify({"success": True}), 200
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except OSError as e:
            logging.error(f"Erro ao salvar filters_file: {e}")
            return jsonify({"success": False, "error": "Falha ao salvar filtros"}), 500

    else:
        existing = {}
        if os.path.exists(filters_file):
            try:
                with open(filters_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}
        if not existing:
            existing = {
                "Monday":    {"enabled": False, "start": 0, "end": 24},
                "Tuesday":   {"enabled": False, "start": 0, "end": 24},
                "Wednesday": {"enabled": False, "start": 0, "end": 24},
                "Thursday":  {"enabled": False, "start": 0, "end": 24},
                "Friday":    {"enabled": False, "start": 0, "end": 24},
                "Saturday":  {"enabled": False, "start": 0, "end": 24},
                "Sunday":    {"enabled": False, "start": 0, "end": 24}
            }
        return render_template("filters.html", filters=existing)

# ────────────────────────────────────────────────────────────────────────────────
# 11) Rota de Collected Shifts (agrupa por data e ordena cronologicamente)
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/collected", methods=["GET"])
def collected_shifts():
    user_id = get_last_user_id()
    if not user_id:
        return "Nenhum usuário autenticado. Execute a autenticação antes.", 400

    collected_file = os.path.join(AUTH_DIR, f"collected_{user_id}.json")
    all_collected = {}

    if os.path.exists(collected_file):
        try:
            with open(collected_file, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
        except (json.JSONDecodeError, OSError):
            raw_list = []

        def parse_date_key(date_str):
            try:
                return datetime.fromisoformat(date_str)
            except ValueError:
                try:
                    return datetime.strptime(date_str, "%d/%m/%Y")
                except:
                    return datetime.min

        for entry in raw_list:
            date_key = entry.get("shift_date", "unknown")
            all_collected.setdefault(date_key, []).append(entry)

        all_collected = dict(
            sorted(all_collected.items(), key=lambda kv: parse_date_key(kv[0]))
        )

    return render_template("collected.html", collected=all_collected)

# ────────────────────────────────────────────────────────────────────────────────
# 12) Execução do Flask
# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Força o Flask a rodar em modo DEBUG
    print("▶ Iniciando Flask em http://127.0.0.1:5000/  (modo debug=on)")
    app.run(host="0.0.0.0", port=5000, debug=True)

