import asyncio
import uuid
import os
import json
import datetime
import urllib.parse as urlparse
import subprocess

from pyppeteer import launch
from pyppeteer.connection import Connection  # Add this import
from pyppeteer_stealth import stealth
from config import save_last_user_id, AUTH_DIR

# Chrome/Chromium executable path. Use environment variable if provided,
# falling back to a common Windows installation path.
CHROME_PATH = os.environ.get(
    "PUPPETEER_EXECUTABLE_PATH",
    r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
)

def verify_chrome_path():
    """Verify Chrome executable exists and is runnable"""
    if not os.path.exists(CHROME_PATH):
        print(f"❌ Chrome not found at: {CHROME_PATH}")
        return False
    
    if not os.path.isfile(CHROME_PATH):
        print(f"❌ Path exists but is not a file: {CHROME_PATH}")
        return False
    
    try:
        # Try to get Chrome version
        result = subprocess.run([CHROME_PATH, '--version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        print(f"✅ Chrome version check: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"❌ Failed to execute Chrome: {str(e)}")
        return False

# Define iPhone X device configuration manually
IPHONE_DEVICE = {
    'name': 'iPhone X',
    'userAgent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    'viewport': {
        'width': 375,
        'height': 812,
        'deviceScaleFactor': 3,
        'isMobile': True,
        'hasTouch': True,
        'isLandscape': False
    }
}

# 1) Generate a random “state” value for CSRF protection
STATE = str(uuid.uuid4())

LOGIN_URL = (
    "https://api-produk.skipthedishes.com/auth/realms/Courier/"
    "protocol/openid-connect/auth?"
    "client_id=courier_mobile_jet_uk"
    "&redirect_uri=courierapp%3A%2F%2Fhomepage"
    "&response_mode=fragment"
    f"&state={STATE}"
    "&response_type=code"
    "&scope=openid%20profile%20email%20offline_access"
    "&prompt=login"
)

async def verify_browser_launch():
    """Test if Pyppeteer can launch Chrome"""
    try:
        print("🔍 Testing Chrome launch...")
        test_browser = await launch(
            executablePath=CHROME_PATH,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--no-startup-window",
                "--no-default-browser-check"
            ]
        )
        await test_browser.close()
        print("✅ Chrome launch test successful")
        return True
    except Exception as e:
        print(f"❌ Failed to launch Chrome: {str(e)}")
        return False

async def run():
    print("\n=== Chrome Verification ===")
    if not verify_chrome_path():
        print("❌ Aborting: Chrome executable verification failed")
        return
    
    if not await verify_browser_launch():
        print("❌ Aborting: Chrome launch test failed")
        return

    # Expose the Chrome path for pyppeteer
    os.environ["PUPPETEER_EXECUTABLE_PATH"] = CHROME_PATH

    print("\n=== Debug Information ===")
    print(f"Chrome Path: {CHROME_PATH}")
    print(f"File exists: {os.path.exists(CHROME_PATH)}")
    print(f"Is file: {os.path.isfile(CHROME_PATH)}")
    print(f"File size: {os.path.getsize(CHROME_PATH)} bytes")
    print(f"Working directory: {os.getcwd()}")
    print(f"PUPPETEER_PRODUCT: {os.environ.get('PUPPETEER_PRODUCT')}")
    print(f"PUPPETEER_EXECUTABLE_PATH: {os.environ.get('PUPPETEER_EXECUTABLE_PATH')}")

    try:
        browser = await launch(
            executablePath=CHROME_PATH,
            headless=False,
            ignoreDefaultArgs=[
                "--enable-automation",
                "--enable-blink-features=AutomationControlled"
            ],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-component-update",
                "--browser-test",  # Force browser check
                f"--user-data-dir={os.path.join(os.getcwd(), 'chrome-data')}"  # Custom profile dir
            ],
            ignoreHTTPSErrors=True,
            product="chrome"
        )
    except Exception as e:
        print(f"❌ Failed to launch Chrome: {str(e)}")
        print("❌ Script cannot continue without Chrome/Chromium")
        return

    page = await browser.newPage()

    # 4) Emulate iPhone X (sets UA, viewport, DPR, touch, etc.)
    await page.setUserAgent(IPHONE_DEVICE['userAgent'])
    await page.setViewport(IPHONE_DEVICE['viewport'])

    # 5) Run stealth to reduce bot detection
    await stealth(page)

    # 6) Log all requests/responses (for debugging)
    page.on("request", lambda req: print(f"[→ REQUEST ] {req.method} {req.url}"))
    page.on("response", lambda res: print(f"[← RESPONSE] {res.status} {res.url}"))

    # 7) Define handle_response as a coroutine, and register it properly
    async def handle_response(resp):
        # Whenever Keycloak returns a 302, check if it’s to courierapp://
        if resp.status == 302:
            location = resp.headers.get("location", "")
            if location.startswith("courierapp://"):
                print("📨 302→ Location header:", location)

                # Parse the fragment from that Location header
                parsed = urlparse.urlparse(location)
                fragment = urlparse.parse_qs(parsed.fragment)

                code          = fragment.get("code", [""])[0]
                state_value   = fragment.get("state", [""])[0]
                session_state = fragment.get("session_state", [""])[0]

                print("   · code         =", code)
                print("   · state        =", state_value)
                print("   · session_state=", session_state)

                # 8) Save the auth data immediately
                os.makedirs(AUTH_DIR, exist_ok=True)
                user_id = uuid.uuid4().hex[:8]
                auth_data = {
                    "code": code,
                    "state": state_value,
                    "session_state": session_state,
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
                }
                output_file = os.path.join(AUTH_DIR, f"user_{user_id}.json")
                with open(output_file, "w") as f:
                    json.dump(auth_data, f, indent=2)

                save_last_user_id(user_id)
                print(f"✅ Auth data saved to: {output_file}")
                print(f"👤 User ID: {user_id}")

                # 9) Close the browser and stop the script
                await browser.close()
                # Raise CancelledError so the main loop ends
                raise asyncio.CancelledError

    # 10) Register handle_response, but ensure we await it properly by wrapping in ensure_future
    page.on("response", lambda resp: asyncio.ensure_future(handle_response(resp)))

    # 11) Navigate to the login page
    print("🌐 Opening login page…")
    await page.goto(LOGIN_URL, {"waitUntil": "networkidle2"})

    # 12) Screenshot for debugging
    await page.screenshot({"path": "before_login.png", "fullPage": True})
    print("📸 Saved before_login.png")

    print("👉 Please enter your credentials and click Login.")
    print("🕵️ Waiting for redirect to courierapp://…")

    # 13) Keep the script alive until handle_response closes the browser
    try:
        while True:
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        # We expect this once handle_response() sees the 302 and calls browser.close()
        return

# 14) Run the async function
asyncio.run(run())
