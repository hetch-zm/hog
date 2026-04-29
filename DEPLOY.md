# Deployment

## Local

```
pip install -r requirements.txt
python payroll/app.py
```

Open http://127.0.0.1:5000 — the HOG site.
Click **Staff Portal** in the nav (or go to /payroll) for the payroll system.

## Move from Vercel to Render

The current Vercel deployment serves only the static HOG pages. Once you
add the payroll, you need a host that runs Python AND has persistent disk
(for SQLite, uploaded Excel files, generated PDFs). Render fits.

### One-time setup on Render

1. Push this repo to GitHub.
2. In Render: **New → Blueprint** and point at the repo. Render reads
   `render.yaml` and provisions:
   - a Python web service running `gunicorn payroll.app:app`
   - a 1 GB persistent disk mounted at `/var/data` (DB + uploads + payslips)
   - `SECRET_KEY` auto-generated, `PAYROLL_DATA_DIR=/var/data`
3. First deploy gives you `https://hope-of-glory.onrender.com`.
4. (Optional) Add the custom domain in Render → Settings → Custom Domains,
   then update the DNS CNAME from Vercel to Render. Remove the Vercel
   project once DNS has propagated.

### What changes vs. Vercel

| Concern        | Vercel (now)             | Render (after)              |
|----------------|--------------------------|-----------------------------|
| Static HOG site| Edge CDN, instant        | Served by gunicorn (fine)   |
| Payroll        | Not possible (no disk)   | Works, data persists        |
| Cold start     | None                     | ~30s on Starter free tier   |
| Cost           | Free                     | $7/mo Starter (or free w/ spin-down) |

### Free tier caveat

Render's free web service spins down after 15 min idle and takes ~30s
to wake. For internal payroll use, that's usually fine. If you need
always-on, use the $7/mo Starter plan (set `plan: starter` in
`render.yaml`, already configured).

### Backups

The SQLite DB lives at `/var/data/payroll.db`. To back up:
- Render dashboard → Disk → Snapshot, or
- `render disk download` via Render CLI, or
- add a scheduled job that copies the DB to S3/GCS.
