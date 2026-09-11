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
