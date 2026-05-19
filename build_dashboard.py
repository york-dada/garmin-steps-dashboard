#!/usr/bin/env python3
"""Build a static Garmin steps dashboard from CSV files in data/raw."""

from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SITE_DIR = ROOT / "site"


@dataclass(frozen=True)
class StepRecord:
    member: str
    calendar_date: str
    steps: int
    daily_goal: int
    goal_met: bool
    completion_rate: float | None
    weekday: str
    source_file: str


def normalize_header(value: str | None) -> str:
    return "".join(char.lower() for char in (value or "").strip() if char.isalnum())


def parse_int(value: str | None) -> int:
    cleaned = (value or "").strip().replace(",", "")
    return int(float(cleaned)) if cleaned else 0


def parse_date(value: str | None) -> str:
    cleaned = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            pass
    return cleaned


def is_number_like(value: str | None) -> bool:
    try:
        parse_int(value)
        return True
    except ValueError:
        return False


def is_date_like(value: str | None) -> bool:
    cleaned = (value or "").strip()
    return bool(cleaned) and (parse_date(cleaned) != cleaned or "/" in cleaned or "-" in cleaned)


def weekday_name(iso_date: str) -> str:
    try:
        return date.fromisoformat(iso_date).strftime("%A")
    except ValueError:
        return ""


def member_name(path: Path) -> str:
    return path.parent.name.replace("-", " ").replace("_", " ").strip().title()


def metric_values(row: list[str]) -> list[str]:
    if row and not row[0].strip():
        return [cell.strip() for cell in row[1:]]
    return [cell.strip() for cell in row]


def make_record(member: str, raw_date: str, raw_steps: str, raw_goal: str, source: Path) -> StepRecord:
    day = parse_date(raw_date)
    steps = parse_int(raw_steps)
    goal = parse_int(raw_goal)
    return StepRecord(
        member=member,
        calendar_date=day,
        steps=steps,
        daily_goal=goal,
        goal_met=goal > 0 and steps >= goal,
        completion_rate=round(steps / goal, 4) if goal else None,
        weekday=weekday_name(day),
        source_file=source.relative_to(ROOT).as_posix(),
    )


def parse_transposed(rows: list[list[str]], member: str, source: Path) -> list[StepRecord]:
    if len(rows) < 3:
        return []
    if len(rows[1]) >= 2 and is_date_like(rows[1][0]) and is_number_like(rows[1][1]):
        return []
    dates = metric_values(rows[0])
    steps = metric_values(rows[1])
    goals = metric_values(rows[2])
    return [
        make_record(member, dates[i], steps[i], goals[i], source)
        for i in range(min(len(dates), len(steps), len(goals)))
        if dates[i].strip()
    ]


def parse_csv_file(path: Path) -> list[StepRecord]:
    member = member_name(path)
    content = path.read_text(encoding="utf-8-sig")
    raw_rows = [row for row in csv.reader(io.StringIO(content)) if any(cell.strip() for cell in row)]
    transposed = parse_transposed(raw_rows, member, path)
    if transposed:
        return transposed

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError(f"{path} is empty or missing a header row.")

    header_map = {normalize_header(header): header for header in reader.fieldnames}
    date_keys = ["date", "day", "calendardate", "日期"]
    step_keys = ["steps", "stepcount", "totalsteps", "實際", "实际", "步數", "步数"]
    goal_keys = ["goal", "dailygoal", "target", "stepsgoal", "目標", "目标"]
    date_header = next((header_map[key] for key in date_keys if key in header_map), None)
    step_header = next((header_map[key] for key in step_keys if key in header_map), None)
    goal_header = next((header_map[key] for key in goal_keys if key in header_map), None)

    if (date_header is None or step_header is None) and len(reader.fieldnames) >= 3 and not reader.fieldnames[0].strip():
        date_header, step_header, goal_header = reader.fieldnames[:3]
    if date_header is None or step_header is None:
        raise ValueError(f"Could not identify date/steps columns in {path}. Headers: {reader.fieldnames}")

    records: list[StepRecord] = []
    for row in reader:
        raw_date = row.get(date_header, "")
        raw_steps = row.get(step_header, "")
        raw_goal = row.get(goal_header, "") if goal_header else ""
        if raw_date or raw_steps:
            records.append(make_record(member, raw_date, raw_steps, raw_goal, path))
    return records


def load_records() -> list[StepRecord]:
    csv_paths = sorted(RAW_DIR.glob("*/*.csv"), key=lambda path: (path.parent.name.lower(), path.name.lower()))
    if not csv_paths:
        raise FileNotFoundError("No CSV files found. Add files under data/raw/<member>/<file>.csv")

    winners: dict[tuple[str, str], tuple[tuple[float, str, str], StepRecord]] = {}
    for path in csv_paths:
        priority = (path.stat().st_mtime, path.name, path.as_posix())
        for record in parse_csv_file(path):
            key = (record.member.lower(), record.calendar_date)
            current = winners.get(key)
            if current is None or priority >= current[0]:
                winners[key] = (priority, record)
    return sorted((record for _, record in winners.values()), key=lambda record: (record.calendar_date, record.member.lower()))


def week_start_for(day: date) -> date:
    return date.fromordinal(day.toordinal() - day.weekday())


def weekly_summary(records: list[StepRecord]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str], list[StepRecord]] = {}
    for record in records:
        day = date.fromisoformat(record.calendar_date)
        buckets.setdefault((week_start_for(day).isoformat(), record.member), []).append(record)

    summaries: list[dict[str, object]] = []
    for (week_start_text, member), rows in sorted(buckets.items()):
        start = date.fromisoformat(week_start_text)
        end = date.fromordinal(start.toordinal() + 6)
        rows = sorted(rows, key=lambda row: row.calendar_date)
        total_steps = sum(row.steps for row in rows)
        total_goal = sum(row.daily_goal for row in rows)
        best = max(rows, key=lambda row: row.steps)
        lowest = min(rows, key=lambda row: row.steps)
        summaries.append({
            "week": f"{start.isoformat()} ~ {end.isoformat()}",
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "member": member,
            "total_steps": total_steps,
            "average_steps": round(total_steps / len(rows), 1),
            "total_goal": total_goal,
            "goal_met_days": sum(1 for row in rows if row.goal_met),
            "tracked_days": len(rows),
            "completion_rate": round(total_steps / total_goal, 4) if total_goal else None,
            "best_day": best.calendar_date,
            "best_day_steps": best.steps,
            "lowest_day": lowest.calendar_date,
            "lowest_day_steps": lowest.steps,
        })
    return summaries


def monthly_totals(records: list[StepRecord]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for record in records:
        month = record.calendar_date[:7]
        totals.setdefault(month, {})
        totals[month][record.member] = totals[month].get(record.member, 0) + record.steps
    return totals


def number(value: int | float) -> str:
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}"
    return f"{int(value):,}"


def pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.0f}%"


def render_html(records: list[StepRecord], summaries: list[dict[str, object]]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    latest_week_start = max((str(row["week_start"]) for row in summaries), default="")
    latest_week = [row for row in summaries if row["week_start"] == latest_week_start]
    latest_week_label = str(latest_week[0]["week"]) if latest_week else "尚無資料"
    total_latest_steps = sum(int(row["total_steps"]) for row in latest_week)
    winner = str(max(latest_week, key=lambda row: int(row["total_steps"]))["member"]) if latest_week else "尚無資料"
    max_week_steps = max((int(row["total_steps"]) for row in latest_week), default=1)
    latest_date = max((record.calendar_date for record in records), default="尚無資料")

    months = monthly_totals(records)
    latest_month = max(months, default="")
    month_rows = sorted(months.get(latest_month, {}).items(), key=lambda item: item[1], reverse=True)
    members = ", ".join(sorted({record.member for record in records})) or "尚無成員"

    leaderboard = "\n".join(
        f"""
        <article class="rank-card">
          <div class="rank-medal">{index}</div>
          <div class="rank-main">
            <div class="rank-line"><h3>{html.escape(str(row['member']))}</h3><strong>{number(int(row['total_steps']))} 步</strong></div>
            <p>平均 {number(float(row['average_steps']))} 步 / 達標 {row['goal_met_days']}/{row['tracked_days']} 天 / 完成率 {pct(row['completion_rate'])}</p>
            <div class="bar"><span style="width:{round(int(row['total_steps']) / max_week_steps * 100)}%"></span></div>
          </div>
        </article>
        """
        for index, row in enumerate(sorted(latest_week, key=lambda item: int(item["total_steps"]), reverse=True), start=1)
    )

    month_cards = "\n".join(
        f"<article class=\"mini-card\"><span>{html.escape(member)}</span><strong>{number(total)} 步</strong></article>"
        for member, total in month_rows
    )

    history_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(str(row['week']))}</td><td>{html.escape(str(row['member']))}</td>
          <td>{number(int(row['total_steps']))}</td><td>{number(float(row['average_steps']))}</td>
          <td>{row['goal_met_days']}/{row['tracked_days']}</td><td>{pct(row['completion_rate'])}</td>
          <td>{html.escape(str(row['best_day']))} ({number(int(row['best_day_steps']))})</td>
        </tr>
        """
        for row in sorted(summaries, key=lambda item: (str(item["week_start"]), int(item["total_steps"])), reverse=True)[:24]
    )

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Garmin 步數儀表板</title>
  <style>
    :root {{ --ink:#243238; --muted:#647277; --line:#d9e2df; --panel:rgba(255,255,255,.88); --green:#4f9d69; --coral:#e96b5c; --gold:#f5bd3d; --blue:#5d93c8; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); font-family:"Avenir Next","Noto Sans TC","Segoe UI",sans-serif; background:linear-gradient(135deg,#fff8ea 0%,#e9f6ee 48%,#eef5fb 100%); min-height:100vh; }}
    main {{ width:min(1120px,calc(100% - 28px)); margin:0 auto; padding:24px 0 42px; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:16px; align-items:stretch; }}
    .panel {{ background:var(--panel); border:1px solid rgba(36,50,56,.1); border-radius:8px; box-shadow:0 18px 50px rgba(48,72,68,.12); }}
    .headline {{ padding:clamp(24px,5vw,48px); }}
    .eyebrow {{ color:var(--coral); font-size:.82rem; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
    h1 {{ margin:10px 0 14px; font-size:clamp(2rem,5vw,4rem); line-height:1; letter-spacing:0; }}
    .lede {{ margin:0; max-width:60ch; color:var(--muted); font-size:1.03rem; line-height:1.7; }}
    .stats {{ display:grid; gap:12px; padding:14px; }}
    .stat {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .stat span,.mini-card span {{ display:block; color:var(--muted); font-size:.88rem; font-weight:800; }}
    .stat strong {{ display:block; margin-top:6px; font-size:clamp(1.2rem,3vw,1.65rem); }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr); gap:16px; margin-top:16px; }}
    .section {{ padding:20px; }} h2 {{ margin:0 0 14px; font-size:1.25rem; }}
    .rank-card {{ display:flex; gap:14px; align-items:center; background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; margin-top:10px; }}
    .rank-medal {{ width:42px; height:42px; display:grid; place-items:center; border-radius:50%; background:var(--gold); font-weight:900; flex:0 0 auto; }}
    .rank-main {{ min-width:0; flex:1; }} .rank-line {{ display:flex; gap:10px; justify-content:space-between; align-items:baseline; }}
    .rank-line h3 {{ margin:0; font-size:1.04rem; }} .rank-main p {{ margin:6px 0 10px; color:var(--muted); font-size:.92rem; }}
    .bar {{ height:12px; overflow:hidden; border-radius:999px; background:#e7ece9; }} .bar span {{ display:block; height:100%; background:linear-gradient(90deg,var(--green),var(--blue)); }}
    .mini-grid {{ display:grid; gap:10px; }} .mini-card {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; }} .mini-card strong {{ display:block; margin-top:6px; font-size:1.2rem; }}
    .table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; }} th,td {{ padding:12px 14px; text-align:left; border-bottom:1px solid var(--line); white-space:nowrap; font-size:.92rem; }} th {{ background:#f1f7f3; color:#3d555d; }}
    footer {{ margin-top:16px; color:var(--muted); font-size:.86rem; line-height:1.6; }}
    @media (max-width:820px) {{ main {{ width:min(100% - 20px,680px); padding-top:12px; }} .hero,.grid {{ grid-template-columns:1fr; }} .rank-line {{ display:block; }} th,td {{ padding:10px 12px; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="panel headline"><span class="eyebrow">Family Steps</span><h1>Garmin 步數儀表板</h1><p class="lede">CSV 手動上傳到 GitHub 後，雲端會自動重建這個頁面。資料來源只採用彙整後結果，不公開原始 CSV 內容。</p></div>
      <aside class="panel stats"><div class="stat"><span>最新週次</span><strong>{html.escape(latest_week_label)}</strong></div><div class="stat"><span>本週總步數</span><strong>{number(total_latest_steps)} 步</strong></div><div class="stat"><span>本週第一名</span><strong>{html.escape(winner)}</strong></div></aside>
    </section>
    <section class="grid"><div class="panel section"><h2>本週排行榜</h2>{leaderboard or '<p>尚無排行榜資料。</p>'}</div><div class="panel section"><h2>{html.escape(latest_month or '最新月份')} 月累計</h2><div class="mini-grid">{month_cards or '<p>尚無月統計資料。</p>'}</div></div></section>
    <section class="panel section" style="margin-top:16px"><h2>歷史週次</h2><div class="table-wrap"><table><thead><tr><th>週次</th><th>成員</th><th>總步數</th><th>日均</th><th>達標</th><th>完成率</th><th>最佳日</th></tr></thead><tbody>{history_rows}</tbody></table></div></section>
    <footer>成員：{html.escape(members)}<br>最新資料日期：{html.escape(latest_date)}。產生時間：{generated_at}。</footer>
  </main>
</body>
</html>
"""


def write_outputs(records: list[StepRecord], summaries: list[dict[str, object]]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records": [asdict(record) for record in records],
        "weekly_summary": summaries,
        "monthly_totals": monthly_totals(records),
    }
    (PROCESSED_DIR / "steps.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SITE_DIR / "index.html").write_text(render_html(records, summaries), encoding="utf-8")


def main() -> None:
    records = load_records()
    summaries = weekly_summary(records)
    write_outputs(records, summaries)
    print(f"Processed {len(records)} unique day/member record(s).")
    print("Wrote data/processed/steps.json and site/index.html.")


if __name__ == "__main__":
    main()
