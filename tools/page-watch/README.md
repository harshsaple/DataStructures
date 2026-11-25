# page-watch

Small scheduled job that reads a page, counts items per section, and sends a push notification through [ntfy](https://ntfy.sh) when something new shows up. Identical results are not re-sent.

Runs from `.github/workflows/page-watch.yml` every ~5 minutes. Everything specific is configured through repository secrets — either one `CONFIG` secret holding a JSON object with the keys below, or the keys as separate secrets:

| Secret | Purpose |
| --- | --- |
| `NTFY_TOPIC` | ntfy topic to push to |
| `TARGET_URL` | page to read |
| `CLICK_URL` | link opened when tapping the notification |
| `SECTIONS` | comma-separated section names to look for |
| `LABELS` | two comma-separated labels (type A, type B) as written on the page |
| `NAMES` | two comma-separated names to show in alerts |
| `ANCHOR` | optional text marking where the relevant part of the page starts |

Type B results are sent as urgent; type A only as normal priority.
