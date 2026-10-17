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
