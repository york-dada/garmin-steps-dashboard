from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE_PATHS = [
    "data/raw",
    "build_dashboard.py",
    "site/assets",
    ".github/workflows/build-and-deploy.yml",
    ".gitignore",
    "scripts/upload_to_github.py",
    "upload_to_github.bat",
    "build_upload_exe.bat",
]


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"> {' '.join(args)}")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.stdout:
        print(completed.stdout.rstrip())
    if check and completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(args)}")
    return completed


def git_output(args: list[str]) -> str:
    return run(["git", *args]).stdout.strip()


def has_changes() -> bool:
    return bool(git_output(["status", "--porcelain", "--", *STAGE_PATHS]))


def staged_changes() -> bool:
    return bool(git_output(["diff", "--cached", "--name-only"]))


def make_commit_message() -> str:
    names = []
    today = dt.date.today().isoformat()
    for member_dir in (ROOT / "data" / "raw").iterdir():
        if not member_dir.is_dir():
            continue
        if bool(git_output(["status", "--porcelain", "--", str(member_dir.relative_to(ROOT))])):
            names.append(member_dir.name.capitalize())

    people = " and ".join(sorted(names)) if names else "Garmin"
    return f"Update {people} data for {today}"


def main() -> int:
    print("Garmin dashboard GitHub uploader")
    print(f"Repository: {ROOT}")
    print()

    try:
        git_output(["rev-parse", "--is-inside-work-tree"])
        run([sys.executable, "build_dashboard.py"])

        if not has_changes():
            print("No data/dashboard source changes to upload.")
            return 0

        print()
        print("Changes to upload:")
        print(git_output(["status", "--short", "--", *STAGE_PATHS]))
        print()

        run(["git", "add", *STAGE_PATHS])
        if not staged_changes():
            print("No staged changes after git add.")
            return 0

        commit_message = make_commit_message()
        run(["git", "commit", "-m", commit_message])

        branch = git_output(["branch", "--show-current"])
        if not branch:
            raise RuntimeError("Could not determine the current Git branch.")

        run(["git", "push", "origin", branch])
        print()
        print(f"Done. Uploaded commit to origin/{branch}.")
        print("GitHub Actions will rebuild and publish the dashboard from the uploaded data.")
        return 0
    except Exception as exc:
        print()
        print(f"Upload failed: {exc}")
        print("Please check the message above, then run this tool again.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
