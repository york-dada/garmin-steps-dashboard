from __future__ import annotations

import csv  # Imported so PyInstaller bundles build_dashboard.py dependencies.
import datetime as dt
import html
import importlib.util
import io
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

_PYINSTALLER_HINTS = (asdict, csv, dataclass, html, io, Iterable, json)


def find_repo_root() -> Path:
    starts = [Path.cwd()]
    if getattr(sys, "frozen", False):
        starts.append(Path(sys.executable).resolve().parent)
    else:
        starts.append(Path(__file__).resolve().parent)

    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / ".git").exists() and (candidate / "build_dashboard.py").exists():
                return candidate

    return Path.cwd()


ROOT = find_repo_root()
STAGE_PATHS = [
    "README.md",
    "GarminUploadToGitHub.exe",
    "data/raw",
    "build_dashboard.py",
    "site/assets",
    ".github/workflows/build-and-deploy.yml",
    ".gitignore",
    "scripts/upload_to_github.py",
    "scripts/dev/upload_to_github.bat",
    "scripts/dev/build_upload_exe.bat",
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


def build_dashboard() -> None:
    script_path = ROOT / "build_dashboard.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing {script_path}")

    print("> build dashboard")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("garmin_dashboard_build", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.main()


def main() -> int:
    print("Garmin 步數資料上傳工具")
    print(f"資料夾: {ROOT}")
    print()

    try:
        git_output(["rev-parse", "--is-inside-work-tree"])
        build_dashboard()

        if not has_changes():
            print("沒有偵測到新的 CSV 或 dashboard 相關變更。")
            print("這次不會上傳到 GitHub。")
            return 0

        print()
        print("準備上傳這些變更:")
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
        if branch not in {"main", "master"}:
            raise RuntimeError(f"目前在 {branch} 分支，請切回 main 後再上傳，否則 dashboard 不會更新。")

        run(["git", "push", "origin", branch])
        print()
        print(f"完成，上傳到 origin/{branch} 了。")
        print("GitHub 會自動更新 dashboard，通常約 1 到 3 分鐘。")
        print("查看結果: https://york-dada.github.io/garmin-steps-dashboard/")
        return 0
    except Exception as exc:
        print()
        print(f"上傳失敗: {exc}")
        print("請檢查上面的錯誤訊息，修正後再執行一次。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    if getattr(sys, "frozen", False):
        input("\n看完訊息後，按 Enter 關閉視窗...")
    raise SystemExit(exit_code)
