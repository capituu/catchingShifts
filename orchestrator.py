import subprocess
import sys

def run_script(script_name):
    print(f"🔄 Running {script_name}...")
    result = subprocess.run([sys.executable, script_name])
    if result.returncode != 0:
        print(f"❌ {script_name} failed with code {result.returncode}")
        sys.exit(result.returncode)
    else:
        print(f"✅ {script_name} finished successfully\n")

def main():
    print("🚀 Starting authentication flow...")
    
    # Step 1: Capture auth code
    run_script("auth_code_capture.py")
    
    # Step 2: Exchange tokens
    run_script("exchange_tokens.py")
    
    print("🎉 All steps completed. Tokens saved.")

if __name__ == "__main__":
    main()
