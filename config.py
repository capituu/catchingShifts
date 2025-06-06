import os

# ────────────────────────────────────────────────────────────────────────────────
# Definimos BASE_DIR como a pasta "catchingShifts" (uma pasta acima de bot_manager)
# ────────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)

# Pasta "userauth" fica diretamente em BASE_DIR:
AUTH_DIR = os.path.join(BASE_DIR, "userauth")

LAST_USER_FILE = os.path.join(AUTH_DIR, "last_user.txt")

def save_last_user_id(user_id: str):
    """
    Grava o user_id em last_user.txt dentro de catchingShifts/userauth.
    """
    os.makedirs(AUTH_DIR, exist_ok=True)
    try:
        with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
            f.write(user_id)
        print(f"📄 Saved last user ID: {user_id}")
    except OSError as e:
        print(f"❌ Erro ao salvar last_user.txt: {e}")

def get_last_user_id() -> str | None:
    """
    Lê last_user.txt em catchingShifts/userauth. Retorna user_id ou None.
    """
    try:
        with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
    except OSError as e:
        print(f"❌ Erro ao ler last_user.txt: {e}")
        return None
