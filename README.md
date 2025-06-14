# Catching Shifts

This project contains a collection of Python scripts used to authenticate with the
SkipTheDishes API and automatically fetch or confirm courier shifts.

## Requirements

- Python 3.11+
- Google Chrome or Chromium installed.
- `PUPPETEER_EXECUTABLE_PATH` environment variable pointing to the Chrome executable.
  Example values:
  - Windows: `C:\Program Files\Google\Chrome\Application\chrome.exe`
  - Linux: `/usr/bin/chromium-browser` or `/usr/bin/google-chrome`
  You can verify the path by running `chrome --version` or `chromium-browser --version`.

Install dependencies with:

```bash
python -m venv venv
venv\Scripts\activate   # On Windows
pip install -r requirements.txt
```

## Running

To collect shifts periodically via Flask interface run:

```bash
python bot_manager/app.py
```

The application starts a local web server at `http://127.0.0.1:5000/`.
Use the **Connect** button to authenticate. A Chromium window will open and
mimic the official mobile app using the `courierapp://homepage` redirect URI.
After you finish logging in, the window closes automatically. If necessary, you
can override the redirect using the `REDIRECT_URI` environment variable.
Tokens are stored in `userauth/`.
The login window stays open until the authentication code is captured or a
timeout occurs. You can change the timeout (default 180 seconds) using the
`LOGIN_TIMEOUT_SECONDS` environment variable.
Use the **Connect** button to authenticate. By default the login flow mimics
the official mobile app and uses the `courierapp://homepage` redirect URI.
If necessary, you can override this with the `REDIRECT_URI` environment
variable. Tokens are stored in `userauth/`.

To run the individual authorization flow from the terminal you can also run:

```bash
python orchestrator.py
```

## Development notes

Temporary data such as authentication files and Chrome profile data are ignored
by Git through `.gitignore`.
