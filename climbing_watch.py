#!/usr/bin/env python3
"""Check UTVS climbing class listings for newly opened free spots and notify via ntfy.sh.

Runs in GitHub Actions on a schedule (see .github/workflows/check.yml).
State is persisted in climbing_watch_state.json, which the workflow commits
back to the repo after each run.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.utvs.cvut.cz/vyuka/povinna-volitelna?s%5B%5D=17&d=0&t=420%3B1380"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
MAX_LOG_LINES = 2000

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "climbing_watch_state.json"
LOG_FILE = BASE_DIR / "climbing_watch.log"

ROW_RE = re.compile(
    r'<td class="exp"></td>\s*'
    r'<td><a[^>]*>([^<]+)</a></td>\s*'
    r'<td class="c">([^<]+)</td>\s*'
    r'<td class="c">([^<]+)</td>\s*'
    r'<td class="c">(\d+)</td>\s*'
    r'<td class="c">\s*(?:<a[^>]*>([^<]*)</a>|([^<]*))\s*</td>\s*'
    r'<td class="c">\s*(?:<a[^>]*>([^<]*)</a>|([^<]*))\s*</td>',
    re.DOTALL,
)
CODE_RE = re.compile(r'Zkratka sportu:\s*</strong>\s*<span[^>]*>([^<]+)</span>')


def fetch_html() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_classes(html: str):
    matches = list(ROW_RE.finditer(html))
    classes = []
    for i, m in enumerate(matches):
        sport, day, time, free, loc_a, loc_b, teacher_a, teacher_b = m.groups()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        tail = html[m.end():chunk_end]
        code_m = CODE_RE.search(tail)
        code = code_m.group(1) if code_m else f"row{i}-{day.strip()}-{time.strip()}"
        classes.append({
            "code": code,
            "sport": sport.strip(),
            "day": day.strip(),
            "time": time.strip(),
            "free": int(free),
            "location": (loc_a or loc_b or "").strip(),
            "teacher": (teacher_a or teacher_b or "").strip(),
        })
    return classes


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(msg)
    lines = LOG_FILE.read_text().splitlines() if LOG_FILE.exists() else []
    lines.insert(0, f"[{ts}] {msg}")
    LOG_FILE.write_text("\n".join(lines[:MAX_LOG_LINES]) + "\n")


def notify_ntfy(title: str, message: str) -> None:
    if not NTFY_TOPIC:
        print("WARNING: NTFY_TOPIC not set, skipping push notification", file=sys.stderr)
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": "high",
            "Tags": "climbing",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except Exception as e:
        print(f"ERROR sending ntfy notification: {e}", file=sys.stderr)


def main() -> None:
    try:
        html = fetch_html()
    except Exception as e:
        log(f"ERROR fetching page: {e}")
        sys.exit(1)

    classes = parse_classes(html)
    if not classes:
        log("WARNING: no classes parsed - page structure may have changed")
        sys.exit(1)

    state = load_state()
    newly_free = []
    for c in classes:
        prev_free = state.get(c["code"], {}).get("free", 0)
        if c["free"] > 0 and c["free"] > prev_free:
            newly_free.append(c)
        state[c["code"]] = {
            "free": c["free"], "sport": c["sport"],
            "day": c["day"], "time": c["time"],
        }
    save_state(state)

    total_free = sum(c["free"] for c in classes)
    summary = f"Checked {len(classes)} classes, {total_free} free spot(s) total"
    if newly_free:
        summary += f", NEW: {len(newly_free)}"
    log(summary)

    if newly_free:
        lines = [
            f"{c['day']} {c['time']} - {c['sport']} ({c['teacher']}, {c['location']}) "
            f"- {c['free']} free spot(s)"
            for c in newly_free
        ]
        body = "\n".join(lines) + f"\n\n{URL}"
        title = (
            "Climbing class spot open!"
            if len(newly_free) == 1
            else f"{len(newly_free)} climbing spots opened!"
        )
        notify_ntfy(title, body)
        log("Notification sent: " + "; ".join(lines))


if __name__ == "__main__":
    main()
