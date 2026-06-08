import asyncio
import os

import uvicorn

import bot
from main import app
from meme_store import init_db


async def run_web():
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info"),
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot():
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        print("DISCORD_BOT_TOKEN is not set. Starting web server only.")
        return

    await bot.client.start(token)


async def main():
    init_db()
    await asyncio.gather(run_web(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
