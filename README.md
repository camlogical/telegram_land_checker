# Telegram Land Checker Bot

A Telegram bot for checking land information using the MLMUPC Cambodia service, with Google Sheets integration and user management.

## Features
- Telegram bot for user queries
- Google Sheets integration for logging
- User database management
- Flask server for webhooks/keep-alive

## Setup

1. **Clone the repository and create a virtual environment:**
   ```sh
   git clone <repo-url>
   cd telegram_land_checker
   python3 -m venv venv
   source venv/bin/activate
   ```
2. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Configure environment variables:**
   - Copy `.env.example` to `.env` and fill in all required values.

4. **Run the bot locally:**
   ```sh
   python telegram_land_checker.py
   ```
   Or in production:
   ```sh
   gunicorn telegram_land_checker:app
   ```

## Environment Variables
See `.env.example` for all required variables.

## Deployment
- Use the provided `Procfile` for deployment to platforms like Heroku or Railway.
- Ensure all secrets are set in your deployment environment.

## Security
- Never commit your `.env` file or secrets to git.
- Regenerate your bot token and credentials if they are ever exposed.

## License
MIT
