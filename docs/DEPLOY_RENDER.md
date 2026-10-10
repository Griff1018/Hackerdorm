# Deploy Enterprise Buddy on Render

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
   - `ENTERPRISE_BUDDY_PASSWORD` — the password for opening the console (share it only with your team/judges).
4. **Apply**. The first build takes a few minutes (installs Node + the CodeBuddy CLI).
5. Open `https://<service>.onrender.com`. The browser asks for a login: any username, your `ENTERPRISE_BUDDY_PASSWORD`.
6. Check the dot next to "Enterprise Buddy" is green (CLI found) and send a chat message.

## Settings (environment variables)
| variable | meaning |
|---|---|
| `CODEBUDDY_API_KEY` | CLI login (secret) |
| `ENTERPRISE_BUDDY_PASSWORD` | console password; empty = no login (local use only) |
| `DATA_DIR` | persistent disk mount; `data/` is kept there (`/var/data`) |
| `PORT` | set by Render |
| `ENTERPRISE_BUDDY_HOST` | `0.0.0.0` in the image (local default `127.0.0.1`) |

## Free instance instead of Starter
- Pick the **Free** instance, add **no disk**, and **do not set `DATA_DIR`**.
- The server pings its own `RENDER_EXTERNAL_URL/healthz` every 10 minutes (Render sets that variable), so the instance
  does not fall asleep and auto-reply, the daily list and automations keep running. `ENTERPRISE_BUDDY_KEEPALIVE=0` turns it off.
- Free has no persistent disk: chats, orders and plans reset to the repo's demo data on every deploy or restart.
- 0.1 CPU makes page loads and tool runs slower; the agent itself mostly waits on the CodeBuddy API.

## Notes
- The disk keeps `data/` across restarts and redeploys. It is seeded from the repo on the **first** boot only — later
  changes to committed files in `data/` are not copied over. To start fresh, use "Reset demo data" in the console or
  delete `/var/data/data` from the Render shell and restart.
- Logs: Render → service → **Logs**. The first line shows `WorkBuddy CLI: …` and `login ON`.
- Health check: `/healthz` (no password needed).
