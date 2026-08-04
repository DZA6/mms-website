#!/usr/bin/env python3
"""
MMS Deploy Worker — keeps the live site in sync with GitHub automatically.

Runs as a PythonAnywhere always-on task (or any long-running process).
Every POLL_INTERVAL seconds it:
  1. Asks GitHub for the latest commit SHA on the repo's default branch
  2. Compares it to the last SHA it deployed
  3. If new: git pull → pip install (if requirements changed) →
     migrate → collectstatic → reload the web app (PA API) → log it

Fails loud (logs every step) but never exits: a network blip or GitHub
rate-limit just means it tries again next cycle.

Usage:
    python3 deploy_worker.py [--once] [--poll 300] [--repo DZA6/mms-website]

Environment variables (optional):
    PA_API_TOKEN   PythonAnywhere API token (for auto-reload; skips reload if unset)
    PA_USERNAME    PythonAnywhere username (for auto-reload)
    PA_DOMAIN      web app domain, e.g. www.memorialmediaservices.org
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

DEFAULT_REPO = "DZA6/mms-website"
DEFAULT_POLL = 300  # seconds

# Where we remember the last deployed SHA (persists across restarts)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".deploy_state.json")


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run(cmd, cwd=None, timeout=300):
    """Run a shell command, return (exit_code, output)."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip() + ("\n" + p.stderr if p.stderr and p.stderr.strip() else "").strip()
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s: {cmd}"
    except Exception as e:
        return 1, f"ERROR: {e}"


def find_python(workdir):
    """Prefer the site's virtualenv Python; fall back to any python3."""
    # Common venv locations
    candidates = [
        os.path.join(workdir, "venv/bin/python"),
        os.path.join(workdir, ".venv/bin/python"),
        os.path.expanduser("~/.virtualenvs/*/bin/python"),
    ]
    import glob
    expanded = []
    for c in candidates:
        if "*" in c:
            expanded.extend(glob.glob(c))
        else:
            expanded.append(c)
    for c in expanded:
        if os.path.exists(c):
            return c
    return "python3"


def github_latest_sha(repo, token=None):
    """Get the latest commit SHA on the default branch via the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/commits?per_page=1"
    req = urllib.request.Request(url, headers={"User-Agent": "mms-deploy-worker", "Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    if not data:
        raise RuntimeError("GitHub returned an empty commit list")
    return data[0]["sha"]


def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"deployed_sha": None}


def write_state(sha):
    with open(STATE_FILE, "w") as f:
        json.dump({"deployed_sha": sha, "updated_at": datetime.now().isoformat()}, f)


def reload_pythonanywhere(api_token, username, domain):
    """Trigger a PythonAnywhere web app reload via their REST API."""
    url = f"https://www.pythonanywhere.com/api/v0/user/{username}/webapps/{domain}/reload/"
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Token {api_token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return body


def deploy(repo, workdir, pa_api_token, pa_username, pa_domain):
    """Pull and apply the latest changes. Returns True if anything deployed."""
    # 1. Fetch latest remote SHA
    try:
        sha = github_latest_sha(repo)
    except Exception as e:
        log(f"⚠️  Could not reach GitHub ({e}) — will retry next cycle.")
        return False

    state = read_state()
    if state.get("deployed_sha") == sha:
        return False  # Already current

    log(f"🚀 New commit detected: {sha[:10]} (was {str(state.get('deployed_sha'))[:10]})")

    # 2. git pull
    code, out = run("git pull --ff-only origin main", cwd=workdir)
    if code != 0:
        log(f"❌ git pull failed:\n{out}\nRetrying next cycle (SHA not recorded).")
        return False
    log(f"✅ git pull ok")

    # 3. Check if requirements changed → pip install
    py = find_python(workdir)
    log(f"(using Python: {py})")
    code, out = run("git diff HEAD@{1} HEAD --name-only | grep -q requirements.txt", cwd=workdir)
    if code == 0:
        log("📦 requirements.txt changed — installing deps")
        pip = os.path.join(os.path.dirname(py), "pip") if py != "python3" else "pip3"
        code, out = run(f"{pip} install -r requirements.txt", cwd=workdir, timeout=600)
        if code != 0:
            log(f"⚠️  pip install had issues (continuing anyway):\n{out[-500:]}")
        else:
            log("✅ deps installed")
    else:
        log("(requirements.txt unchanged — skipping pip)")

    # 4. migrate
    code, out = run(f"{py} manage.py migrate --noinput", cwd=workdir, timeout=300)
    if code != 0:
        log(f"⚠️  migrate warnings/errors (continuing):\n{out[-500:]}")
    else:
        log("✅ migrations applied")

    # 5. collectstatic
    code, out = run(f"{py} manage.py collectstatic --noinput", cwd=workdir, timeout=300)
    if code != 0:
        log(f"⚠️  collectstatic issues (continuing):\n{out[-500:]}")
    else:
        log("✅ static files collected")

    # 6. Reload web app (only if API creds given)
    if pa_api_token and pa_username and pa_domain:
        try:
            body = reload_pythonanywhere(pa_api_token, pa_username, pa_domain)
            log(f"✅ web app reloaded: {body[:100]}")
        except Exception as e:
            log(f"⚠️  web app reload failed ({e}) — you may need to reload manually")
    else:
        log("ℹ️  PA_API_TOKEN not set — skip auto-reload (site code is updated, reload manually)")

    # 7. Record the SHA only after success
    write_state(sha)
    log(f"🏁 Deploy complete — recorded {sha[:10]}")
    return True


def main():
    ap = argparse.ArgumentParser(description="MMS auto-deploy worker")
    ap.add_argument("--once", action="store_true", help="Run one cycle and exit (for cron/testing)")
    ap.add_argument("--poll", type=int, default=int(os.environ.get("POLL_SECONDS", DEFAULT_POLL)))
    ap.add_argument("--repo", default=os.environ.get("REPO", DEFAULT_REPO))
    ap.add_argument("--workdir", default=os.environ.get("WORKDIR", os.path.expanduser("~/mms-website")))
    args = ap.parse_args()

    workdir = os.path.expanduser(args.workdir)
    if not os.path.isdir(os.path.join(workdir, ".git")):
        log(f"❌ {workdir} is not a git repo. Point --workdir at the site directory.")
        sys.exit(1)

    pa_api_token = os.environ.get("PA_API_TOKEN", "")
    pa_username = os.environ.get("PA_USERNAME", "")
    pa_domain = os.environ.get("PA_DOMAIN", "")

    log(f"🟢 Deploy worker started — repo={args.repo} workdir={workdir} poll={args.poll}s")
    if args.once:
        deployed = deploy(args.repo, workdir, pa_api_token, pa_username, pa_domain)
        log("(one-shot mode: done)" if not deployed else "(one-shot mode: deployed)")
        return

    # Forever loop
    while True:
        try:
            deploy(args.repo, workdir, pa_api_token, pa_username, pa_domain)
        except Exception as e:
            log(f"⚠️  unexpected error: {e}")
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
