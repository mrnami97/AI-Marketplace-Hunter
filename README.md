# AI Marketplace Hunter

A Telegram-based marketplace search and watchlist assistant.

## Current working features

- `/search RTX 3070 under RM900 in Sabah`
- `/watch RTX 3070 under RM900 in Sabah`
- `/list`
- `/remove 1`
- SQLite watchlist storage
- Direct Carousell and Facebook Marketplace search links

## Planned crawler fields

- Listing title
- Price
- Location
- Source
- Posted time
- First seen
- Last seen
- Active/removed status
- Direct listing link

## Windows setup

### 1. Open this folder in Visual Studio Code

Open a terminal in the project folder.

### 2. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install packages

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 4. Create your Telegram bot

1. Open Telegram.
2. Search for `@BotFather`.
3. Send `/newbot`.
4. Choose a name and username.
5. Copy the token.

### 5. Configure the project

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Open `.env` and replace:

```text
TELEGRAM_BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
```

with your real token.

### 6. Run

```powershell
python app.py
```

You should see:

```text
AI Marketplace Hunter is running...
```

Then open your bot in Telegram and send:

```text
/start
```

## Add the bot to a Telegram group

1. Open the Telegram group.
2. Add the bot as a member.
3. In BotFather, use `/setprivacy`.
4. Select your bot.
5. Choose `Disable` so it can read commands in the group.

The bot only reacts to slash commands in this version.

## Important

Facebook and Carousell frequently change their page layouts and may restrict automated access. The crawler should use your normal browser session only where permitted and should not bypass access controls.
