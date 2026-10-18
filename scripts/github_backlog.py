"""Creates GitHub milestones, labels and issues from specs/tasks.md.

Requires an authenticated `gh` CLI (`gh auth login`) and must run inside the repo.
Idempotent: does not duplicate milestones, labels or issues with the same title.

Usage:
    python scripts/github_backlog.py --dry-run   # show what it would do
    python scripts/github_backlog.py             # create everything
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TASKS_FILE = Path(__file__).resolve().parent.parent / "specs" / "tasks.md"

# Due date of each milestone (checkpoint).
DUE_DATES = {
    "Week 1": "2026-10-23",
    "Week 2": "2026-10-31",
    "Week 3": "2026-11-06",
    "Week 4": "2026-11-13",
    "Week 5": "2026-11-21",
    "After the grade": "2026-12-31",
}
COLOURS = {
    "infra": "5319e7", "aws": "ff9900", "repo": "c5def5", "api": "1d76db",
    "ci": "0e8a16", "data": "fbca04", "model": "d93f0b", "evaluation": "b60205",
    "cascade": "0052cc", "security": "e11d21", "web": "bfd4f2", "docs": "006b75",
    "submission": "000000",
}  # fmt: skip


@dataclass
class Task:
    id: str
    title: str
    milestone: str
    hours: str = ""
    labels: list[str] = field(default_factory=list)
    spec: str = ""
    done_when: str = ""

    @property
    def issue_title(self) -> str:
        return f"{self.id} · {self.title}"

    def body(self) -> str:
        return (
            f"**Estimate:** {self.hours} h · **Spec:** {self.spec}\n\n"
            f"### Done when\n{self.done_when}\n\n"
            "### Session log\n"
            "_Added with `/close-session` (actual hours, done, blockers, next)._\n\n"
            "Source: `specs/tasks.md`"
        )


def parse(text: str) -> list[Task]:
    tasks: list[Task] = []
    milestone = ""
    current: Task | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            milestone = name.split(" · ")[0] if name.startswith("Week") else name
        elif m := re.match(r"### (T\d+\.\d+) · (.+)", line):
            current = Task(id=m[1], title=m[2].strip(), milestone=milestone)
            tasks.append(current)
        elif current and (m := re.match(r"- (Hours|Labels|Spec|Done when): (.+)", line)):
            key, value = m[1], m[2].strip()
            if key == "Hours":
                current.hours = value
            elif key == "Labels":
                current.labels = [label.strip() for label in value.split(",")]
            elif key == "Spec":
                current.spec = value
            else:
                current.done_when = value
    return tasks


def gh(*args: str, dry_run: bool) -> str:
    if dry_run:
        print("  [dry-run] gh " + " ".join(args))
        return ""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def existing(dry_run: bool) -> tuple[set[str], set[str], set[str]]:
    if dry_run:
        return set(), set(), set()
    milestones = json.loads(
        gh("api", "repos/{owner}/{repo}/milestones?state=all&per_page=100", dry_run=False)
    )
    labels = json.loads(gh("label", "list", "--limit", "200", "--json", "name", dry_run=False))
    issues = json.loads(
        gh("issue", "list", "--state", "all", "--limit", "500", "--json", "title", dry_run=False)
    )
    return (
        {m["title"] for m in milestones},
        {label["name"] for label in labels},
        {i["title"] for i in issues},
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="Only show what it would do")
    dry_run = parser.parse_args().dry_run

    tasks = parse(TASKS_FILE.read_text(encoding="utf-8"))
    have_milestones, have_labels, have_issues = existing(dry_run)
    print(f"{len(tasks)} tasks in specs/tasks.md")

    for milestone in dict.fromkeys(t.milestone for t in tasks):
        if milestone not in have_milestones:
            print(f"Milestone: {milestone}")
            due = DUE_DATES.get(milestone, "2026-11-21")
            gh("api", "repos/{owner}/{repo}/milestones", "-f", f"title={milestone}",
               "-f", f"due_on={due}T23:00:00Z", dry_run=dry_run)  # fmt: skip

    for label in sorted({label for t in tasks for label in t.labels}):
        if label not in have_labels:
            print(f"Label: {label}")
            gh("label", "create", label, "--color", COLOURS.get(label, "ededed"), "--force",
               dry_run=dry_run)  # fmt: skip

    for t in tasks:
        if t.issue_title in have_issues:
            continue
        print(f"Issue: {t.issue_title}")
        args = ["issue", "create", "--title", t.issue_title, "--body", t.body(),
                "--milestone", t.milestone]  # fmt: skip
        for label in t.labels:
            args += ["--label", label]
        gh(*args, dry_run=dry_run)

    print("Done. Now create the GitHub Projects board (see docs/workflow.md).")


if __name__ == "__main__":
    main()
