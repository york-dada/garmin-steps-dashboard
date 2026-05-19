#!/usr/bin/env python3
"""Build a static Garmin steps dashboard from manually exported CSV files."""

from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SITE_DIR = ROOT / "site"
STEPS_JSON = PROCESSED_DIR / "steps.json"


@dataclass(frozen=True)
class StepRecord:
    member: str
    calendar_date: str
    steps: int
    daily_goal: int
    goal_met: bool
    completion_rate: float | None
    step_gap: int | None
    weekday: str
    source_file: str


@dataclass(frozen=True)
class WeeklySummary:
    week: str
    week_start: str
    week_end: str
    member: str
    total_steps: int
    average_steps: float
    total_goal: int
    goal_met_days: int
    tracked_days: int
    completion_rate: float | None
    best_day: str
    best_day_steps: int
    lowest_day: str
    lowest_day_steps: int


def normalize_header(value: str | None) -> str:
    return "".join(char.lower() for char in (value or "").strip() if char.isalnum())


def parse_int(value: str | None) -> int:
    cleaned = (value or "").strip().replace(",", "")
    return int(float(cleaned)) if cleaned else 0


def parse_date_value(value: str | None) -> str:
    cleaned = (value or "").strip()
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            continue
    return cleaned


def is_number_like(value: str | None) -> bool:
    try:
        parse_int(value)
        return True
    except ValueError:
        return False


def is_date_like(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    parsed = parse_date_value(value)
    return parsed != value.strip() or "/" in value or "-" in value


def weekday_name(iso_date: str) -> str:
    try:
        return date.fromisoformat(iso_date).strftime("%A")
    except ValueError:
        return ""


def display_member(member_dir: Path) -> str:
    return member_dir.name.replace("-", " ").replace("_", " ").strip().title()


def metric_row_values(row: list[str]) -> list[str]:
    if row and not row[0].strip():
        return [value.strip() for value in row[1:]]
    return [value.strip() for value in row]


def make_record(member: str, raw_date: str, raw_steps: str, raw_goal: str, source_file: Path) -> StepRecord:
    calendar_date = parse_date_value(raw_date)
    steps = parse_int(raw_steps)
    goal = parse_int(raw_goal)
    goal_met = goal > 0 and steps >= goal
    return StepRecord(
        member=member,
        calendar_date=calendar_date,
        steps=steps,
        daily_goal=goal,
        goal_met=goal_met,
        completion_rate=round(steps / goal, 4) if goal else None,
        step_gap=steps - goal if goal else None,
        weekday=weekday_name(calendar_date),
        source_file=source_file.relative_to(ROOT).as_posix(),
    )


def parse_transposed_rows(raw_rows: list[list[str]], member: str, source_file: Path) -> list[StepRecord]:
    if len(raw_rows) < 3:
        return []
    if len(raw_rows[1]) >= 2 and is_date_like(raw_rows[1][0]) and is_number_like(raw_rows[1][1]):
        return []
    dates = metric_row_values(raw_rows[0])
    steps = metric_row_values(raw_rows[1])
    goals = metric_row_values(raw_rows[2])
    return [
        make_record(member, dates[index], steps[index], goals[index], source_file)
        for index in range(min(len(dates), len(steps), len(goals)))
        if dates[index].strip()
    ]


def parse_csv_file(path: Path) -> list[StepRecord]:
    member = display_member(path.parent)
    content = path.read_text(encoding="utf-8-sig")
    raw_rows = [row for row in csv.reader(io.StringIO(content)) if any(cell.strip() for cell in row)]
    transposed = parse_transposed_rows(raw_rows, member, path)
    if transposed:
        return transposed

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError(f"{path} is empty or missing a header row.")

    header_map = {normalize_header(header): header for header in reader.fieldnames}
    date_candidates = ["date", "day", "calendardate", "日期"]
    step_candidates = ["steps", "stepcount", "totalsteps", "實際", "实际", "步數", "步数"]
    goal_candidates = ["goal", "dailygoal", "target", "stepsgoal", "目標", "目标"]

    date_header = next((header_map[key] for key in date_candidates if key in header_map), None)
    step_header = next((header_map[key] for key in step_candidates if key in header_map), None)
    goal_header = next((header_map[key] for key in goal_candidates if key in header_map), None)

    if (date_header is None or step_header is None) and len(reader.fieldnames) >= 3 and not reader.fieldnames[0].strip():
        date_header = reader.fieldnames[0]
        step_header = reader.fieldnames[1]
        goal_header = reader.fieldnames[2]

    if date_header is None or step_header is None:
        headers = ", ".join(reader.fieldnames)
        raise ValueError(f"Could not identify date/steps columns in {path}. Headers found: {headers}")

    records: list[StepRecord] = []
    for row in reader:
        raw_date = row.get(date_header, "")
        raw_steps = row.get(step_header, "")
        raw_goal = row.get(goal_header, "") if goal_header else ""
        if raw_date or raw_steps:
            records.append(make_record(member, raw_date, raw_steps, raw_goal, path))
    return records


def load_records(raw_dir: Path = RAW_DIR) -> list[StepRecord]:
    csv_paths = sorted(raw_dir.glob("*/*.csv"), key=lambda path: (path.parent.name.lower(), path.name.lower()))
    if not csv_paths:
        raise FileNotFoundError(f"No CSV files found under {raw_dir}. Expected data/raw/<member>/<file>.csv")

    winners: dict[tuple[str, str], tuple[tuple[float, str, str], StepRecord]] = {}
    for path in csv_paths:
        priority = (path.stat().st_mtime, path.name, path.as_posix())
        for record in parse_csv_file(path):
            key = (record.member.lower(), record.calendar_date)
            current = winners.get(key)
            if current is None or priority >= current[0]:
                winners[key] = (priority, record)
    return sorted((record for _, record in winners.values()), key=lambda record: (record.calendar_date, record.member.lower()))


def summarize_weeks(records: Iterable[StepRecord]) -> list[WeeklySummary]:
    buckets: dict[tuple[str, str], list[StepRecord]] = {}
    for record in records:
        try:
            day = date.fromisoformat(record.calendar_date)
        except ValueError:
            continue
        week_start = day.fromordinal(day.toordinal() - day.weekday())
        buckets.setdefault((week_start.isoformat(), record.member), []).append(record)

    summaries: list[WeeklySummary] = []
    for (week_start_text, member), week_records in sorted(buckets.items()):
        week_start = date.fromisoformat(week_start_text)
        week_end = week_start.fromordinal(week_start.toordinal() + 6)
        ordered = sorted(week_records, key=lambda record: record.calendar_date)
        total_steps = sum(record.steps for record in ordered)
        total_goal = sum(record.daily_goal for record in ordered)
        tracked_days = len(ordered)
        best = max(ordered, key=lambda record: record.steps)
        lowest = min(ordered, key=lambda record: record.steps)
        summaries.append(
            WeeklySummary(
                week=f"{week_start.isoformat()} ~ {week_end.isoformat()}",
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
                member=member,
                total_steps=total_steps,
                average_steps=round(total_steps / tracked_days, 1) if tracked_days else 0,
                total_goal=total_goal,
                goal_met_days=sum(1 for record in ordered if record.goal_met),
                tracked_days=tracked_days,
                completion_rate=round(total_steps / total_goal, 4) if total_goal else None,
                best_day=best.calendar_date,
                best_day_steps=best.steps,
                lowest_day=lowest.calendar_date,
                lowest_day_steps=lowest.steps,
            )
        )
    return summaries


def monthly_totals(records: Iterable[StepRecord]) -> dict[str, dict[str, int]]:
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


def render_dashboard(records: list[StepRecord], summaries: list[WeeklySummary]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    members = sorted({record.member for record in records})
    latest_date = max((record.calendar_date for record in records), default="")
    latest_week_start = max((summary.week_start for summary in summaries), default="")
    latest_week = [summary for summary in summaries if summary.week_start == latest_week_start]
    latest_week_label = latest_week[0].week if latest_week else "尚無資料"
    winner = max(latest_week, key=lambda summary: summary.total_steps).member if latest_week else "尚無資料"

    month_totals = monthly_totals(records)
    latest_month = max(month_totals, default="")
    latest_month_rows = sorted(month_totals.get(latest_month, {}).items(), key=lambda item: item[1], reverse=True)
    latest_week_records = [record for record in records if latest_week_start <= record.calendar_date <= (latest_week[0].week_end if latest_week else "")]

    def day_label(iso_date: str) -> str:
        try:
            day = date.fromisoformat(iso_date)
        except ValueError:
            return iso_date
        return f"{day.month}/{day.day}"

    champion_counts = {member: 0 for member in members}
    for week_start in sorted({summary.week_start for summary in summaries}):
        week_summaries = [summary for summary in summaries if summary.week_start == week_start]
        if week_summaries:
            champion = max(week_summaries, key=lambda summary: summary.total_steps)
            champion_counts[champion.member] = champion_counts.get(champion.member, 0) + 1
    top_champion_count = max(champion_counts.values(), default=0)

    champion_rows = "\n".join(
        f"""
        <article class="champion-row">
          <div class="champion-person">
            {'<span class="crown" aria-label="目前累積最多週冠軍">♛</span>' if count == top_champion_count and count > 0 else '<span class="crown-spacer" aria-hidden="true"></span>'}
            <strong>{html.escape(member)}</strong>
          </div>
          <div class="champion-meter" aria-label="{html.escape(member)} 累積週冠軍 {count} 次">
            <div class="champion-fill" style="width:{min(100, round(count / 5 * 100))}%"></div>
            <div class="champion-ticks" aria-hidden="true">{''.join('<span></span>' for _ in range(5))}</div>
          </div>
          <b>{count} 次</b>
        </article>
        """
        for member, count in sorted(champion_counts.items(), key=lambda item: item[1], reverse=True)
    )

    daily_charts = "\n".join(
        f"""
        <article class="chart-card">
          <div class="chart-head"><h3>{html.escape(member)}</h3><span>{sum(record.goal_met for record in member_records)}/{len(member_records)} 天達標</span></div>
          <div class="day-list">
            {''.join(
                f'''
                <div class="day-row {'is-met' if record.goal_met else 'is-miss'}">
                  <div class="day-meta"><strong>{day_label(record.calendar_date)}</strong><span>{number(record.steps)} / {number(record.daily_goal)} 步</span></div>
                  <div class="goal-track" aria-label="{html.escape(member)} {day_label(record.calendar_date)} 實際 {record.steps} 目標 {record.daily_goal}"><div class="actual-fill" style="width:{max(2, min(100, round(record.steps / max(record.daily_goal, 1) * 100)))}%"></div></div>
                  <span class="day-badge">{'達標' if record.goal_met else f'差 {number(abs(record.steps - record.daily_goal))}'}</span>
                </div>
                '''
                for record in member_records
            )}
          </div>
        </article>
        """
        for member in sorted({record.member for record in latest_week_records})
        for member_records in [[record for record in latest_week_records if record.member == member]]
    )

    leaderboard = "\n".join(
        f"""
        <article class="rank-card">
          <div class="rank-medal">{index}</div>
          <div class="rank-main"><div class="rank-line"><h3>{html.escape(summary.member)}</h3><strong>{number(summary.total_steps)} 步</strong></div><p>平均 {number(round(summary.average_steps))} 步</p></div>
        </article>
        """
        for index, summary in enumerate(sorted(latest_week, key=lambda item: item.total_steps, reverse=True), start=1)
    )

    month_cards = "\n".join(f"<article class=\"mini-card\"><span>{html.escape(member)}</span><strong>{number(total)} 步</strong></article>" for member, total in latest_month_rows)
    history_rows = "\n".join(
        f"""
        <tr><td>{html.escape(summary.week)}</td><td>{html.escape(summary.member)}</td><td>{number(summary.total_steps)}</td><td>{number(round(summary.average_steps))}</td><td>{summary.goal_met_days}/{summary.tracked_days}</td><td>{html.escape(summary.best_day)} ({number(summary.best_day_steps)})</td></tr>
        """
        for summary in sorted(summaries, key=lambda item: (item.week_start, item.total_steps), reverse=True)[:24]
    )
    member_options = ", ".join(html.escape(member) for member in members) or "尚無成員"

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>豬豬步數記分板</title>
  <style>
    :root {{ --ink:#243238; --muted:#647277; --line:#d9e2df; --panel:rgba(255,255,255,.86); --green:#4f9d69; --coral:#e96b5c; --gold:#f5bd3d; --blue:#5d93c8; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); font-family:"Avenir Next","Noto Sans TC","Segoe UI",sans-serif; background:linear-gradient(135deg,#fff8ea 0%,#e9f6ee 48%,#eef5fb 100%); min-height:100vh; }}
    main {{ width:min(1120px,calc(100% - 28px)); margin:0 auto; padding:24px 0 42px; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:16px; align-items:stretch; }}
    .panel {{ background:var(--panel); border:1px solid rgba(36,50,56,.1); border-radius:8px; box-shadow:0 18px 50px rgba(48,72,68,.12); backdrop-filter:blur(12px); }}
    .headline {{ padding:clamp(24px,5vw,48px); display:grid; grid-template-columns:minmax(0,1fr) 180px; gap:28px; align-items:center; }}
    h1 {{ margin:0 0 14px; font-size:clamp(1.8rem,4vw,3.35rem); line-height:1.05; letter-spacing:0; white-space:nowrap; }}
    .pig {{ width:min(180px,100%); justify-self:end; filter:drop-shadow(0 18px 22px rgba(95,67,54,.2)); }}
    .stats {{ display:grid; gap:12px; padding:14px; }}
    .stat {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .stat span,.mini-card span {{ display:block; color:var(--muted); font-size:.88rem; font-weight:800; }}
    .stat strong {{ display:block; margin-top:6px; font-size:clamp(1.2rem,3vw,1.65rem); }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin-top:16px; }}
    .section {{ padding:20px; }} h2 {{ margin:0 0 14px; font-size:1.25rem; }}
    .rank-card {{ display:flex; gap:14px; align-items:center; background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; margin-top:10px; }}
    .rank-medal {{ width:42px; height:42px; display:grid; place-items:center; border-radius:50%; background:var(--gold); font-weight:900; flex:0 0 auto; }}
    .rank-main {{ min-width:0; flex:1; }} .rank-line {{ display:flex; gap:10px; justify-content:space-between; align-items:baseline; }}
    .rank-line h3 {{ margin:0; font-size:1.04rem; }} .rank-main p {{ margin:6px 0 0; color:var(--muted); font-size:.92rem; }}
    .chart-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .chart-card,.mini-card,.rank-card,.champion-row {{ background:#fff; border:1px solid var(--line); border-radius:8px; }}
    .chart-card {{ padding:16px; }} .chart-head {{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:14px; }}
    .chart-head h3 {{ margin:0; font-size:1.08rem; }} .chart-head span {{ color:var(--muted); font-weight:800; font-size:.9rem; }}
    .day-list {{ display:grid; gap:12px; }} .day-row {{ display:grid; grid-template-columns:96px minmax(120px,1fr) 54px; gap:10px; align-items:center; }}
    .day-meta strong {{ display:block; font-size:.95rem; }} .day-meta span {{ display:block; color:var(--muted); font-size:.78rem; margin-top:2px; white-space:nowrap; }}
    .goal-track {{ height:18px; min-width:0; border-radius:999px; background:linear-gradient(90deg,#e3eee8,#f8fbf9); border:1px solid #d3dfda; overflow:hidden; box-shadow:inset 0 1px 3px rgba(36,50,56,.08); }}
    .actual-fill {{ height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--green),var(--blue)); box-shadow:0 4px 10px rgba(79,157,105,.18); }} .is-miss .actual-fill {{ background:linear-gradient(90deg,var(--coral),#f1a064); }}
    .day-badge {{ justify-self:end; min-width:48px; padding:5px 7px; border-radius:999px; background:#e8f5ec; color:#357950; font-size:.72rem; line-height:1; font-weight:900; text-align:center; white-space:nowrap; }} .is-miss .day-badge {{ background:#fff0ec; color:#c25e51; }}
    .champion-list,.mini-grid {{ display:grid; gap:12px; }} .champion-row {{ display:grid; grid-template-columns:150px minmax(0,1fr) 56px; gap:14px; align-items:center; background:linear-gradient(135deg,#fff,#fbfdf9); padding:14px; }}
    .champion-person {{ display:flex; align-items:center; gap:8px; min-width:0; }} .crown,.crown-spacer {{ width:24px; flex:0 0 24px; text-align:center; }} .crown {{ color:var(--gold); font-size:1.35rem; line-height:1; text-shadow:0 2px 0 rgba(36,50,56,.12); }}
    .champion-meter {{ position:relative; height:24px; overflow:hidden; border-radius:999px; background:#eef5f1; border:1px solid #d2dfd9; box-shadow:inset 0 1px 4px rgba(36,50,56,.08); }} .champion-fill {{ position:absolute; inset:0 auto 0 0; border-radius:inherit; background:linear-gradient(90deg,#f5bd3d 0%,#65ad79 52%,#5d93c8 100%); box-shadow:0 5px 14px rgba(93,147,200,.22); }}
    .champion-ticks {{ position:absolute; inset:0; display:grid; grid-template-columns:repeat(5,1fr); pointer-events:none; }} .champion-ticks span + span {{ border-left:1px solid rgba(255,255,255,.9); }} .champion-row b {{ justify-self:end; }}
    .mini-card {{ padding:14px; }} .mini-card strong {{ display:block; margin-top:6px; font-size:1.2rem; }} .table-wrap {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; }} th,td {{ padding:12px 14px; text-align:left; border-bottom:1px solid var(--line); white-space:nowrap; font-size:.92rem; }} th {{ background:#f1f7f3; color:#3d555d; }}
    footer {{ margin-top:16px; color:var(--muted); font-size:.86rem; line-height:1.6; }}
    @media (max-width:820px) {{ main {{ width:min(100% - 20px,680px); padding-top:12px; }} .hero,.grid,.headline,.chart-grid {{ grid-template-columns:1fr; }} .day-row {{ grid-template-columns:82px minmax(96px,1fr) 50px; gap:8px; }} .day-meta span {{ font-size:.72rem; }} .day-badge {{ min-width:46px; padding-inline:6px; font-size:.68rem; }} .champion-row {{ grid-template-columns:1fr; gap:10px; }} .champion-row b {{ justify-self:start; }} .pig {{ width:96px; justify-self:start; }} .rank-line {{ display:block; }} th,td {{ padding:10px 12px; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero"><div class="panel headline"><div><h1>豬豬步數記分板</h1></div><img class="pig" src="assets/pig.svg" alt="豬豬步數記分板插圖"></div><aside class="panel stats"><div class="stat"><span>最新週次</span><strong>{html.escape(latest_week_label)}</strong></div><div class="stat"><span>本週第一名</span><strong>{html.escape(winner)}</strong></div></aside></section>
    <section class="grid"><div class="panel section"><h2>本週排行榜</h2>{leaderboard or '<p>尚無排行榜資料。</p>'}</div><div class="panel section"><h2>{html.escape(latest_month or '最新月份')} 月累計</h2><div class="mini-grid">{month_cards or '<p>尚無月統計資料。</p>'}</div></div></section>
    <section class="panel section" style="margin-top:16px"><h2>累積週冠軍次數</h2><div class="champion-list">{champion_rows or '<p>尚無冠軍紀錄。</p>'}</div></section>
    <section class="panel section" style="margin-top:16px"><h2>本週每日步數</h2><div class="chart-grid">{daily_charts or '<p>尚無本週每日資料。</p>'}</div></section>
    <section class="panel section" style="margin-top:16px"><h2>歷史週次</h2><div class="table-wrap"><table><thead><tr><th>週次</th><th>成員</th><th>總步數</th><th>日均</th><th>達標</th><th>最佳日</th></tr></thead><tbody>{history_rows}</tbody></table></div></section>
    <footer>成員：{member_options}<br>最新資料日期：{html.escape(latest_date or '尚無資料')}。產生時間：{generated_at}。</footer>
  </main>
</body>
</html>
"""


def write_outputs(records: list[StepRecord], summaries: list[WeeklySummary]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records": [asdict(record) for record in records],
        "weekly_summary": [asdict(summary) for summary in summaries],
        "monthly_totals": monthly_totals(records),
    }
    STEPS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SITE_DIR / "index.html").write_text(render_dashboard(records, summaries), encoding="utf-8")


def main() -> None:
    records = load_records()
    summaries = summarize_weeks(records)
    write_outputs(records, summaries)
    print(f"Processed {len(records)} unique day/member record(s).")
    print(f"Wrote {STEPS_JSON.relative_to(ROOT)} and {(SITE_DIR / 'index.html').relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
