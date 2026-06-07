import os
import sqlite3
import uuid
from io import BytesIO
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageOps


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "memes.db"
IMAGES_DIR = BASE_DIR / "images"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
COMPRESSED_IMAGE_EXTENSION = ".webp"
MAX_IMAGE_WIDTH = 1000
WEBP_QUALITY = 82


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                phrase TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )


def process_image_bytes(image_bytes, original_filename):
    extension = Path(original_filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("対応している画像形式は png, jpg, gif, webp です。")

    if extension == ".gif":
        return image_bytes, extension

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            if image.width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / image.width
                new_size = (MAX_IMAGE_WIDTH, max(1, int(image.height * ratio)))
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")

            output = BytesIO()
            image.save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
            return output.getvalue(), COMPRESSED_IMAGE_EXTENSION
    except Exception as error:
        raise ValueError(f"画像を処理できませんでした: {error}") from error


def save_image_bytes(meme_id, image_bytes, original_filename):
    processed_bytes, extension = process_image_bytes(image_bytes, original_filename)
    image_filename = f"{meme_id}{extension}"
    image_disk_path = IMAGES_DIR / image_filename
    image_disk_path.write_bytes(processed_bytes)
    return str(Path("images") / image_filename)


def create_meme_from_bytes(title, phrase, tags, note, source_url, image_bytes, original_filename):
    meme_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    image_path = save_image_bytes(meme_id, image_bytes, original_filename)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO memes (id, title, phrase, tags, note, image_path, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meme_id,
                title.strip(),
                phrase.strip(),
                tags.strip(),
                note.strip(),
                image_path,
                source_url.strip(),
                created_at,
            ),
        )

    return meme_id


def row_to_meme(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "phrase": row["phrase"],
        "tags": row["tags"],
        "note": row["note"],
        "image_path": row["image_path"],
        "image_url": f"/{row['image_path'].replace(os.sep, '/')}",
        "source_url": row["source_url"],
        "created_at": row["created_at"],
    }


def normalize_text(value):
    return " ".join((value or "").lower().strip().split())


def score_meme(query, meme):
    normalized_query = normalize_text(query)
    if not normalized_query:
        return 1.0

    fields = [
        normalize_text(meme["title"]),
        normalize_text(meme["phrase"]),
        normalize_text(meme["tags"]),
        normalize_text(meme["note"]),
    ]
    combined = " ".join(fields)

    if normalized_query in combined:
        return 1.0

    token_hits = 0
    query_tokens = normalized_query.replace(",", " ").split()
    for token in query_tokens:
        if token and token in combined:
            token_hits += 1

    token_score = token_hits / max(len(query_tokens), 1)
    fuzzy_scores = [SequenceMatcher(None, normalized_query, field).ratio() for field in fields if field]
    fuzzy_score = max(fuzzy_scores, default=0.0)
    return max(token_score * 0.9, fuzzy_score)


def search_memes(query="", limit=None, min_score=0.25):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM memes ORDER BY created_at DESC").fetchall()

    memes = [row_to_meme(row) for row in rows]
    scored = [
        {**meme, "score": round(score_meme(query, meme), 3)}
        for meme in memes
    ]

    if query:
        scored = [meme for meme in scored if meme["score"] >= min_score]

    scored.sort(key=lambda meme: (meme["score"], meme["created_at"]), reverse=True)
    if limit is not None:
        return scored[:limit]
    return scored


def get_meme(meme_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM memes WHERE id = ?", (meme_id,)).fetchone()
    return row_to_meme(row) if row else None


def get_meme_image_path(meme_id):
    meme = get_meme(meme_id)
    if not meme:
        return None
    return BASE_DIR / meme["image_path"]
