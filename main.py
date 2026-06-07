import os

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from meme_store import BASE_DIR, IMAGES_DIR, create_meme_from_bytes, get_db, init_db, save_image_bytes, search_memes


DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGES_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
async def get_index():
    index_path = BASE_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/memes")
async def list_memes(q: str = ""):
    return {"memes": search_memes(q)}


@app.post("/api/memes")
async def create_meme(
    title: str = Form(...),
    phrase: str = Form(...),
    tags: str = Form(""),
    note: str = Form(""),
    source_url: str = Form(""),
    image: UploadFile = File(...),
):
    try:
        meme_id = create_meme_from_bytes(
            title=title,
            phrase=phrase,
            tags=tags,
            note=note,
            source_url=source_url,
            image_bytes=await image.read(),
            original_filename=image.filename or "",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"status": "success", "meme_id": meme_id}


@app.put("/api/memes/{meme_id}")
async def update_meme(
    meme_id: str,
    title: str = Form(...),
    phrase: str = Form(...),
    tags: str = Form(""),
    note: str = Form(""),
    source_url: str = Form(""),
    image: UploadFile | None = File(None),
):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM memes WHERE id = ?", (meme_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ミームが見つかりません。")

        image_path = row["image_path"]
        if image and image.filename:
            try:
                image_path = save_image_bytes(
                    meme_id=meme_id,
                    image_bytes=await image.read(),
                    original_filename=image.filename,
                )
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

            old_image_path = BASE_DIR / row["image_path"]
            new_image_path = BASE_DIR / image_path
            if old_image_path != new_image_path and old_image_path.exists() and old_image_path.is_file():
                old_image_path.unlink()

        conn.execute(
            """
            UPDATE memes
            SET title = ?, phrase = ?, tags = ?, note = ?, source_url = ?, image_path = ?
            WHERE id = ?
            """,
            (
                title.strip(),
                phrase.strip(),
                tags.strip(),
                note.strip(),
                source_url.strip(),
                image_path,
                meme_id,
            ),
        )

    return {"status": "success", "meme_id": meme_id}


@app.delete("/api/memes/{meme_id}")
async def delete_meme(meme_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT image_path FROM memes WHERE id = ?", (meme_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ミームが見つかりません。")
        conn.execute("DELETE FROM memes WHERE id = ?", (meme_id,))

    image_path = BASE_DIR / row["image_path"]
    if image_path.exists() and image_path.is_file():
        image_path.unlink()

    return {"status": "success"}


@app.post("/api/memes/{meme_id}/discord")
async def send_to_discord(meme_id: str):
    if not DISCORD_WEBHOOK_URL:
        raise HTTPException(
            status_code=400,
            detail="DISCORD_WEBHOOK_URL が設定されていません。今後Bot方式に移行する場合、この機能は使わなくてもOKです。",
        )

    with get_db() as conn:
        row = conn.execute("SELECT * FROM memes WHERE id = ?", (meme_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ミームが見つかりません。")

    image_path = BASE_DIR / row["image_path"]
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="画像ファイルが見つかりません。")

    with image_path.open("rb") as f:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            data={"content": row["phrase"]},
            files={"file": f},
            timeout=10,
        )
    response.raise_for_status()
    return {"status": "success"}
