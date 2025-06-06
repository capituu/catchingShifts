import requests
import json
import os
from config import get_last_user_id, AUTH_DIR

# 1. Determine which user’s tokens to load
USER_ID = get_last_user_id()
if not USER_ID:
    print("❌ No user ID found. Run auth_code_capture.py + token_exchange.py first.")
    exit(1)

TOKEN_FILE = os.path.join(AUTH_DIR, f"tokens_user_{USER_ID}.json")

# 2. Load tokens and courier_id from disk
try:
    with open(TOKEN_FILE, "r") as f:
        token_data = json.load(f)
except FileNotFoundError:
    print(f"❌ Token file not found: {TOKEN_FILE}")
    exit(1)
except json.JSONDecodeError:
    print(f"❌ Failed to parse JSON in: {TOKEN_FILE}")
    exit(1)

access_token = token_data.get("access_token")
courier_id   = token_data.get("courier_id")

if not access_token or not courier_id:
    print("❌ access_token or courier_id missing in token_data.")
    exit(1)

# 3. Build and send the GET request
API_URL = f"https://api-courier-produk.skipthedishes.com/v2/couriers/{courier_id}"
headers = { "Authorization": f"Bearer {access_token}" }

print(f"🛰️ Fetching user info for courier_id={courier_id}...")
resp = requests.get(API_URL, headers=headers)

# 4. Check for errors
if resp.status_code != 200:
    print(f"❌ Failed to fetch user info: HTTP {resp.status_code}")
    try:
        print("Response JSON:", resp.json())
    except:
        print("Response text:", resp.text)
    exit(1)

# 5. Print the user’s info
user_info = resp.json()
print("✅ User Info:")
print(json.dumps(user_info, indent=2))
