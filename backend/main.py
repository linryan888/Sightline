import os
import shutil
import tempfile
from calendar import monthrange
from dotenv import load_dotenv
from supabase import create_client
from fastapi import FastAPI, status, Depends, Query
from auth import make_current_user_dependency
from windows import get_duration, make_windows, save_windows
from pydantic import BaseModel
from datetime import date, datetime
from uuid import UUID, uuid4
from pathlib import Path
from fastapi import UploadFile, File, Form, HTTPException

# 1. Initialize the FastAPI app
app = FastAPI()

# Load Supabase credentials from the local .env file
load_dotenv()

# Create the Supabase client for Storage and database operations
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"]
)
get_current_user = make_current_user_dependency(supabase)

# 2. Define a Pydantic model for data validation (for POST/PUT requests)
class Item(BaseModel):
    name: str
    price: float
    description: str | None = None

# 3. Create a simple GET endpoint (Root)
@app.get("/")
def read_root():
    return {"message": "Welcome to your FastAPI backend!"}

# 4. Create a GET endpoint with a path parameter
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "query_parameter": q}

# 5. Create a POST endpoint that accepts JSON data matching the Item model
@app.post("/items/", status_code=status.HTTP_201_CREATED)
def create_item(item: Item):
    return {"message": "Item created successfully", "data": item}

# --- SightLine video chunk endpoints ---

WINDOW_SECONDS = 5

def update_chunk(chunk_id, values):
    return supabase.table("chunks").update(values).eq("id", chunk_id).execute().data

# Create a chunk's window rows and return the updated chunk record.
# Errors are logged rather than raised so a failed split never loses the upload.
def split_chunk(chunk_id, video_file):
    temp_path = None
    try:
        # ffprobe needs a real file on disk
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            video_file.seek(0)
            shutil.copyfileobj(video_file, temp_file)

        duration = get_duration(temp_path)
        windows = make_windows(duration, window_size=WINDOW_SECONDS)
        if not windows:
            raise ValueError(f"No windows for duration {duration}")

        save_windows(chunk_id, windows, supabase)
        return update_chunk(chunk_id, {
            "duration_seconds": duration,
            "status": "split"
        })
    except Exception as e:
        print(f"Chunk Split Error ({chunk_id}): {type(e).__name__}: {e}")

        try:
            return update_chunk(chunk_id, {"status": "split_failed"})
        except Exception as update_error:
            print(
                f"Chunk Status Error ({chunk_id}): "
                f"{type(update_error).__name__}: {update_error}"
            )
            return None
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

# Upload a video chunk, save its metadata to Supabase, and create its windows
@app.post("/chunks/upload", status_code=201)
def upload_chunk(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
    date: date = Form(...)
):
    # 1. Create a unique filename
    filename = f"{uuid4().hex}_{Path(file.filename or 'video.mp4').name}"

    # 2. Construct the Supabase Storage path
    storage_path = f"{user_id}/{date.isoformat()}/{filename}"

    # 3. Upload the video to Supabase Storage
    try:
        supabase.storage.from_("footage").upload(
            path=storage_path,
            file=file.file.read(),
            file_options={
                "content-type": file.content_type or "application/octet-stream"
            }
        )
    except Exception as e:
        print(f"Supabase Storage Error: {type(e).__name__}: {e}")

        raise HTTPException(
            status_code=502,
            detail="Failed to upload video to storage"
        ) from e

    # 4. Insert the video's metadata into the database
    try:
        result = (
            supabase.table("chunks")
            .insert({
                "user_id": str(user_id),
                "date": date.isoformat(),
                "storage_path": storage_path
            })
            .execute()
        )
    except Exception:
        # Remove the uploaded file if the database insert fails
        try:
            supabase.storage.from_("footage").remove([storage_path])
        except Exception:
            pass

        raise HTTPException(
            status_code=502,
            detail="Failed to save chunk metadata"
        )

    # 5. Split the video into windows and record the outcome on the chunk
    updated_chunk = split_chunk(result.data[0]["id"], file.file)

    # 6. Return the database record
    return {
        "message": "Video uploaded successfully",
        "chunk": updated_chunk or result.data
    }

# Retrieve all video chunks for a specific user and date
@app.get("/chunks")
def get_chunks(
    date: date,
    user_id: str = Depends(get_current_user)
):
    try:
        # Filter chunks by both user ID and date
        result = (
            supabase.table("chunks")
            .select("*")
            .eq("user_id", str(user_id))
            .eq("date", date.isoformat())
            .execute()
        )

        # Return the matching chunk records
        return {"chunks": result.data}

    except Exception as e:
        print(f"Supabase Database Error: {type(e).__name__}: {e}")

        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve video chunks"
        ) from e


class Recap(BaseModel):
    date: date
    url: str
    created_at: datetime


@app.get("/recaps", response_model=Recap)
def get_recap(date: date, user_id: str = Depends(get_current_user)):
    try:
        # The schema permits duplicates; use the newest recap for this day.
        rows = (supabase.table("recaps")
                .select("date,storage_path,created_at")
                .eq("user_id", user_id).eq("date", date.isoformat())
                .order("created_at", desc=True).limit(1).execute().data)
    except Exception as e:
        raise HTTPException(502, "Failed to retrieve recap") from e

    if not rows:
        raise HTTPException(404, f"No recap available for {date.isoformat()} yet")

    row = rows[0]
    try:
        signed = supabase.storage.from_("recaps").create_signed_url(
            row["storage_path"], 3600
        )
        url = signed.get("signedURL") or signed.get("signedUrl")
        if not url:
            raise ValueError("Storage returned no signed URL")
    except Exception as e:
        raise HTTPException(502, "Failed to create recap playback URL") from e

    return {"date": row["date"], "url": url, "created_at": row["created_at"]}


@app.get("/recaps/days", response_model=dict[str, list[date]])
def get_recap_days(
    month: str = Query(..., pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
    user_id: str = Depends(get_current_user)
):
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError as e:
        raise HTTPException(422, "month must be a valid YYYY-MM") from e
    last = first.replace(day=monthrange(first.year, first.month)[1])
    try:
        rows = (supabase.table("recaps").select("date")
                .eq("user_id", user_id)
                .gte("date", first.isoformat()).lte("date", last.isoformat())
                .execute().data)
    except Exception as e:
        raise HTTPException(502, "Failed to retrieve recap days") from e
    return {"dates": sorted({row["date"] for row in rows})}
