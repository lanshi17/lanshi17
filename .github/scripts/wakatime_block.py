#!/usr/bin/env python3
"""Render WakaTime all-time stats into the one-line block in README.md.

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
    return f"{text.split(' hrs')[0]} hrs" if " hrs" in text else text


def compact(text: str) -> str:
    """'3 hrs 21 mins' -> '3h 21m'"""
    return text.replace(" hrs", "h").replace(" mins", "m")


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

    parts = [
        f"**{short_hours(data.get('human_readable_total_including_other_language') or data['human_readable_total'])}** logged",
        compact(data.get("human_readable_daily_average") or "—") + "/day",
        f"since {data['start'][:7]}",
    ]
    parts += [f"{l['name']} {hours(l['total_seconds'])}" for l in languages[:1]]
    if editors:
        parts.append(f"editor {editors[0]['name']} {hours(editors[0]['total_seconds'])}")

    block = " · ".join(parts)

    with open(README, encoding="utf-8") as fh:
        text = fh.read()

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        print("markers not found in README.md", file=sys.stderr)
        return 1

    updated = pattern.sub(lambda _: f"{START}{block}{END}", text)
    if updated == text:
        print("no change")
        return 0

    with open(README, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print("README updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
