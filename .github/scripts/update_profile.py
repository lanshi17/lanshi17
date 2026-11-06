#!/usr/bin/env python3
"""Regenerate the dynamic blocks of the profile README.

Two sections are rewritten in place, between HTML comment markers:

  NOW        - the repos pushed to most recently, so the page shows what is
               actually moving instead of what we remembered to edit.
  SELECTED   - the pinned repositories. Pinning on the GitHub profile is the
               curation step; this script just mirrors that choice as a table
               with language, topics and description.

Everything outside the markers is hand-written and never touched. If the API
call fails the README is left alone and the script exits non-zero, so a bad
token fails the job instead of blanking the profile.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "lanshi17")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
README = Path(os.environ.get("README_PATH", "README.md"))

API = "https://api.github.com"
NOW_MARKERS = ("<!-- NOW:START -->", "<!-- NOW:END -->")
SELECTED_MARKERS = ("<!-- SELECTED:START -->", "<!-- SELECTED:END -->")

NOW_LIMIT = 3
ACTIVE_WINDOW_DAYS = 60


def api(path: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "profile-readme-refresh",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def graphql(query: str, variables: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API}/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "profile-readme-refresh",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"][0].get("message", "graphql error"))
    return payload["data"]


def owned_repos() -> list[dict]:
    repos = api(f"/users/{USER}/repos?per_page=100&sort=pushed&direction=desc&type=owner")
    return [
        r
        for r in repos
        if not r["fork"] and not r["archived"] and r["name"].lower() != USER.lower()
    ]


def pinned_repos() -> list[dict]:
    """Pinned repositories, in the order they are pinned on the profile."""
    query = """
    query($login: String!) {
      user(login: $login) {
        pinnedItems(first: 6, types: [REPOSITORY]) {
          nodes {
            ... on Repository {
              name
              nameWithOwner
              url
              description
              primaryLanguage { name }
              repositoryTopics(first: 6) { nodes { topic { name } } }
              isArchived
            }
          }
        }
      }
    }
    """
    data = graphql(query, {"login": USER})
    nodes = (((data.get("user") or {}).get("pinnedItems") or {}).get("nodes")) or []
    # The API returns pins oldest-first; newest curation is what we want on top.
    return [n for n in reversed(nodes) if n]


def relative_date(iso: str) -> str:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - then).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    return f"{months}mo ago"


ACRONYMS = {"ai", "llm", "tui", "wasm", "rag", "api", "sql", "ci", "cli", "ui", "ocr", "gpu", "db", "mcp"}


def prettify(topic: str) -> str:
    words = topic.replace("-", " ").split()
    return " ".join(w.upper() if w.lower() in ACRONYMS else w.capitalize() for w in words)


def stack_of(repo: dict) -> str:
    lang = (repo.get("primaryLanguage") or {}).get("name") or (repo.get("language") or "")
    topics = [t["topic"]["name"] for t in ((repo.get("repositoryTopics") or {}).get("nodes") or [])]
    parts = [lang] if lang else []
    parts += [prettify(t) for t in topics[:2]]
    return " · ".join(parts) if parts else "—"


def short(text: str | None, limit: int = 150) -> str:
    if not text:
        return "No description yet."
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def render_now(repos: list[dict]) -> str:
    active = [r for r in repos if _days_since(r["pushed_at"]) <= ACTIVE_WINDOW_DAYS]
    active = (active or repos)[:NOW_LIMIT]
    if not active:
        return "Nothing public has moved recently."
    lines = []
    for r in active:
        meta = [r.get("language") or ""]
        # Same-day activity is the norm here; spelling it out three times reads
        # like a log, so only older work gets its age called out.
        if _days_since(r["pushed_at"]) >= 2:
            meta.append(f"updated {relative_date(r['pushed_at'])}")
        lines.append(
            f"- **[{r['name']}]({r['html_url']})** — {short(r['description'])} "
            f"`{' · '.join(x for x in meta if x)}`"
        )
    return "\n".join(lines)


def render_selected(repos: list[dict]) -> str:
    if not repos:
        return "No pinned repositories."
    rows = ["| Project | Stack | What it does |", "| :-- | :-- | :-- |"]
    for r in repos:
        name = r["name"]
        owner = r["nameWithOwner"].split("/")[0]
        label = name if owner == USER else r["nameWithOwner"]
        if r.get("isArchived"):
            label += " *(archived)*"
        rows.append(f"| [{label}]({r['url']}) | {stack_of(r)} | {short(r.get('description'))} |")
    return "\n".join(rows)


def _days_since(iso: str) -> int:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - then).days


def replace_block(text: str, markers: tuple[str, str], body: str) -> str:
    start, end = markers
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    block = f"{start}\n{body}\n{end}"
    if not pattern.search(text):
        raise SystemExit(f"missing markers {start} / {end} in {README}")
    return pattern.sub(lambda _: block, text, count=1)


def main() -> int:
    if not TOKEN:
        print("GITHUB_TOKEN is not set", file=sys.stderr)
        return 1

    original = README.read_text(encoding="utf-8")
    try:
        pins = pinned_repos()
        pinned_names = {r["nameWithOwner"].split("/")[-1] for r in pins}
        repos = owned_repos()
        # What is already pinned is shown below as cards; repeating it in "Now"
        # just says the same thing twice. Only fall back to pinned repos when
        # there is nothing else moving.
        unpinned = [r for r in repos if r["name"] not in pinned_names]
        now_body = render_now(unpinned if len(unpinned) >= 2 else repos)
        selected_body = render_selected(pins)
    except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
        print(f"could not refresh profile blocks: {exc}", file=sys.stderr)
        return 1

    updated = replace_block(original, NOW_MARKERS, now_body)
    updated = replace_block(updated, SELECTED_MARKERS, selected_body)

    if updated == original:
        print("README already up to date")
        return 0

    README.write_text(updated, encoding="utf-8")
    print("README updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
