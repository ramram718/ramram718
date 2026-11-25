"""CLI.

  python -m kal_award capture [--headless] [--no-autofill]
  python -m kal_award analyze captures/<run>
  python -m kal_award dates   captures/<run> [--map field_map.json] [--from 2027-08-01]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .match import round_trips
from .parse import FieldMap, describe, detect_field_map, extract, fm_to_json, load_captures

WEEKDAY = "월화수목금토일"


def fmt(d: date) -> str:
    return f"{d.isoformat()}({WEEKDAY[d.weekday()]})"


def cmd_capture(a):
    from .capture import SearchCondition, capture
    run = capture(Path(a.out), headless=a.headless, autofill=not a.no_autofill,
                  cond=SearchCondition(a.origin, a.dest))
    caps = load_captures(run)
    print(describe(caps))
    if caps:
        print(f"\n다음 단계: python -m kal_award dates {run}")


def cmd_analyze(a):
    caps = load_captures(Path(a.run))
    if not caps:
        sys.exit(f"no captures in {a.run}")
    print(describe(caps, top=a.top))
    fm = detect_field_map(caps)
    print("\n=== auto-detected field map ===")
    if not fm:
        print("날짜+가용성 형태의 필드를 찾지 못했습니다. 위 구조를 보고 field map을 직접 작성하세요.")
        return
    print(fm_to_json(fm))
    print("evidence:", {k: v for k, v in fm.evidence.items() if k != "samples"})
    for s in fm.evidence["samples"]:
        print("  sample:", s)


def cmd_dates(a):
    caps = load_captures(Path(a.run))
    fm = FieldMap.load(Path(a.map)) if a.map else detect_field_map(caps)
    if not fm:
        sys.exit("field map을 찾지 못했습니다. `analyze`로 구조를 확인하세요.")
    if not a.map:
        print("(auto-detected map — 실제 필드인지 analyze 출력으로 확인 후 --map으로 고정 권장)")
        print(fm_to_json(fm))
    start = date.fromisoformat(a.date_from) if a.date_from else None
    end = date.fromisoformat(a.date_to) if a.date_to else None
    res = extract(caps, fm, a.origin, a.dest, start, end)

    fwd, rev = f"{a.origin}-{a.dest}", f"{a.dest}-{a.origin}"
    for k in res:
        if k not in (fwd, rev):
            print(f"\n!! 방향을 판별하지 못한 레코드 {len(res[k])}건 ({k}). field map에 origin_key/dest_key 지정 필요.")
    out_days = sorted(d for d, ok in res.get(fwd, {}).items() if ok)
    in_days = sorted(d for d, ok in res.get(rev, {}).items() if ok)
    for name, key, days in (("가는 날", fwd, out_days), ("오는 날", rev, in_days)):
        checked = res.get(key, {})
        span = f"{min(checked)} ~ {max(checked)}" if checked else "-"
        print(f"\n[{name} {key}] 조회된 날짜 {len(checked)}일 ({span}), 프레스티지 가능 {len(days)}일")
        for d in days:
            print("  ", fmt(d))

    trips = round_trips(out_days, in_days, a.min_stay, a.max_stay)
    print(f"\n[왕복 조합] 체류 {a.min_stay}~{a.max_stay}일: {len(trips)}건")
    for o, b, n in trips:
        print(f"   {fmt(o)} → {fmt(b)}  ({n}박)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kal_award")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("capture", "analyze", "dates"):
        p = sub.add_parser(name)
        p.add_argument("--origin", default="ICN")
        p.add_argument("--dest", default="CDG")
        if name == "capture":
            p.add_argument("--out", default="captures")
            p.add_argument("--headless", action="store_true")
            p.add_argument("--no-autofill", action="store_true")
            p.set_defaults(fn=cmd_capture)
        else:
            p.add_argument("run")
        if name == "analyze":
            p.add_argument("--top", type=int, default=3)
            p.set_defaults(fn=cmd_analyze)
        if name == "dates":
            p.add_argument("--map")
            p.add_argument("--from", dest="date_from", default="2027-08-01")
            p.add_argument("--to", dest="date_to")
            p.add_argument("--min-stay", type=int, default=7)
            p.add_argument("--max-stay", type=int, default=14)
            p.set_defaults(fn=cmd_dates)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
