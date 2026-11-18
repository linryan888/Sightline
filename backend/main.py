import os
import shutil
import tempfile
from dotenv import load_dotenv
from supabase import create_client
from fastapi import FastAPI, status, Depends
from auth import make_current_user_dependency
from windows import get_duration, make_windows, save_windows
from datetime import date
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

# Create a simple GET endpoint (Root)
@app.get("/")
def read_root():
    return {"message": "Welcome to your FastAPI backend!"}

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

# Retrieve a single chunk and its scoring progress
@app.get("/chunks/{chunk_id}")
def get_chunk(
    chunk_id: UUID,
    user_id: str = Depends(get_current_user)
):
    try:
        # Find the chunk and verify that it belongs to this user
        result = (
            supabase.table("chunks")
            .select("*")
            .eq("id", str(chunk_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Chunk not found"
            )

        chunk = result.data[0]

        # Retrieve windows associated with this chunk
        windows_result = (
            supabase.table("windows")
            .select("score")
            .eq("chunk_id", str(chunk_id))
            .execute()
        )

        windows = windows_result.data or []

        total_windows = len(windows)

        # A score of 0 is valid; only None means unscored
        scored_windows = sum(
            1 for window in windows
            if window["score"] is not None
        )

        return {
            "chunk": chunk,
            "total_windows": total_windows,
            "scored_windows": scored_windows
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Chunk Retrieval Error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve chunk progress"
        ) from e


# Count how many of a user's chunks are in each pipeline status
@app.get("/pipeline/status")
def get_pipeline_status(
    date: date,
    user_id: str = Depends(get_current_user)
):
    # Every possible pipeline status
    statuses = [
        "uploaded",
        "split",
        "split_failed",
        "scored",
        "recap_ready"
    ]

    try:
        # Retrieve the statuses for this user's chunks on this date
        result = (
            supabase.table("chunks")
            .select("status")
            .eq("user_id", user_id)
            .eq("date", date.isoformat())
            .execute()
        )

        # Start every count at zero
        counts = {status: 0 for status in statuses}

        # Count each chunk according to its status
        for chunk in result.data:
            chunk_status = chunk["status"]
            if chunk_status in counts:
                counts[chunk_status] += 1

        return {
            "date": date.isoformat(),
            "counts": counts
        }

    except Exception as e:
        print(f"Pipeline Status Error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve pipeline status"
        ) from e
