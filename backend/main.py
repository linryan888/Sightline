import os
from dotenv import load_dotenv
from supabase import create_client
from fastapi import FastAPI, status
from pydantic import BaseModel
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

# Upload a video chunk and save its metadata to Supabase
@app.post("/chunks/upload", status_code=201)
def upload_chunk(
    file: UploadFile = File(...),
    user_id: UUID = Form(...),
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

    # 5. Return the newly created database record
    return {
        "message": "Video uploaded successfully",
        "chunk": result.data
    }

# Retrieve all video chunks for a specific user and date
@app.get("/chunks")
def get_chunks(
    user_id: UUID,
    date: date
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