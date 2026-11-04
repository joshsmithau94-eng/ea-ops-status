#!/usr/bin/env python3
"""Generate status.json from gh PRs + bots.json. stdlib only, no LLM.

status.json is public. Output must contain only sanitized, non-identifying
fields: no titles, URLs, authors, labels, branch names, or links.
"""
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone

REPO = os.environ.get("EA_REPO", "")
JOSH_LOGIN = "joshsmithau94-eng"
BOTS_PATH = os.environ.get("BOTS_PATH", "bots-src/bots.json")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status.json")

FIELDS = "number,title,url,author,labels,reviewDecision,reviewRequests,headRefOid,isDraft,updatedAt"

LABEL_RE = re.compile(r"[^a-z0-9:_-]+")
ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)
URL_OR_PATH_RE = re.compile(r"(https?://\S+|/\S*/\S*)", re.IGNORECASE)


def sanitize_label(value, max_len):
    text = str(value or "").lower()
    text = LABEL_RE.sub("", text)
    return text[:max_len]


def sanitize_job(value, max_len=60):
    text = str(value or "")
    text = URL_OR_PATH_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def sanitize_since(value):
    text = str(value or "")
    return text if ISO_DATETIME_RE.match(text) else ""


def run_gh(errors):
    if not REPO:
        errors.append("EA_REPO not set")
        return []
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "-R", REPO, "--state", "open", "--json", FIELDS],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return json.loads(out.stdout)
    except subprocess.CalledProcessError as e:
        errors.append(f"gh pr list failed: {e.stderr.strip() or e}")
    except subprocess.TimeoutExpired:
        errors.append("gh pr list timed out")
    except json.JSONDecodeError as e:
        errors.append(f"gh pr list returned invalid JSON: {e}")
    except FileNotFoundError:
        errors.append("gh CLI not found")
    return []


def gh_api(path, errors):
    try:
        out = subprocess.run(["gh", "api", path], capture_output=True, text=True,
                             timeout=60, check=True)
        return json.loads(out.stdout)
    except subprocess.CalledProcessError:
        errors.append("gh api failed")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        errors.append("gh api error")
    return None


def compute_ci(sha, errors):
    """CI from commit statuses + workflow runs for the head sha (no Checks API)."""
    if not sha or not REPO:
        return "none"
    states = []
    combined = gh_api(f"repos/{REPO}/commits/{sha}/status", errors)
    if isinstance(combined, dict):
        for st in combined.get("statuses") or []:
            states.append((st.get("state") or "").lower())
    runs = gh_api(f"repos/{REPO}/actions/runs?head_sha={sha}&per_page=100", errors)
    if isinstance(runs, dict):
        for r in runs.get("workflow_runs") or []:
            if r.get("status") != "completed":
                states.append("pending")
            else:
                c = (r.get("conclusion") or "").lower()
                if c in ("success", "skipped", "neutral"):
                    states.append("success")
                elif c in ("failure", "cancelled", "timed_out", "startup_failure", "action_required"):
                    states.append("failure")
                else:
                    states.append("pending")
    if not states:
        return "none"
    if any(s in ("failure", "error") for s in states):
        return "failure"
    if any(s != "success" for s in states):
        return "pending"
    return "success"


def compute_qa(labels):
    for label in labels:
        name = (label.get("name") or "").lower()
        if name.startswith("qa"):
            return name
    return "none"


def compute_review_needed(labels, review_requests, review_decision):
    for label in labels:
        name = (label.get("name") or "").lower()
        if "josh" in name or "needs-review" in name:
            return True
    for req in review_requests or []:
        login = (req.get("login") or "").lower()
        if login == JOSH_LOGIN:
            return True
    if review_decision == "REVIEW_REQUIRED":
        return True
    return False


def load_bots(errors):
    try:
        with open(BOTS_PATH) as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("bots.json is not a list")
        return data
    except FileNotFoundError:
        errors.append(f"{BOTS_PATH} not found")
    except (json.JSONDecodeError, ValueError) as e:
        errors.append(f"{BOTS_PATH} invalid: {e}")
    return []


def main():
    errors = []
    raw_prs = run_gh(errors)

    prs = []
    for pr in raw_prs:
        labels = pr.get("labels") or []
        review_requests = pr.get("reviewRequests") or []
        review_decision = pr.get("reviewDecision")
        prs.append({
            "number": pr.get("number"),
            "ci": compute_ci(pr.get("headRefOid"), errors),
            "qa": sanitize_label(compute_qa(labels), 30),
            "review_needed": compute_review_needed(labels, review_requests, review_decision),
        })

    raw_bots = load_bots(errors)
    bots = []
    for b in raw_bots:
        if not isinstance(b, dict):
            continue
        bots.append({
            "bot": sanitize_label(b.get("bot"), 40),
            "state": sanitize_label(b.get("state"), 40),
            "job": sanitize_job(b.get("job")),
            "since": sanitize_since(b.get("since")),
        })

    status = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prs": prs,
        "bots": bots,
        "error_count": len(errors),
    }

    old_status = None
    try:
        with open(OUT_PATH) as f:
            old_status = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if isinstance(old_status, dict):
        comparable_old = {k: v for k, v in old_status.items() if k != "generated_at"}
        comparable_new = {k: v for k, v in status.items() if k != "generated_at"}
        if comparable_old == comparable_new:
            print("unchanged")
            return

    dir_name = os.path.dirname(OUT_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".status.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(status, f, indent=2)
        os.replace(tmp_path, OUT_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    print("changed")


if __name__ == "__main__":
    main()
