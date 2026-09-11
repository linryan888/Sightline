# Sightline

Smart glasses that continuously capture your day, paired with an app that
turns that footage into a short, watchable recap.

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

## License

[MIT](LICENSE)
