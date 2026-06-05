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
- SQLite
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
