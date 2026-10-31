# Sightline

An app that captures your day, and at the end of the day, turns it into 60-second, watchable recap.

## Repository structure

```
Sightline/
├── ios/        iOS app (capture, recap playback, calendar, settings)
├── backend/    API + processing for uploads, clip selection, recap generation
├── ml/         Scoring models + evaluation pipeline
└── docs/       Architecture, API reference, roadmap
```

Each subteam owns and documents its own folder — see the README inside
`ios/`, `backend/`, and `ml/`.

## Running locally

The backend runs in Docker with Python 3.11 and FFmpeg included. You do not
need to install Python, FFmpeg, or Python packages on your laptop.

1. Install and start [Docker Desktop](https://docs.docker.com/get-started/get-docker/).
   On Windows, use the WSL 2 backend and Linux containers. Complete any required
   restart before continuing.
2. Clone the repository (or extract the source ZIP), then open a terminal in
   the repository root: the folder containing `docker-compose.yml`.
3. Copy `.env.example` to `.env` in that folder:

   **Windows PowerShell:**

   ```powershell
   Copy-Item .env.example .env
   ```

   **macOS / Linux:**

   ```sh
   cp .env.example .env
   ```

   The starter app can run with blank values now.
   Before using the chunk endpoints:
       - fill in SUPABASE_URL
       - fill in SUPABASE_KEY
      in your local `.env` file.
   Never commit `.env`; it is already listed in `.gitignore`.
5. Start the backend:

   ```sh
   docker compose up
   ```

   The first run builds the image and downloads its dependencies, which can
   take several minutes and requires internet access. Wait for
   `Application startup complete` in the logs.
6. Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive
   API documentation. The root endpoint is [http://localhost:8000/](http://localhost:8000/).

Stop the attached server with **Ctrl+C**. To remove the project's stopped
containers and network, run `docker compose down` from the repository root.

After changing backend code or dependencies, rebuild with:

```sh
docker compose up --build
```

The container uses a copy of the backend source, so edits are picked up on
rebuild. To run in the background, use `docker compose up -d`; inspect its
status with `docker compose ps` and its logs with `docker compose logs api`.

If startup fails, check that Docker Desktop is running, the root `.env` file
exists, and port 8000 is free. The API is exposed only on your laptop's
loopback address.

### Teammate verification

 - confirm that `/docs` opens,
 -  `GET /` returns the welcome message
 -  request can be executed using **Try it out** in the docs.
Send screenshot to ruthvik102008@gmail.com or text me 2096655056.
