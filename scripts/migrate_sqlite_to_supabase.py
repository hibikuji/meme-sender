import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import meme_store


def load_sqlite_memes():
    conn = sqlite3.connect(meme_store.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM memes ORDER BY created_at ASC").fetchall()
    finally:
        conn.close()


def supabase_meme_exists(meme_id):
    rows = meme_store.supabase_request("GET", f"/rest/v1/memes?id=eq.{meme_id}&select=id&limit=1")
    return bool(rows)


def migrate_one(row):
    meme_id = row["id"]
    if supabase_meme_exists(meme_id):
        return "skipped"

    image_path = meme_store.BASE_DIR / row["image_path"]
    if not image_path.exists():
        return "missing_image"

    image_url, sha256_hash, ahash = meme_store.save_image_bytes_supabase(
        meme_id=meme_id,
        image_bytes=image_path.read_bytes(),
        original_filename=image_path.name,
    )

    meme_store.supabase_request(
        "POST",
        "/rest/v1/memes",
        headers={
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={
            "id": meme_id,
            "title": row["title"],
            "phrase": row["phrase"],
            "tags": row["tags"],
            "note": row["note"],
            "image_url": image_url,
            "source_url": row["source_url"],
            "image_sha256": sha256_hash,
            "image_ahash": ahash,
            "created_at": row["created_at"],
        },
    )
    return "migrated"


def main():
    meme_store.require_supabase_config()
    rows = load_sqlite_memes()
    counts = {"migrated": 0, "skipped": 0, "missing_image": 0, "failed": 0}

    for row in rows:
        try:
            result = migrate_one(row)
        except Exception as error:
            counts["failed"] += 1
            print(f"FAILED {row['id']} {row['title']}: {error}")
            continue

        counts[result] += 1
        print(f"{result.upper()} {row['id']} {row['title']}")

    print("SUMMARY", counts)


if __name__ == "__main__":
    main()
