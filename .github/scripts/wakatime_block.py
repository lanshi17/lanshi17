#!/usr/bin/env python3
"""Render WakaTime all-time stats into the coding-time block in README.md.

Replaces everything between <!-- WAKA:START --> and <!-- WAKA:END -->.
Exits non-zero only on real failures so the workflow fails loudly.
"""
import json
import os
import re
import sys
import urllib.request

API = "https://wakatime.com/api/v1/users/current/stats/all_time"
START = "<!-- WAKA:START -->"
END = "<!-- WAKA:END -->"
README = "README.md"


def hours(seconds: float) -> str:
    value = seconds / 3600
    return f"{value:,.0f}h" if value >= 10 else f"{value:.1f}h"


def short_hours(text: str) -> str:
    """'1,842 hrs 20 mins' -> '1,842 hrs'"""
    return f"{text.split(' hrs')[0]} hrs" if ' hrs' in text else text


def top(items, n=4):
    return " · ".join(f"{i['name']} {hours(i['total_seconds'])}" for i in items[:n])


def main() -> int:
    token = os.environ.get("WAKATIME_TOKEN", "").strip()
    if not token:
        print("WAKATIME_TOKEN is empty", file=sys.stderr)
        return 1

    req = urllib.request.Request(
        API,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "lanshi17-profile-readme"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)["data"]

    languages = [l for l in data.get("languages", []) if l["name"] != "Other"]
    editors = data.get("editors", [])
    systems = data.get("operating_systems", [])

    block = "\n".join(
        [
            "```console",
            "$ wakatime --all-time",
            f"total    {short_hours(data.get('human_readable_total_including_other_language') or data['human_readable_total'])} · "
            f"{data.get('human_readable_daily_average') or '—'}/day · since {data['start'][:7]}",
            f"langs    {top(languages)}",
            f"editors  {top(editors)}",
            f"os       {top(systems, 3)}",
            "```",
        ]
    )

    with open(README, encoding="utf-8") as fh:
        text = fh.read()

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        print("markers not found in README.md", file=sys.stderr)
        return 1

    updated = pattern.sub(lambda _: f"{START}\n{block}\n{END}", text)
    if updated == text:
        print("no change")
        return 0

    with open(README, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print("README updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
