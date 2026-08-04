# MMS Deploy Worker — Auto-Deploy Setup

This worker keeps the live site in sync with GitHub automatically. It runs on
PythonAnywhere as an always-on task (or any long-running process).

## What it does (every 5 minutes by default)

1. Asks GitHub for the latest commit on `main`
2. If it's new vs. the last deployed SHA (stored in `.deploy_state.json`):
   - `git pull --ff-only origin main`
   - `pip install -r requirements.txt` (only if requirements.txt changed)
   - `python manage.py migrate --noinput`
   - `python manage.py collectstatic --noinput`
   - Reloads the web app (if PA API token provided)
3. Logs every step; never exits — retries next cycle on any failure

## Setup on PythonAnywhere

### 1. Put the worker in the site directory

The script is already in the repo (`deploy_worker.py`) — it comes down with
`git pull`. Ensure the site's virtualenv is at one of:
`venv/bin/python`, `.venv/bin/python`, or `~/.virtualenvs/<name>/bin/python`
(it auto-detects).

### 2. Create the always-on task

- PythonAnywhere → **Tasks** tab → **Always-on tasks**
- "New task" → command:
  ```
  cd ~/mms-website && python3 deploy_worker.py
  ```
  (adjust `~/mms-website` to your site's actual path)
- Start it. Logs appear in the task's console (also printed to stdout).

### 3. Optional: auto-reload the web app (recommended)

Without this, the worker updates code/DB/static but you still have to click
**Reload** on the Web tab. To automate it:

1. Get an API token: PythonAnywhere → **Account** → **API token**
2. Run the worker with env vars:
   ```
   cd ~/mms-website && PA_API_TOKEN=<your-token> PA_USERNAME=<your-username> PA_DOMAIN=www.memorialmediaservices.org python3 deploy_worker.py
   ```

### 4. Alternative: cron instead of always-on

If you'd rather not run a forever-process, use a scheduled task every 10
minutes:
```
cd ~/mms-website && python3 deploy_worker.py --once
```
Same effect (polling every 10 min instead of every 5).

## Testing locally

```bash
python3 deploy_worker.py --once --workdir ~/memorial-site/my_website
```

## Notes

- `--poll N` changes the interval (default 300s). `POLL_SECONDS` env var works too.
- Repo defaults to `DZA6/mms-website`; override with `--repo` or `REPO`.
- The worker never force-pushes and only ever `pull --ff-only` — it cannot
  clobber local changes; if a pull conflicts it logs and retries next cycle.
- `.deploy_state.json` is gitignored (auto-add below).
