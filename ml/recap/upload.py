"""
Save a finished recap to Supabase (SIG-73).

Uploads the mp4 to the private `recaps` bucket at <user_id>/<date>/recap.mp4 (overwriting any
older version) and makes sure the `recaps` table has exactly one row for that user and day.

    python upload.py USER_ID 2026-11-06 recap.mp4

Needs ml/recap/.env (never commit it):
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_KEY=<the secret / service_role key; row-level security blocks the anon key>
"""

import argparse
import os
import sys
from datetime import date as Date
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

HERE = Path(__file__).resolve().parent
BUCKET = "recaps"


def connect():
    """Supabase client from the URL and key in .env."""
    load_dotenv(HERE / ".env")
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY. Put them in ml/recap/.env")
    return create_client(url, key)


def save_recap(user_id, date, mp4_path, sb=None):
    """Uploads the recap and records it. Returns the storage path."""
    sb = sb or connect()
    day = Date.fromisoformat(str(date)).isoformat()      # rejects anything that isn't YYYY-MM-DD
    mp4 = Path(mp4_path)
    if not mp4.is_file():
        raise FileNotFoundError(f"No such file: {mp4}")
    storage_path = f"{user_id}/{day}/recap.mp4"

    # 1. Upload. "upsert" overwrites the old recap if this day was already made once.
    sb.storage.from_(BUCKET).upload(storage_path, str(mp4),
                                    {"content-type": "video/mp4", "upsert": "true"})

    # 2. One row per user per day. The table has no unique constraint on (user_id, date),
    #    so look for an existing row first: update it if found, otherwise insert a new one.
    found = (sb.table("recaps").select("id").eq("user_id", user_id).eq("date", day)
             .execute().data)
    if found:
        sb.table("recaps").update({"storage_path": storage_path}).eq("id", found[0]["id"]).execute()
    else:
        res = sb.table("recaps").insert({"user_id": user_id, "date": day,
                                         "storage_path": storage_path}).execute()
        if not res.data:
            raise PermissionError("Supabase inserted 0 rows: use the secret/service_role key in .env.")
    return storage_path


def signed_url(storage_path, seconds=3600, sb=None):
    """A temporary link that plays the private video in a browser."""
    sb = sb or connect()
    res = sb.storage.from_(BUCKET).create_signed_url(storage_path, seconds)
    return res.get("signedURL") or res.get("signedUrl")    # the key name differs between versions


def main():
    ap = argparse.ArgumentParser(description="Save a finished recap to Supabase (SIG-73)")
    ap.add_argument("user_id", help="the user's id from Supabase Auth")
    ap.add_argument("date", help="the day of the recap, YYYY-MM-DD")
    ap.add_argument("mp4", help="path to the finished recap.mp4")
    args = ap.parse_args()

    sb = connect()
    path = save_recap(args.user_id, args.date, args.mp4, sb=sb)
    print(f"Uploaded to {BUCKET}/{path}")
    print(f"Plays for 1 hour at:\n{signed_url(path, sb=sb)}")


if __name__ == "__main__":
    main()