"""repo_pulse logic: one call gathers a repo's recent activity and computes every number in code.

The LLM that writes the daily report only turns this JSON into text, so it never counts, sorts or
guesses. Everything here is plain GitHub REST (no MCP, no LLM) and testable with a fake client:
pass any object with ``get(path, params=None, headers=None) -> (json, headers)``.

Calls per run (default caps): 1 repo + ~1-3 stargazer pages + 5 searches + 1 per merged PR and
per reviewed PR (capped) + 1 releases + up to MAX_NEWCOMER_CHECKS searches. Search is limited to
30 requests a minute per token, so this stays well inside it for a daily run.
"""
from __future__ import annotations

import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

API = "https://api.github.com"
MAX_PRS = 30                 # merged / reviewed PRs we fetch reviews for
MAX_NEWCOMER_CHECKS = 10     # issue authors we check for "first issue in this repo"
STALE_REVIEW_DAYS = 5        # an open PR with no review for this long "needs attention"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BOTS = re.compile(r"\[bot\]$|^dependabot|^renovate|^github-actions", re.I)


# ── auth + client ───────────────────────────────────────────────────────────────────────────────
def github_token() -> str:
    """GITHUB_TOKEN from the tools' secret dir (a Code Engine secret mounted as files), else env."""
    d = os.environ.get("MCP_SECRETS_DIR", "")
    if d:
        p = Path(d) / "GITHUB_TOKEN"
        if p.is_file():
            return p.read_text().strip()
    return os.environ.get("GITHUB_TOKEN", "").strip()


class GitHub:
    """Minimal REST client: GET only (this tool never writes)."""

    def __init__(self, token: str | None = None, timeout: float = 20.0):
        tok = token if token is not None else github_token()
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
             "User-Agent": "cuga-apps-repo-pulse"}
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        self._c = httpx.Client(base_url=API, headers=h, timeout=timeout)

    def get(self, path: str, params: dict | None = None, headers: dict | None = None):
        # GitHub's search API has a per-minute limit and a burst ("secondary") limit, answered with 403
        # or 429. Wait and retry briefly (about 10 s in total, inside CUGA's tool timeout) rather than fail: a failed call leaves the
        # agent to improvise, and a POLL agent that improvises can emit a wrong change signal.
        waits = [3, 8]
        while True:
            r = self._c.get(path, params=params, headers=headers)
            limited = r.status_code == 429 or (
                r.status_code == 403 and ("rate limit" in r.text.lower() or r.headers.get("x-ratelimit-remaining") == "0"))
            if not limited or not waits:
                break
            time.sleep(min(int(r.headers.get("retry-after") or 0) or waits[0], 10))
            waits.pop(0)
        if limited:
            raise RuntimeError("GitHub rate limit reached; try again later")
        if r.status_code == 404:
            raise LookupError(f"not found: {path}")
        r.raise_for_status()
        return r.json(), r.headers


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────
def check_repo(repo: str) -> str:
    repo = (repo or "").strip().removeprefix("https://github.com/").strip("/")
    if not _REPO_RE.match(repo) or any(part in (".", "..") for part in repo.split("/")):
        raise ValueError(f"repo must look like owner/name, got {repo!r}")
    return repo


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _login(obj: dict | None) -> str:
    return ((obj or {}).get("user") or {}).get("login") or ""


def _is_bot(login: str) -> bool:
    return bool(_BOTS.search(login or ""))


def _search(gh, q: str, per_page: int = 100) -> tuple[int, list[dict]]:
    data, _ = gh.get("/search/issues", params={"q": q, "per_page": per_page, "sort": "created", "order": "desc"})
    return int(data.get("total_count", 0)), list(data.get("items") or [])


def _item(it: dict) -> dict:
    return {"number": it.get("number"), "title": it.get("title", ""), "author": _login(it),
            "url": it.get("html_url", ""), "author_association": it.get("author_association", "")}


# ── the pieces ──────────────────────────────────────────────────────────────────────────────────
def new_stars(gh, repo: str, total: int, since: datetime) -> list[dict]:
    """Stargazers newer than ``since``. GitHub lists them oldest first, so walk back from the last page."""
    if total <= 0:
        return []
    per = 100
    page = max(1, math.ceil(total / per))
    out: list[dict] = []
    while page >= 1:
        data, _ = gh.get(f"/repos/{repo}/stargazers", params={"per_page": per, "page": page},
                         headers={"Accept": "application/vnd.github.star+json"})
        older_seen = False
        for s in reversed(data or []):
            at = _ts(s.get("starred_at"))
            if at and at >= since:
                out.append({"user": (s.get("user") or {}).get("login", ""), "starred_at": s.get("starred_at")})
            else:
                older_seen = True
                break
        if older_seen or not data:
            break
        page -= 1
    return out


def reviews_for(gh, repo: str, number: int) -> list[dict]:
    data, _ = gh.get(f"/repos/{repo}/pulls/{number}/reviews", params={"per_page": 100})
    return list(data or [])


def is_first_issue(gh, repo: str, login: str, since: datetime) -> bool:
    """True when ``login`` opened no issue or PR in ``repo`` before ``since``."""
    n, _ = _search(gh, f"repo:{repo} author:{login} created:<{_iso(since)}", per_page=1)
    return n == 0


def daily_activity(gh, repo: str, hours: int = 24, now: datetime | None = None) -> dict[str, Any]:
    """Everything the daily report needs, computed in code. ``now`` is injectable for tests."""
    repo = check_repo(repo)
    if not 1 <= int(hours) <= 24 * 31:
        raise ValueError("hours must be between 1 and 744")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = now - timedelta(hours=int(hours))
    s = _iso(since)

    meta, _ = gh.get(f"/repos/{repo}")
    total_stars = int(meta.get("stargazers_count", 0))
    # Listing stargazers needs a token that may read them; some fine-grained tokens are refused (403)
    # while every other call works. Keep the report and say why the new-star count is missing.
    star_note = ""
    try:
        stars: list[dict] | None = new_stars(gh, repo, total_stars, since)
    except Exception as e:  # noqa: BLE001
        stars, star_note = None, f"new stars unavailable: {str(e)[:120]}"

    merged_n, merged = _search(gh, f"repo:{repo} is:pr is:merged merged:>={s}")
    opened_prs_n, opened_prs = _search(gh, f"repo:{repo} is:pr created:>={s}")
    opened_issues_n, opened_issues = _search(gh, f"repo:{repo} is:issue created:>={s}")
    closed_issues_n, _ = _search(gh, f"repo:{repo} is:issue is:closed closed:>={s}", per_page=1)
    stale_before = _iso(now - timedelta(days=STALE_REVIEW_DAYS))
    stale_n, stale = _search(gh, f"repo:{repo} is:pr is:open draft:false review:none created:<{stale_before}")

    # Reviews: who reviewed the merged PRs, and who reviewed anything in the window (top reviewer).
    _, touched = _search(gh, f"repo:{repo} is:pr updated:>={s}")
    review_counts: Counter[str] = Counter()
    reviewers_by_pr: dict[int, list[str]] = {}
    numbers = []
    for it in merged[:MAX_PRS] + touched[:MAX_PRS]:
        if it.get("number") not in numbers:
            numbers.append(it.get("number"))
    merged_numbers = {it.get("number") for it in merged}
    for num in numbers[:MAX_PRS]:
        revs = reviews_for(gh, repo, num)
        author = next((_login(it) for it in merged + touched if it.get("number") == num), "")
        if num in merged_numbers:
            reviewers_by_pr[num] = sorted({_login(r) for r in revs if _login(r) and _login(r) != author and not _is_bot(_login(r))})
        for r in revs:
            at = _ts(r.get("submitted_at"))
            who = _login(r)
            if at and at >= since and who and who != author and not _is_bot(who):
                review_counts[who] += 1

    merged_out = []
    for it in merged:
        d = _item(it)
        d["merged_at"] = (it.get("pull_request") or {}).get("merged_at") or it.get("closed_at")
        d["reviewers"] = reviewers_by_pr.get(it.get("number"), [])
        merged_out.append(d)

    # Newcomers: first-time PR authors (GitHub marks them), and issue authors with no earlier activity.
    newcomers: list[dict] = []
    seen: set[str] = set()
    for it in opened_prs:
        who = _login(it)
        if who and who not in seen and not _is_bot(who) and it.get("author_association") in ("FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"):
            seen.add(who)
            newcomers.append({"user": who, "first": "PR", "number": it.get("number"), "url": it.get("html_url", "")})
    checks = 0
    for it in opened_issues:
        who = _login(it)
        if not who or who in seen or _is_bot(who) or it.get("author_association") != "NONE":
            continue
        if checks >= MAX_NEWCOMER_CHECKS:
            break
        checks += 1
        seen.add(who)
        if is_first_issue(gh, repo, who, since):
            newcomers.append({"user": who, "first": "issue", "number": it.get("number"), "url": it.get("html_url", "")})

    rels, _ = gh.get(f"/repos/{repo}/releases", params={"per_page": 10})
    releases = [{"tag": r.get("tag_name", ""), "name": r.get("name") or r.get("tag_name", ""),
                 "url": r.get("html_url", ""), "published_at": r.get("published_at")}
                for r in (rels or []) if (_ts(r.get("published_at")) or since) > since and not r.get("draft")]

    top = review_counts.most_common(3)
    return {
        "repo": repo,
        "url": f"https://github.com/{repo}",
        "window": {"since": s, "until": _iso(now), "hours": int(hours)},
        "stars": {"total": total_stars, "new": None if stars is None else len(stars),
                  "new_stargazers": [] if stars is None else [x["user"] for x in stars]},
        "merged_prs": {"count": merged_n, "items": merged_out[:20]},
        "opened_prs": {"count": opened_prs_n, "items": [_item(i) for i in opened_prs[:20]]},
        "opened_issues": {"count": opened_issues_n, "items": [_item(i) for i in opened_issues[:20]]},
        "closed_issues": {"count": closed_issues_n},
        "newcomers": newcomers,
        "top_reviewers": [{"user": u, "reviews": n} for u, n in top],
        "releases": releases,
        "needs_attention": {"rule": f"open, not draft, no review, opened more than {STALE_REVIEW_DAYS} days ago",
                            "count": stale_n, "items": [_item(i) for i in stale[:5]]},
        "notes": [n for n in (star_note,
                              f"newcomer check capped at {MAX_NEWCOMER_CHECKS} issue authors",
                              f"reviews read for at most {MAX_PRS} PRs") if n],
    }



MAX_LINES = 5  # per kind, so a bulk close does not flood the channel


def _epoch(ts: str | None) -> int:
    d = _ts(ts)
    return int(d.timestamp()) if d else 0


def activity(gh, repo: str, minutes: int = 35, now: datetime | None = None) -> dict[str, Any]:
    """What happened in the last ``minutes``: PRs opened and merged, issues opened and closed.

    Built for a POLL, and built to be cheap: ONE call to the issues API (which lists PRs too, with
    their created, closed and merged times), sorted by last update, no search API. Search has a
    burst limit that a poll every 30 minutes, plus retries, can trip and keep tripped.

    ``activity_cursor`` is the newest of all those event times (epoch seconds) among the 100 most
    recently updated items. It moves forward exactly when a PR or issue is opened, a PR is merged
    or an issue is closed; comments and labels do not move it. The agent echoes it as its change
    SIGNAL and CUGA posts only when it moves. Bot merges are left out of both the list and the cursor.
    """
    repo = check_repo(repo)
    if not 1 <= int(minutes) <= 24 * 60:
        raise ValueError("minutes must be between 1 and 1440")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = now - timedelta(minutes=int(minutes))
    rows, _ = gh.get(f"/repos/{repo}/issues",
                     params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100})
    kinds: dict[str, list[dict]] = {"opened_prs": [], "merged_prs": [], "opened_issues": [], "closed_issues": []}
    cursor = 0
    for it in rows or []:
        is_pr = bool(it.get("pull_request"))
        bot = (it.get("user") or {}).get("type") == "Bot" or _is_bot(_login(it))
        created, closed = it.get("created_at"), it.get("closed_at")
        merged = (it.get("pull_request") or {}).get("merged_at") if is_pr else None
        row = _item(it) | {"first_time": it.get("author_association") in ("FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR")}
        times = [created]
        if is_pr and merged and not bot:
            times.append(merged)
        if not is_pr and it.get("state") == "closed":
            times.append(closed)
        cursor = max([cursor] + [_epoch(t) for t in times])
        if (_ts(created) or since) > since or _ts(created) == since:
            kinds["opened_prs" if is_pr else "opened_issues"].append(row)
        if is_pr and merged and not bot and _ts(merged) >= since:
            kinds["merged_prs"].append(row)
        if not is_pr and it.get("state") == "closed" and closed and _ts(closed) >= since:
            kinds["closed_issues"].append(row)
    out = {k: {"count": len(v), "items": v[:MAX_LINES], "more": max(0, len(v) - MAX_LINES)} for k, v in kinds.items()}
    return {
        "lines": _lines(out),
        "repo": repo,
        "window": {"since": _iso(since), "until": _iso(now), "minutes": int(minutes)},
        **out,
        "nothing_new": not any(v["count"] for v in out.values()),
        "activity_cursor": cursor,
    }


# The feed lines are rendered here, not by the LLM: asked to fill a template, the model retyped an
# author's login wrong ("Serrey" for "Sergey"). Copying finished lines leaves it nothing to garble.
_TEMPLATES = {
    "opened_prs": ("🟡", "New PR", "PRs opened"),
    "merged_prs": ("🟢", "Merged PR", "PRs merged"),
    "opened_issues": ("🔵", "New issue", "issues opened"),
    "closed_issues": ("✅", "Closed issue", "issues closed"),
}


def _lines(out: dict) -> list[str]:
    lines = []
    for kind, (emoji, label, plural) in _TEMPLATES.items():
        for i in out[kind]["items"]:
            by = "" if kind == "closed_issues" else f" by @{i['author']}"
            first = " · 👋 first contribution" if i.get("first_time") and kind in ("opened_prs", "opened_issues") else ""
            lines.append(f'{emoji} {label} #{i["number"]} "{i["title"]}"{by} · {i["url"]}{first}')
        if out[kind]["more"]:
            lines.append(f"… and {out[kind]['more']} more {plural}")
    return lines  # empty when nothing happened: a pre-checked poll then posts nothing


def stars(gh, repo: str) -> dict[str, Any]:
    """The star total, for a POLL that posts when it changes (it can go down: people unstar)."""
    repo = check_repo(repo)
    meta, _ = gh.get(f"/repos/{repo}")
    total = int(meta.get("stargazers_count", 0))
    url = f"https://github.com/{repo}"
    return {"repo": repo, "url": url, "total": total, "line": f"⭐ {repo} now has {total} stars · {url}"}
