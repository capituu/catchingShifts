import os
import sys
import asyncio
import uuid
import json
import datetime
import subprocess
from urllib.parse import urlparse, parse_qs

from pyppeteer import launch, errors
from pyppeteer_stealth import stealth

# ────────────────────────────────────────────────────────────────────────────────
# 1) Ajuste de PYTHONPATH para importar config da pasta pai
# ────────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from config import save_last_user_id, AUTH_DIR

# ────────────────────────────────────────────────────────────────────────────────
# 2) Configurações do Chrome e OIDC
# ────────────────────────────────────────────────────────────────────────────────
CHROME_PATH = os.getenv(
    'PUPPETEER_EXECUTABLE_PATH',
    r"C:\Users\gusta\OneDrive\Desktop\chrome-win\chrome.exe"
)

OIDC_CLIENT_ID = "courier_mobile_jet_uk"
REDIRECT_URI = "courierapp://homepage"
OIDC_STATE = str(uuid.uuid4())
LOGIN_URL = (
    "https://api-produk.skipthedishes.com/auth/realms/Courier/"
    "protocol/openid-connect/auth?" +
    f"client_id={OIDC_CLIENT_ID}&redirect_uri={urlparse.quote(REDIRECT_URI, safe='')}" +
    f"&state={OIDC_STATE}&response_type=code&scope=openid%20profile%20email%20offline_access&prompt=login"
)

IPHONE_DEVICE = {
    'userAgent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
    ),
    'viewport': {
        'width': 375,
        'height': 812,
        'deviceScaleFactor': 3,
        'isMobile': True,
        'hasTouch': True,
        'isLandscape': False
    }
}

# ────────────────────────────────────────────────────────────────────────────────
# 3) Verificação do executável do Chrome
# ────────────────────────────────────────────────────────────────────────────────
def verify_chrome_path() -> bool:
    if not os.path.isfile(CHROME_PATH):
        print(f"❌ Chrome not found or not a file at: {CHROME_PATH}")
        return False
    try:
        result = subprocess.run(
            [CHROME_PATH, '--version'],
            capture_output=True, text=True, timeout=5
        )
        print(f"✅ Chrome version: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"❌ Chrome execution failed: {e}")
        return False

async def verify_browser_launch() -> bool:
    try:
        print("🔍 Testing Chrome launch...")
        browser = await launch(
            executablePath=CHROME_PATH,
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ],
            ignoreHTTPSErrors=True,
            product='chrome'
        )
        await browser.close()
        print("✅ Browser launch test successful")
        return True
    except Exception as e:
        print(f"❌ Browser launch failed: {e}")
        return False

# ────────────────────────────────────────────────────────────────────────────────
# 4) Fluxo principal de captura de código de autorização
# ────────────────────────────────────────────────────────────────────────────────
async def run_oidc_flow():
    # 1) Verificações iniciais
    print("\n=== Chrome Verification ===")
    if not verify_chrome_path():
        print("❌ Aborting: Chrome verification failed")
        return
    if not await verify_browser_launch():
        print("❌ Aborting: Browser launch test failed")
        return

    # 2) Depuração de ambiente
    print("\n=== Debug Info ===")
    print(f"Working dir: {os.getcwd()}")
    print(f"PUPPETEER_EXECUTABLE_PATH: {os.environ.get('PUPPETEER_EXECUTABLE_PATH')}")

    # 3) Inicia o browser real para fluxo OIDC
    try:
        browser = await launch(
            executablePath=CHROME_PATH,
            headless=False,
            ignoreDefaultArgs=['--enable-automation'],
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--no-default-browser-check',
                '--no-first-run',
                f"--user-data-dir={os.path.join(os.getcwd(), 'chrome-profile')}"
            ],
            ignoreHTTPSErrors=True,
            product='chrome'
        )
    except Exception as e:
        print(f"❌ Failed to launch Chrome: {e}")
        return

    # 4) Abre nova página e configurações
    page = await browser.newPage()
    await page.setUserAgent(IPHONE_DEVICE['userAgent'])
    await page.setViewport(IPHONE_DEVICE['viewport'])
    await stealth(page)

    # 5) Função para capturar redirect
    async def on_response(resp):
        if resp.status == 302:
            loc = resp.headers.get('location', '')
            if loc.startswith(REDIRECT_URI):
                print("📨 Detected redirect to app URI")
                parsed = urlparse(loc)
                frag = parse_qs(parsed.fragment)
                code = frag.get('code', [''])[0]
                state = frag.get('state', [''])[0]
                sess = frag.get('session_state', [''])[0]
                # Salva dados de autenticação
                os.makedirs(AUTH_DIR, exist_ok=True)
                user_id = uuid.uuid4().hex[:8]
                auth_data = {
                    'code': code,
                    'state': state,
                    'session_state': sess,
                    'timestamp': datetime.datetime.now(timezone.utc).isoformat()
                }
                out_file = os.path.join(AUTH_DIR, f'user_{user_id}.json')
                with open(out_file, 'w', encoding='utf-8') as f:
                    json.dump(auth_data, f, indent=2)
                save_last_user_id(user_id)
                print(f"✅ Saved auth data: {out_file}")
                await browser.close()
                raise asyncio.CancelledError

    # 6) Registra listener
    page.on('response', lambda resp: asyncio.ensure_future(on_response(resp)))

    # 7) Navega para login
    print("🌐 Opening login page…")
    await page.goto(LOGIN_URL, {'waitUntil': 'networkidle2'})
    await page.screenshot({'path': 'auth_start.png', 'fullPage': True})
    print("📸 Saved auth_start.png; please complete login in browser")

    # 8) Aguarda callback
    try:
        while True:
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        print("✅ Auth flow completed")

# ────────────────────────────────────────────────────────────────────────────────
# 5) Execução principal
# ────────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    asyncio.run(run_oidc_flow())
