# Sightline Backend

API + worker: accepts uploaded footage, runs ML scoring, selects clips,
assembles recaps.

TODO: flesh out `main.py` into a proper FastAPI app package (routes, models,
schemas, services, worker).

## Running locally

Follow [Running locally in the root README](../README.md#running-locally).
Run Docker Compose from the repository root, one level above this folder.

`Dockerfile` packages the current `main:app` FastAPI starter with Python 3.11,
FFmpeg, and the dependencies in `requirements.txt`. The container runs Uvicorn
as an unprivileged user on port 8000. Compose passes the root `.env` file to
the API at runtime; secrets are excluded from the backend image.


## Run the backend

Install and start Docker Desktop. From the repository root—the folder containing `docker-compose.yml`—copy the environment template:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```sh
cp .env.example .env
```

Fill in `SUPABASE_URL` and `SUPABASE_KEY` in your local `.env`. Use the Project URL and server-side secret key from the same Supabase project. Never commit `.env` or share the key in screenshots.

Before testing, confirm:

- The tables defined in `backend/schema.sql` exist in Supabase.
- A private Storage bucket named `footage` exists.
- A test user exists under Supabase Authentication → Users.

The initial schema enables row-level security without client access policies. This development backend uses a server-side key; authentication and user authorization remain follow-up work.

Start the backend:

```sh
docker compose up --build
```

Wait for startup, then open http://127.0.0.1:8000/docs.

## Test video upload and retrieval

1. Expand `POST /chunks/upload` and click **Try it out**.
2. Select a small MP4 file.
3. Enter the UUID of an existing Supabase Auth test user and a date in `YYYY-MM-DD` format.
4. Click **Execute**. Expect HTTP **201**. Note the returned chunk `id`.
5. Expand `GET /chunks` and click **Try it out**.
6. Enter the same user ID and date, then click **Execute**.
7. Expect HTTP **200** and confirm the uploaded chunk's `id` appears in the response.

The upload creates a file in `footage` and a metadata row in `chunks`. Repeating the upload creates another record.

## Verification

The updated PR #5 code was built with Docker and tested against Supabase using a one-second MP4. Automated checks confirmed successful upload, retrieval, the metadata row, and that the stored video matched the original. Manual testing through `/docs` also confirmed that the uploaded chunk appeared in retrieval results.

A final fresh-clone check from `main` remains to be completed after merging.

## Stop the backend

Press **Ctrl+C**, then remove the stopped containers and network:

```sh
docker compose down
```
