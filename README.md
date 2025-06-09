# catchingShifts

This project runs a small Flask application that manages a bot for fetching delivery shifts.

## Setup
1. Create and activate a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   The `pyppeteer-stealth` package now uses version `2.7.4`, which exists on
   PyPI. If you previously saw an installation error for version `1.1.0`,
   run `git pull` to update `requirements.txt` and reinstall the packages.

## Running
Start the application from the project root:
```bash
python bot_manager/app.py
```
The templates and static files reside under `bot_manager/`, so the server can be launched from any directory as long as you run this command.

After starting, visit [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your browser. The main page automatically calls `/state` and `/auth_status` to update its UI.

If you encounter `BuildError: Could not build url for endpoint 'auth_status'`,
ensure you are running the latest version of the code. The template now uses the
literal path `/auth_status` to avoid this issue.

If you see `TemplateNotFound: index.html`, ensure you pulled the latest code with `git pull` and restarted the server; the route configuration in `bot_manager/app.py` expects the templates inside the `bot_manager/templates` folder.
