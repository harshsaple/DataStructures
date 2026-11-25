# page-watch

Small scheduled job that reads several pages of sightings and sends a push notification through [ntfy](https://ntfy.sh) for matching records seen in the last few minutes. Each record is alerted on once.

Runs from `.github/workflows/page-watch.yml` every ~5 minutes. Configuration lives in a `CONFIG` repository secret (JSON); the keys are documented at the top of `check.py`.
