"""TFM hours log.

Usage:
    python scripts/hours.py log --hours 1.5 --task T1.3 --summary "API skeleton"
    python scripts/hours.py total
    python scripts/hours.py status
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "docs" / "hours-log.csv"
FIELDS = ["date", "hours", "task", "summary"]

START = date(2026, 10, 17)
SUBMISSION = date(2026, 11, 21)
# Planned cumulative hours at the end of each week (specs/tasks.md).
PLANNED_CUMULATIVE = {1: 10, 2: 22, 3: 34, 4: 46, 5: 55}
EXTENSION_RULE_H = 36  # 6 Nov checkpoint
CEILING_H = 60
HARD_LIMIT_H = 65


def read_rows() -> list[dict[str, str]]:
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def total(rows: list[dict[str, str]]) -> float:
    return sum(float(r["hours"]) for r in rows)


def current_week(today: date) -> int:
    return min(max((today - START).days // 7 + 1, 1), 5)


def log(hours: float, task: str, summary: str) -> None:
    if hours <= 0 or hours > 12:
        sys.exit("Hours must be between 0 and 12 per session.")
    is_new = not LOG_FILE.exists()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {"date": date.today().isoformat(), "hours": hours, "task": task, "summary": summary}
        )
    print(f"Logged: {hours} h on {task}. Total: {total(read_rows()):.1f} h")


def status(today: date) -> None:
    rows = read_rows()
    spent = total(rows)
    week = current_week(today)
    planned = PLANNED_CUMULATIVE[week]
    days_left = (SUBMISSION - today).days
    print(f"Today: {today.isoformat()} · Week {week} of 5 · Days to submission: {days_left}")
    print(f"Actual hours: {spent:.1f} h · Plan at end of week {week}: {planned} h")
    print(f"Ceiling: {CEILING_H} h ({CEILING_H - spent:.1f} left) · Hard limit: {HARD_LIMIT_H} h")
    if today <= date(2026, 11, 6):
        rule = "met" if spent <= EXTENSION_RULE_H else "NOT met"
        print(f"Extension rule on 6 Nov (≤ {EXTENSION_RULE_H} h): currently {rule}")
    if spent > CEILING_H:
        print("⚠️  60 h ceiling exceeded: scope must be cut.")
    per_task: dict[str, float] = {}
    for r in rows:
        per_task[r["task"]] = per_task.get(r["task"], 0) + float(r["hours"])
    if per_task:
        print("Per task: " + ", ".join(f"{k} {v:.1f} h" for k, v in sorted(per_task.items())))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    log_parser = sub.add_parser("log")
    log_parser.add_argument("--hours", type=float, required=True)
    log_parser.add_argument("--task", default="general")
    log_parser.add_argument("--summary", required=True)
    sub.add_parser("total")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.cmd == "log":
        log(args.hours, args.task, args.summary)
    elif args.cmd == "total":
        print(f"{total(read_rows()):.1f} h logged")
    else:
        status(date.today())


if __name__ == "__main__":
    main()
