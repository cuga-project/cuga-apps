"""Offline tests for repo_pulse: a fake GitHub client, no network.

Run:  cd cuga-apps && .venv/bin/python -m pytest mcp_servers/repo_pulse/tests -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mcp_servers.repo_pulse import service  # noqa: E402

NOW = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)  # window: Nov 3 14:00 → Nov 4 14:00
R = "acme/widget"


def pr(n, who, assoc="CONTRIBUTOR", merged_at=None):
    d = {"number": n, "title": f"PR {n}", "user": {"login": who}, "html_url": f"https://github.com/{R}/pull/{n}",
         "author_association": assoc}
    if merged_at:
        d["pull_request"] = {"merged_at": merged_at}
    return d


def issue(n, who, assoc="NONE"):
    return {"number": n, "title": f"Issue {n}", "user": {"login": who},
            "html_url": f"https://github.com/{R}/issues/{n}", "author_association": assoc}


def review(who, at):
    return {"user": {"login": who}, "submitted_at": at, "state": "APPROVED"}


class FakeGitHub:
    """Answers the exact calls daily_activity makes; records them."""

    def __init__(self, stars_total=205, earlier_activity=("old-timer",)):
        self.calls = []
        self.stars_total = stars_total
        self.earlier = set(earlier_activity)

    def get(self, path, params=None, headers=None):
        self.calls.append((path, dict(params or {})))
        p = params or {}
        if path == f"/repos/{R}":
            return {"stargazers_count": self.stars_total}, {}
        if path == f"/repos/{R}/stargazers":
            page = p["page"]
            if page == 3:   # 5 stars on the last page: 3 new, 2 old
                return [
                    {"user": {"login": "old1"}, "starred_at": "2026-11-01T10:00:00Z"},
                    {"user": {"login": "old2"}, "starred_at": "2026-11-03T13:59:59Z"},
                    {"user": {"login": "s1"}, "starred_at": "2026-11-03T15:00:00Z"},
                    {"user": {"login": "s2"}, "starred_at": "2026-11-04T01:00:00Z"},
                    {"user": {"login": "s3"}, "starred_at": "2026-11-04T13:00:00Z"},
                ], {}
            raise AssertionError(f"unexpected stargazer page {page}")
        if path == "/search/issues":
            q = p["q"]
            if "is:merged" in q:
                return {"total_count": 2, "items": [pr(10, "alice", merged_at="2026-11-04T09:00:00Z"),
                                                    pr(11, "dependabot[bot]", merged_at="2026-11-04T10:00:00Z")]}, {}
            if "is:pr created:" in q:
                return {"total_count": 2, "items": [pr(12, "newbie", "FIRST_TIME_CONTRIBUTOR"), pr(13, "alice")]}, {}
            if "is:issue created:" in q:
                return {"total_count": 3, "items": [issue(20, "fresh"), issue(21, "old-timer"),
                                                    issue(22, "member", "MEMBER")]}, {}
            if "is:closed" in q:
                return {"total_count": 4, "items": []}, {}
            if "review:none" in q:
                return {"total_count": 1, "items": [pr(5, "carol")]}, {}
            if "updated:" in q:
                return {"total_count": 2, "items": [pr(10, "alice"), pr(13, "alice")]}, {}
            if "author:" in q:
                who = q.split("author:")[1].split()[0]
                return {"total_count": 1 if who in self.earlier else 0, "items": []}, {}
            raise AssertionError(q)
        if path == f"/repos/{R}/pulls/10/reviews":
            return [review("bob", "2026-11-04T08:00:00Z"), review("coderabbitai[bot]", "2026-11-04T08:00:00Z"),
                    review("alice", "2026-11-04T08:30:00Z")], {}
        if path == f"/repos/{R}/pulls/11/reviews":
            return [review("bob", "2026-11-04T09:30:00Z")], {}
        if path == f"/repos/{R}/pulls/13/reviews":
            return [review("bob", "2026-11-04T12:00:00Z"), review("dave", "2026-11-02T12:00:00Z")], {}
        if path == f"/repos/{R}/releases":
            return [{"tag_name": "v1.2.0", "name": "v1.2.0", "html_url": "u", "published_at": "2026-11-04T12:00:00Z"},
                    {"tag_name": "v1.1.0", "published_at": "2026-10-01T00:00:00Z"},
                    {"tag_name": "v1.3.0-rc", "draft": True, "published_at": None}], {}
        raise AssertionError(f"unexpected call {path} {p}")


def test_daily_activity_numbers():
    d = service.daily_activity(FakeGitHub(), R, 24, now=NOW)
    assert d["window"] == {"since": "2026-11-03T14:00:00Z", "until": "2026-11-04T14:00:00Z", "hours": 24}
    assert d["stars"] == {"total": 205, "new": 3, "new_stargazers": ["s3", "s2", "s1"]}
    assert d["merged_prs"]["count"] == 2
    m = {i["number"]: i for i in d["merged_prs"]["items"]}
    assert m[10]["reviewers"] == ["bob"]          # author and bots are not reviewers
    assert m[10]["merged_at"] == "2026-11-04T09:00:00Z"
    assert d["opened_prs"]["count"] == 2 and d["opened_issues"]["count"] == 3
    assert d["closed_issues"] == {"count": 4}
    # bob: PR10 + PR11 + PR13 in window; dave's review is before the window; bots never count
    assert d["top_reviewers"] == [{"user": "bob", "reviews": 3}]
    assert [n["user"] for n in d["newcomers"]] == ["newbie", "fresh"]   # old-timer has earlier activity
    assert [r["tag"] for r in d["releases"]] == ["v1.2.0"]
    assert d["needs_attention"]["count"] == 1 and d["needs_attention"]["items"][0]["number"] == 5


def test_result_is_json_serialisable():
    json.dumps(service.daily_activity(FakeGitHub(), R, 24, now=NOW))


def test_no_stars_makes_no_stargazer_call():
    gh = FakeGitHub(stars_total=0)
    d = service.daily_activity(gh, R, 24, now=NOW)
    assert d["stars"]["new"] == 0
    assert not any(c[0].endswith("/stargazers") for c in gh.calls)


@pytest.mark.parametrize("bad", ["", "nope", "a/b/c", "a b/c", "../etc"])
def test_bad_repo_is_refused(bad):
    with pytest.raises(ValueError):
        service.daily_activity(FakeGitHub(), bad, 24, now=NOW)


@pytest.mark.parametrize("hours", [0, -1, 745])
def test_bad_window_is_refused(hours):
    with pytest.raises(ValueError):
        service.daily_activity(FakeGitHub(), R, hours, now=NOW)


def test_repo_url_form_is_accepted():
    assert service.check_repo("https://github.com/acme/widget/") == "acme/widget"


def test_token_from_secret_file(tmp_path, monkeypatch):
    (tmp_path / "GITHUB_TOKEN").write_text("from-file\n")
    monkeypatch.setenv("MCP_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")
    assert service.github_token() == "from-file"


def test_stargazer_refusal_keeps_the_report():
    class NoStars(FakeGitHub):
        def get(self, path, params=None, headers=None):
            if path.endswith("/stargazers"):
                raise RuntimeError("403 Resource not accessible by personal access token")
            return super().get(path, params, headers)

    d = service.daily_activity(NoStars(), R, 24, now=NOW)
    assert d["stars"] == {"total": 205, "new": None, "new_stargazers": []}
    assert d["notes"][0].startswith("new stars unavailable")
    assert d["merged_prs"]["count"] == 2   # the rest of the report is intact



def gh_item(n, who, created, *, pr=False, closed=None, merged=None, bot=False, assoc="CONTRIBUTOR"):
    d = {"number": n, "title": f"T{n}", "user": {"login": who, "type": "Bot" if bot else "User"},
         "html_url": f"https://github.com/{R}/{'pull' if pr else 'issues'}/{n}", "author_association": assoc,
         "created_at": created, "closed_at": closed, "state": "closed" if closed else "open"}
    if pr:
        d["pull_request"] = {"merged_at": merged}
    return d


class ActivityGitHub:
    """One issues-API page, newest update first; records calls (there must be exactly one)."""

    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def get(self, path, params=None, headers=None):
        self.calls.append(path)
        if path == f"/repos/{R}":
            return {"stargazers_count": 1071}, {}
        assert path == f"/repos/{R}/issues" and params["sort"] == "updated"
        return self.rows, {}


# NOW = 2026-11-04 14:00Z, window 35 min → since 13:25Z
ROWS = [
    gh_item(1111, "newbie", "2026-11-04T13:50:00Z", pr=True, assoc="FIRST_TIME_CONTRIBUTOR"),
    gh_item(1100, "alice", "2026-11-01T10:00:00Z", pr=True, closed="2026-11-04T13:40:00Z", merged="2026-11-04T13:40:00Z"),
    gh_item(1099, "github-actions[bot]", "2026-11-04T09:00:00Z", pr=True, closed="2026-11-04T13:55:00Z",
            merged="2026-11-04T13:55:00Z", bot=True),
    gh_item(1090, "bob", "2026-10-20T10:00:00Z", closed="2026-11-04T13:30:00Z"),
    gh_item(1080, "carol", "2026-10-01T10:00:00Z"),   # only a comment: updated, nothing else
]


def test_activity_is_one_call_and_lists_the_four_kinds():
    gh = ActivityGitHub(ROWS)
    d = service.activity(gh, R, 35, now=NOW)
    assert gh.calls == [f"/repos/{R}/issues"]               # no search API at all
    assert d["window"]["since"] == "2026-11-04T13:25:00Z"
    assert [i["number"] for i in d["opened_prs"]["items"]] == [1111] and d["opened_prs"]["items"][0]["first_time"]
    assert [i["number"] for i in d["merged_prs"]["items"]] == [1100]     # the bot merge is left out
    assert [i["number"] for i in d["closed_issues"]["items"]] == [1090]
    assert d["opened_issues"]["count"] == 0 and d["nothing_new"] is False
    # cursor = newest event time, ignoring the bot merge at 13:55
    assert d["activity_cursor"] == int(datetime(2026, 11, 4, 13, 50, tzinfo=timezone.utc).timestamp())


def test_cursor_does_not_move_on_comments_and_moves_on_each_event():
    base = service.activity(ActivityGitHub(ROWS), R, 35, now=NOW)["activity_cursor"]
    commented = [dict(r) for r in ROWS]
    assert service.activity(ActivityGitHub(commented), R, 35, now=NOW)["activity_cursor"] == base
    later = "2026-11-04T13:58:00Z"
    for extra in (gh_item(1112, "x", later, pr=True),                                   # PR opened
                  gh_item(1113, "x", later),                                            # issue opened
                  gh_item(1050, "x", "2026-10-01T00:00:00Z", pr=True, closed=later, merged=later),  # merged
                  gh_item(1060, "x", "2026-10-01T00:00:00Z", closed=later)):           # issue closed
        assert service.activity(ActivityGitHub([extra] + ROWS), R, 35, now=NOW)["activity_cursor"] > base


def test_a_quiet_window_reports_nothing_new_but_keeps_the_cursor():
    quiet_now = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)
    d = service.activity(ActivityGitHub(ROWS), R, 35, now=quiet_now)
    assert d["nothing_new"] is True
    assert d["activity_cursor"] == service.activity(ActivityGitHub(ROWS), R, 35, now=NOW)["activity_cursor"]


def test_bulk_close_is_capped_with_more():
    rows = [gh_item(900 + i, "x", "2026-10-01T00:00:00Z", closed="2026-11-04T13:45:00Z") for i in range(8)]
    d = service.activity(ActivityGitHub(rows), R, 35, now=NOW)
    assert d["closed_issues"]["count"] == 8 and len(d["closed_issues"]["items"]) == 5 and d["closed_issues"]["more"] == 3


@pytest.mark.parametrize("minutes", [0, 1441])
def test_activity_bad_window_is_refused(minutes):
    with pytest.raises(ValueError):
        service.activity(ActivityGitHub(ROWS), R, minutes, now=NOW)


def test_stars_returns_the_total():
    assert service.stars(ActivityGitHub([]), R) == {"repo": R, "url": f"https://github.com/{R}", "total": 1071,
                                                    "line": f"⭐ {R} now has 1071 stars · https://github.com/{R}"}


def test_activity_renders_the_feed_lines_itself():
    d = service.activity(ActivityGitHub(ROWS), R, 35, now=NOW)
    assert d["lines"] == [
        f'🟡 New PR #1111 "T1111" by @newbie · https://github.com/{R}/pull/1111 · 👋 first contribution',
        f'🟢 Merged PR #1100 "T1100" by @alice · https://github.com/{R}/pull/1100',
        f'✅ Closed issue #1090 "T1090" · https://github.com/{R}/issues/1090',
    ]
    quiet = service.activity(ActivityGitHub(ROWS), R, 35, now=datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc))
    assert quiet["lines"] == [] and quiet["nothing_new"] is True
    rows = [gh_item(900 + i, "x", "2026-10-01T00:00:00Z", closed="2026-11-04T13:45:00Z") for i in range(7)]
    assert service.activity(ActivityGitHub(rows), R, 35, now=NOW)["lines"][-1] == "… and 2 more issues closed"


def test_rate_limited_calls_are_retried(monkeypatch):
    import httpx

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(403, text='{"message": "You have exceeded a secondary rate limit."}')
        return httpx.Response(200, json={"stargazers_count": 7})

    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    gh = service.GitHub(token="t")
    gh._c = httpx.Client(base_url=service.API, transport=httpx.MockTransport(handler))
    assert service.stars(gh, R)["total"] == 7 and calls["n"] == 3


def test_a_lasting_rate_limit_still_fails(monkeypatch):
    import httpx

    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    gh = service.GitHub(token="t")
    gh._c = httpx.Client(base_url=service.API, transport=httpx.MockTransport(
        lambda r: httpx.Response(429, text="slow down")))
    with pytest.raises(RuntimeError, match="rate limit"):
        service.stars(gh, R)
