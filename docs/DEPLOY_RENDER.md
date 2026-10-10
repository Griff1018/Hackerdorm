# Deploy BizFlow on Render

One Docker web service runs the console server **and** the CodeBuddy CLI it drives. The CLI is never exposed
on its own port — only the console is public, behind a password.

## What you need
- The repo pushed to GitHub (Render deploys from it).
- A **CodeBuddy API key** (from the CodeBuddy / WorkBuddy site you log in to). China or enterprise (iOA) keys also
  need `CODEBUDDY_INTERNET_ENVIRONMENT` set as the CodeBuddy docs describe.
- A Render account with a payment method (the `starter` plan + 1 GB disk; free instances sleep and lose data).

## Steps
1. Commit and push: `Dockerfile`, `.dockerignore`, `.gitattributes`, `render.yaml`, `deploy/start.sh`, `console/server.py`.
2. Render Dashboard → **New → Blueprint** → connect GitHub → pick this repo → Render reads `render.yaml`.
3. When asked, fill in:
   - `CODEBUDDY_API_KEY` — your key.
   - `BIZFLOW_PASSWORD` — the password for opening the console (share it only with your team/judges).
4. **Apply**. The first build takes a few minutes (installs Node + the CodeBuddy CLI).
5. Open `https://<service>.onrender.com`. The browser asks for a login: any username, your `BIZFLOW_PASSWORD`.
6. Check the dot next to "BizFlow" is green (CLI found) and send a chat message.

## Settings (environment variables)
| variable | meaning |
|---|---|
| `CODEBUDDY_API_KEY` | CLI login (secret) |
| `BIZFLOW_PASSWORD` | console password; empty = no login (local use only) |
| `DATA_DIR` | persistent disk mount; `data/` is kept there (`/var/data`) |
| `PORT` | set by Render |
| `BIZFLOW_HOST` | `0.0.0.0` in the image (local default `127.0.0.1`) |

## Notes
- The disk keeps `data/` across restarts and redeploys. It is seeded from the repo on the **first** boot only — later
  changes to committed files in `data/` are not copied over. To start fresh, use "Reset demo data" in the console or
  delete `/var/data/data` from the Render shell and restart.
- Logs: Render → service → **Logs**. The first line shows `WorkBuddy CLI: …` and `login ON`.
- Health check: `/healthz` (no password needed).
