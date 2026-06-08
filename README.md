# Meme Sender

Discord bot and local web app for registering, searching, and sending meme images.

## Features

- Register meme images with title, phrase, tags, note, and source URL
- Store data in SQLite and image files locally
- Search memes by fuzzy text matching
- Edit and delete registered memes from the web UI
- Send memes from Discord with `/meme`
- Register image attachments from Discord message context menu
- Auto-start scripts for Windows local use

## Tech Stack

- Python
- FastAPI
- SQLite / Supabase PostgreSQL
- Supabase Storage
- discord.py
- HTML / CSS / JavaScript

## Setup

Create and activate a virtual environment, then install dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set Discord bot settings as Windows user environment variables.

```powershell
setx DISCORD_BOT_TOKEN "your_bot_token"
setx DISCORD_GUILD_ID "your_discord_server_id"
```

Open a new PowerShell window after running `setx`.

## Run Locally

Start the web app.

```powershell
.\scripts\start_web.ps1
```

Open:

```text
http://127.0.0.1:8000/
```

Start the Discord bot.

```powershell
.\scripts\start_bot.ps1
```

Start both in the background.

```powershell
.\scripts\start_all.ps1
```

## Supabase Backend

The app can use either local SQLite or Supabase.

```powershell
setx MEME_STORE_BACKEND "supabase"
setx SUPABASE_URL "https://your-project.supabase.co"
setx SUPABASE_SERVICE_ROLE_KEY "your_service_role_key"
setx SUPABASE_BUCKET "memes"
```

Use `sqlite` to return to local storage.

```powershell
setx MEME_STORE_BACKEND "sqlite"
```

The Supabase project needs:

- A public Storage bucket named `memes`
- A `public.memes` PostgreSQL table

Migrate local SQLite records to Supabase:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_supabase.py
```

## Split Cloud Deployment

Recommended free-oriented deployment:

- Render runs the FastAPI web app.
- KEITO Cloud runs the Discord bot.
- Supabase stores the database rows and images.

### Render Web Service

Render should run the web app only.

Start command:

```text
python start_web_cloud.py
```

Required Render environment variables:

```text
MEME_ADMIN_PASSWORD
MEME_ADMIN_TOKEN_DAYS=90
MEME_STORE_BACKEND=supabase
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=memes
LOG_LEVEL=info
```

The app exposes a health check endpoint:

```text
/health
```

### KEITO Cloud Bot

KEITO Cloud should run the Discord bot only.

Start file:

```text
bot.py
```

Required KEITO Cloud environment variables:

```text
DISCORD_BOT_TOKEN
DISCORD_GUILD_ID
MEME_ADMIN_DISCORD_USER_IDS
MEME_STORE_BACKEND=supabase
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=memes
```

### Single-Service Cloud Entrypoint

If a cloud provider can run the web app and bot in one always-on service, use:

```text
python start_cloud.py
```

`start_cloud.py` runs the FastAPI web app and the Discord bot in the same Python process.
This was originally intended for a single free web service such as Koyeb.

Required environment variables for single-service cloud use:

```text
DISCORD_BOT_TOKEN
DISCORD_GUILD_ID
MEME_ADMIN_PASSWORD
MEME_ADMIN_DISCORD_USER_IDS
MEME_STORE_BACKEND=supabase
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=memes
```

Optional environment variables:

```text
MEME_ADMIN_TOKEN_DAYS=90
PORT=8000
LOG_LEVEL=info
```

## Access From a Phone on the Same Wi-Fi

Start the web app with `start_web.ps1`, then find this PC's local IP address.

```powershell
ipconfig
```

Open this from the phone:

```text
http://YOUR_PC_IP:8000/
```

Example:

```text
http://192.168.1.20:8000/
```

## Windows Auto Start

Register a Windows Task Scheduler task that starts the web app and bot when this Windows user logs in.

```powershell
.\scripts\register_startup_task.ps1
```

The task name is:

```text
MemeSenderAutoStart
```

## Security Notes

Do not commit real Discord bot tokens, `.env` files, `memes.db`, or uploaded images.

This repository intentionally ignores local data and secrets with `.gitignore`.
