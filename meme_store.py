import os
import hashlib
import sqlite3
import uuid
from io import BytesIO
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests
from PIL import Image, ImageOps


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "memes.db"
IMAGES_DIR = BASE_DIR / "images"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
COMPRESSED_IMAGE_EXTENSION = ".webp"
MAX_IMAGE_WIDTH = 1000
WEBP_QUALITY = 82
SIMILAR_IMAGE_DISTANCE = 8
MEME_STORE_BACKEND = os.getenv("MEME_STORE_BACKEND", "sqlite").lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "memes")


def use_supabase():
    return MEME_STORE_BACKEND == "supabase"


def require_supabase_config():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY が設定されていません。")


def supabase_headers(extra=None):
    require_supabase_config()
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if extra:
        headers.update(extra)
    return headers


def supabase_request(method, path, **kwargs):
    response = requests.request(
        method,
        f"{SUPABASE_URL}{path}",
        headers=supabase_headers(kwargs.pop("headers", None)),
        timeout=20,
        **kwargs,
    )
    response.raise_for_status()
    if response.content:
        return response.json()
    return None


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if use_supabase():
        require_supabase_config()
        return

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
        ensure_column(conn, "image_sha256", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "image_ahash", "TEXT NOT NULL DEFAULT ''")
    backfill_image_hashes()


def ensure_column(conn, column_name, column_definition):
    columns = conn.execute("PRAGMA table_info(memes)").fetchall()
    if column_name not in {column["name"] for column in columns}:
        conn.execute(f"ALTER TABLE memes ADD COLUMN {column_name} {column_definition}")


def image_sha256(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()


def image_average_hash(image_bytes):
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            pixels = list(image.getdata())
    except Exception as error:
        raise ValueError(f"画像の見た目ハッシュを作成できませんでした: {error}") from error

    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def image_hashes(image_bytes):
    return image_sha256(image_bytes), image_average_hash(image_bytes)


def hamming_distance(left_hash, right_hash):
    if not left_hash or not right_hash:
        return 64
    return (int(left_hash, 16) ^ int(right_hash, 16)).bit_count()


def match_to_summary(meme, match_type, distance=0):
    return {
        "id": meme["id"],
        "title": meme["title"],
        "phrase": meme["phrase"],
        "tags": meme["tags"],
        "image_url": meme["image_url"],
        "match_type": match_type,
        "distance": distance,
    }


def find_image_matches(image_bytes, original_filename="", exclude_id=None, similar_distance=SIMILAR_IMAGE_DISTANCE):
    processed_bytes, _ = process_image_bytes(image_bytes, original_filename)
    sha256_hash, ahash = image_hashes(processed_bytes)
    exact_matches = []
    similar_matches = []

    if use_supabase():
        rows = supabase_list_memes()
        if exclude_id:
            rows = [row for row in rows if row["id"] != exclude_id]
    else:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM memes WHERE id != ?", (exclude_id or "",)).fetchall()

    for row in rows:
        meme = row_to_meme(row)
        if row["image_sha256"] and row["image_sha256"] == sha256_hash:
            exact_matches.append(match_to_summary(meme, "exact", 0))
            continue

        distance = hamming_distance(ahash, row["image_ahash"])
        if distance <= similar_distance:
            similar_matches.append(match_to_summary(meme, "similar", distance))

    similar_matches.sort(key=lambda match: match["distance"])
    return {
        "image_sha256": sha256_hash,
        "image_ahash": ahash,
        "exact": exact_matches,
        "similar": similar_matches,
    }


def backfill_image_hashes():
    with get_db() as conn:
        rows = conn.execute("SELECT id, image_path FROM memes").fetchall()

        for row in rows:
            image_path = BASE_DIR / row["image_path"]
            if not image_path.exists() or not image_path.is_file():
                continue

            try:
                image_bytes = image_path.read_bytes()
                processed_bytes, _ = process_image_bytes(image_bytes, image_path.name)
                sha256_hash, ahash = image_hashes(processed_bytes)
            except ValueError:
                continue

            conn.execute(
                "UPDATE memes SET image_sha256 = ?, image_ahash = ? WHERE id = ?",
                (sha256_hash, ahash, row["id"]),
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
    if use_supabase():
        return save_image_bytes_supabase(meme_id, image_bytes, original_filename)

    processed_bytes, extension = process_image_bytes(image_bytes, original_filename)
    image_filename = f"{meme_id}{extension}"
    image_disk_path = IMAGES_DIR / image_filename
    image_disk_path.write_bytes(processed_bytes)
    sha256_hash, ahash = image_hashes(processed_bytes)
    return str(Path("images") / image_filename), sha256_hash, ahash


def create_meme_from_bytes(title, phrase, tags, note, source_url, image_bytes, original_filename):
    if use_supabase():
        return create_meme_from_bytes_supabase(title, phrase, tags, note, source_url, image_bytes, original_filename)

    meme_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    image_path, sha256_hash, ahash = save_image_bytes(meme_id, image_bytes, original_filename)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO memes
                (id, title, phrase, tags, note, image_path, source_url, created_at, image_sha256, image_ahash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                sha256_hash,
                ahash,
            ),
        )

    return meme_id


def row_to_meme(row):
    image_path = row["image_path"] if "image_path" in row.keys() else ""
    image_url = row["image_url"] if "image_url" in row.keys() else ""
    if not image_url and image_path:
        image_url = f"/{image_path.replace(os.sep, '/')}"

    return {
        "id": row["id"],
        "title": row["title"],
        "phrase": row["phrase"],
        "tags": row["tags"],
        "note": row["note"],
        "image_path": image_path,
        "image_url": image_url,
        "source_url": row["source_url"],
        "created_at": row["created_at"],
        "image_sha256": row["image_sha256"],
        "image_ahash": row["image_ahash"],
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
    if use_supabase():
        rows = supabase_list_memes()
    else:
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
    if use_supabase():
        rows = supabase_request("GET", f"/rest/v1/memes?id=eq.{meme_id}&select=*&limit=1")
        return row_to_meme(rows[0]) if rows else None

    with get_db() as conn:
        row = conn.execute("SELECT * FROM memes WHERE id = ?", (meme_id,)).fetchone()
    return row_to_meme(row) if row else None


def get_meme_image_path(meme_id):
    if use_supabase():
        return None

    meme = get_meme(meme_id)
    if not meme:
        return None
    return BASE_DIR / meme["image_path"]


def supabase_list_memes():
    return supabase_request("GET", "/rest/v1/memes?select=*&order=created_at.desc") or []


def supabase_public_image_url(filename):
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"


def save_image_bytes_supabase(meme_id, image_bytes, original_filename):
    processed_bytes, extension = process_image_bytes(image_bytes, original_filename)
    sha256_hash, ahash = image_hashes(processed_bytes)
    image_filename = f"{meme_id}{extension}"

    response = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{image_filename}",
        headers=supabase_headers(
            {
                "Content-Type": "image/gif" if extension == ".gif" else "image/webp",
                "x-upsert": "true",
            }
        ),
        data=processed_bytes,
        timeout=20,
    )
    response.raise_for_status()

    return supabase_public_image_url(image_filename), sha256_hash, ahash


def create_meme_from_bytes_supabase(title, phrase, tags, note, source_url, image_bytes, original_filename):
    meme_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    image_url, sha256_hash, ahash = save_image_bytes_supabase(meme_id, image_bytes, original_filename)

    supabase_request(
        "POST",
        "/rest/v1/memes",
        headers={
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={
            "id": meme_id,
            "title": title.strip(),
            "phrase": phrase.strip(),
            "tags": tags.strip(),
            "note": note.strip(),
            "image_url": image_url,
            "source_url": source_url.strip(),
            "image_sha256": sha256_hash,
            "image_ahash": ahash,
            "created_at": created_at,
        },
    )
    return meme_id


def update_meme(
    meme_id,
    title,
    phrase,
    tags,
    note,
    source_url,
    image_bytes=None,
    original_filename="",
    force_duplicate=False,
):
    if use_supabase():
        return update_meme_supabase(
            meme_id,
            title,
            phrase,
            tags,
            note,
            source_url,
            image_bytes,
            original_filename,
            force_duplicate,
        )
    return update_meme_sqlite(
        meme_id,
        title,
        phrase,
        tags,
        note,
        source_url,
        image_bytes,
        original_filename,
        force_duplicate,
    )


def update_meme_sqlite(
    meme_id,
    title,
    phrase,
    tags,
    note,
    source_url,
    image_bytes=None,
    original_filename="",
    force_duplicate=False,
):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM memes WHERE id = ?", (meme_id,)).fetchone()
        if not row:
            raise KeyError("ミームが見つかりません。")

        image_path = row["image_path"]
        image_sha256_value = row["image_sha256"]
        image_ahash_value = row["image_ahash"]
        if image_bytes is not None:
            matches = find_image_matches(image_bytes, original_filename, exclude_id=meme_id)
            if not force_duplicate and (matches["exact"] or matches["similar"]):
                return {"status": "duplicate", "matches": matches}

            image_path, image_sha256_value, image_ahash_value = save_image_bytes(
                meme_id=meme_id,
                image_bytes=image_bytes,
                original_filename=original_filename,
            )

            old_image_path = BASE_DIR / row["image_path"]
            new_image_path = BASE_DIR / image_path
            if old_image_path != new_image_path and old_image_path.exists() and old_image_path.is_file():
                old_image_path.unlink()

        conn.execute(
            """
            UPDATE memes
            SET title = ?, phrase = ?, tags = ?, note = ?, source_url = ?,
                image_path = ?, image_sha256 = ?, image_ahash = ?
            WHERE id = ?
            """,
            (
                title.strip(),
                phrase.strip(),
                tags.strip(),
                note.strip(),
                source_url.strip(),
                image_path,
                image_sha256_value,
                image_ahash_value,
                meme_id,
            ),
        )

    return {"status": "success", "meme_id": meme_id}


def update_meme_supabase(
    meme_id,
    title,
    phrase,
    tags,
    note,
    source_url,
    image_bytes=None,
    original_filename="",
    force_duplicate=False,
):
    existing = get_meme(meme_id)
    if not existing:
        raise KeyError("ミームが見つかりません。")

    payload = {
        "title": title.strip(),
        "phrase": phrase.strip(),
        "tags": tags.strip(),
        "note": note.strip(),
        "source_url": source_url.strip(),
    }

    if image_bytes is not None:
        matches = find_image_matches(image_bytes, original_filename, exclude_id=meme_id)
        if not force_duplicate and (matches["exact"] or matches["similar"]):
            return {"status": "duplicate", "matches": matches}

        image_url, sha256_hash, ahash = save_image_bytes_supabase(meme_id, image_bytes, original_filename)
        payload.update(
            {
                "image_url": image_url,
                "image_sha256": sha256_hash,
                "image_ahash": ahash,
            }
        )

    supabase_request(
        "PATCH",
        f"/rest/v1/memes?id=eq.{meme_id}",
        headers={
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=payload,
    )
    return {"status": "success", "meme_id": meme_id}


def delete_meme(meme_id):
    if use_supabase():
        supabase_request("DELETE", f"/rest/v1/memes?id=eq.{meme_id}")
        return

    with get_db() as conn:
        row = conn.execute("SELECT image_path FROM memes WHERE id = ?", (meme_id,)).fetchone()
        if not row:
            raise KeyError("ミームが見つかりません。")
        conn.execute("DELETE FROM memes WHERE id = ?", (meme_id,))

    image_path = BASE_DIR / row["image_path"]
    if image_path.exists() and image_path.is_file():
        image_path.unlink()
