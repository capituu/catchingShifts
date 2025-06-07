# catchingShifts

This project runs a small Flask application that manages a bot for fetching delivery shifts.

## Setup
1. Create and activate a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running
Start the application from the project root:
```bash
python bot_manager/app.py
```
The templates and static files reside under `bot_manager/`, so the server can be launched from any directory as long as you run this command.

After starting, visit [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your browser. The main page automatically calls `/state` and `/auth_status` to update its UI.

If you see `TemplateNotFound: index.html`, ensure you pulled the latest code with `git pull` and restarted the server; the route configuration in `bot_manager/app.py` expects the templates inside the `bot_manager/templates` folder.
