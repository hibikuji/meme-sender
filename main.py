import os
import secrets
import time
import hmac
import hashlib
import base64
import json

import requests
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from meme_store import (
    BASE_DIR,
    IMAGES_DIR,
    create_meme_from_bytes,
    delete_meme as delete_meme_record,
    find_image_matches,
    get_meme,
    get_meme_image_path,
    init_db,
    search_memes,
    update_meme as update_meme_record,
)


DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
MEME_ADMIN_PASSWORD = os.getenv("MEME_ADMIN_PASSWORD", "")
MEME_ADMIN_TOKEN_DAYS = int(os.getenv("MEME_ADMIN_TOKEN_DAYS", "90"))

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


def encode_token_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_token_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def get_token_secret() -> bytes:
    if not MEME_ADMIN_PASSWORD:
        raise HTTPException(
            status_code=403,
            detail="MEME_ADMIN_PASSWORD が設定されていません。追加・編集・削除を使うには管理パスワードを設定してください。",
        )
    return MEME_ADMIN_PASSWORD.encode("utf-8")


def create_admin_token() -> str:
    expires_at = int(time.time()) + MEME_ADMIN_TOKEN_DAYS * 24 * 60 * 60
    payload = {"exp": expires_at, "purpose": "meme-admin"}
    payload_part = encode_token_part(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(get_token_secret(), payload_part.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_part}.{encode_token_part(signature)}"


def verify_admin_token(token: str) -> bool:
    if not token or "." not in token:
        return False

    payload_part, signature_part = token.split(".", 1)
    expected_signature = hmac.new(get_token_secret(), payload_part.encode("ascii"), hashlib.sha256).digest()

    try:
        signature = decode_token_part(signature_part)
        payload = json.loads(decode_token_part(payload_part))
    except (ValueError, json.JSONDecodeError):
        return False

    if not hmac.compare_digest(signature, expected_signature):
        return False

    return payload.get("purpose") == "meme-admin" and int(payload.get("exp", 0)) > int(time.time())


def require_admin(
    x_meme_admin_password: str = Header(""),
    x_meme_admin_token: str = Header(""),
):
    get_token_secret()

    if x_meme_admin_token and verify_admin_token(x_meme_admin_token):
        return

    if not secrets.compare_digest(x_meme_admin_password, MEME_ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="管理ログインが必要です。")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
async def get_index():
    index_path = BASE_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/memes")
async def list_memes(q: str = ""):
    return {"memes": search_memes(q)}


@app.post("/api/auth/check")
async def check_admin(_: None = Depends(require_admin)):
    return {"status": "success"}


@app.post("/api/auth/login")
async def login_admin(_: None = Depends(require_admin)):
    return {
        "status": "success",
        "token": create_admin_token(),
        "expires_in_days": MEME_ADMIN_TOKEN_DAYS,
    }


@app.post("/api/memes")
async def create_meme(
    _: None = Depends(require_admin),
    title: str = Form(...),
    phrase: str = Form(...),
    tags: str = Form(""),
    note: str = Form(""),
    source_url: str = Form(""),
    force_duplicate: str = Form("false"),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()
    try:
        matches = find_image_matches(image_bytes, image.filename or "")
        if force_duplicate != "true" and (matches["exact"] or matches["similar"]):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "似ている画像が既に登録されています。",
                    "matches": matches,
                },
            )

        meme_id = create_meme_from_bytes(
            title=title,
            phrase=phrase,
            tags=tags,
            note=note,
            source_url=source_url,
            image_bytes=image_bytes,
            original_filename=image.filename or "",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"status": "success", "meme_id": meme_id}


@app.put("/api/memes/{meme_id}")
async def update_meme(
    meme_id: str,
    _: None = Depends(require_admin),
    title: str = Form(...),
    phrase: str = Form(...),
    tags: str = Form(""),
    note: str = Form(""),
    source_url: str = Form(""),
    force_duplicate: str = Form("false"),
    image: UploadFile | None = File(None),
):
    image_bytes = await image.read() if image and image.filename else None
    try:
        result = update_meme_record(
            meme_id=meme_id,
            title=title,
            phrase=phrase,
            tags=tags,
            note=note,
            source_url=source_url,
            image_bytes=image_bytes,
            original_filename=image.filename if image else "",
            force_duplicate=force_duplicate == "true",
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if result["status"] == "duplicate":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "似ている画像が既に登録されています。",
                "matches": result["matches"],
            },
        )

    return {"status": "success", "meme_id": meme_id}


@app.delete("/api/memes/{meme_id}")
async def delete_meme(meme_id: str, _: None = Depends(require_admin)):
    try:
        delete_meme_record(meme_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return {"status": "success"}


@app.post("/api/memes/{meme_id}/discord")
async def send_to_discord(meme_id: str, _: None = Depends(require_admin)):
    if not DISCORD_WEBHOOK_URL:
        raise HTTPException(
            status_code=400,
            detail="DISCORD_WEBHOOK_URL が設定されていません。今後Bot方式に移行する場合、この機能は使わなくてもOKです。",
        )

    meme = get_meme(meme_id)
    if not meme:
        raise HTTPException(status_code=404, detail="ミームが見つかりません。")

    image_path = get_meme_image_path(meme_id)
    if image_path and image_path.exists():
        with image_path.open("rb") as f:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                data={"content": meme["phrase"]},
                files={"file": f},
                timeout=10,
            )
    else:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            data={"content": f"{meme['phrase']}\n{meme['image_url']}"},
            timeout=10,
        )
    response.raise_for_status()
    return {"status": "success"}
