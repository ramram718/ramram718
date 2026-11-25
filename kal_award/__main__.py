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
        print("\n다음 단계: python -m kal_award analyze")


def latest_run(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    runs = sorted(p for p in Path("captures").glob("*") if p.is_dir())
    if not runs:
        sys.exit("captures 폴더에 캡처가 없습니다. 먼저 `python -m kal_award capture`를 실행하세요.")
    print(f"(가장 최근 캡처 사용: {runs[-1]})")
    return runs[-1]


def cmd_har(a):
    from .har import import_har
    import_har(Path(a.har))
    print("다음 단계: python -m kal_award analyze")


def cmd_analyze(a):
    a.run = latest_run(a.run)
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


def _months(days) -> list[str]:
    return sorted({d.strftime("%Y-%m") for d in days})


def cmd_dates(a):
    from . import bonusseat
    a.run = latest_run(a.run)
    caps = load_captures(Path(a.run))
    start = date.fromisoformat(a.date_from) if a.date_from else date.min
    end = date.fromisoformat(a.date_to) if a.date_to else date.max
    fwd, rev = f"{a.origin}-{a.dest}", f"{a.dest}-{a.origin}"
    cabin_name = {"P": "프레스티지", "E": "일반석", "F": "일등석"}.get(a.cabin, a.cabin)

    if any(bonusseat.is_bonus_capture(c) for c in caps):
        avail, covered = bonusseat.parse(caps, a.cabin)
        print(f"(bonusSeatView API 응답 {sum(bonusseat.is_bonus_capture(c) for c in caps)}건 사용, 좌석 등급 코드 {a.cabin})")
    else:  # unknown schema: generic detection
        fm = FieldMap.load(Path(a.map)) if a.map else detect_field_map(caps)
        if not fm:
            sys.exit("보너스 좌석 응답을 찾지 못했습니다. 로그인 후 조회했는지 확인하고 `analyze`를 실행해 보세요.")
        res = extract(caps, fm, a.origin, a.dest)
        avail = {k: {d: [] for d, ok in v.items() if ok} for k, v in res.items()}
        covered = {k: set(v) for k, v in res.items()}

    picked = {}
    for name, key in (("가는 날", fwd), ("오는 날", rev)):
        cov = sorted(d for d in covered.get(key, ()) if start <= d <= end)
        days = sorted(d for d in avail.get(key, {}) if start <= d <= end)
        picked[key] = days
        span = f"{cov[0]} ~ {cov[-1]}" if cov else "-"
        print(f"\n[{name} {key}] 조회된 날짜 {len(cov)}일 ({span}; 월: {', '.join(_months(cov)) or '없음'})"
              f", {cabin_name} 가능 {len(days)}일")
        for d in days:
            fl = avail[key][d]
            extra = "  " + ", ".join(f"{f.flight_number} {f.departure_time}" for f in fl) if fl else ""
            print(f"   {fmt(d)}{extra}")
    out_m, in_m = set(_months(covered.get(fwd, ()))), set(_months(covered.get(rev, ())))
    if out_m != in_m:
        print(f"\n!! 가는 편/오는 편 조회 월이 다릅니다. 가는 편만: {sorted(out_m - in_m) or '-'}"
              f", 오는 편만: {sorted(in_m - out_m) or '-'}  → 빠진 달도 달력에서 넘겨 캡처해야 왕복 매칭이 정확합니다.")

    trips = round_trips(picked[fwd], picked[rev], a.min_stay, a.max_stay)
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
            p.add_argument("run", nargs="?", help="캡처 폴더 (생략 시 가장 최근)")
        if name == "analyze":
            p.add_argument("--top", type=int, default=3)
            p.set_defaults(fn=cmd_analyze)
        if name == "dates":
            p.add_argument("--map")
            p.add_argument("--from", dest="date_from", default="2027-08-01")
            p.add_argument("--to", dest="date_to")
            p.add_argument("--min-stay", type=int, default=7)
            p.add_argument("--max-stay", type=int, default=14)
            p.add_argument("--cabin", default="P", help="frontBookingClass: P=프레스티지, E=일반석, F=일등석")
            p.set_defaults(fn=cmd_dates)
    ph = sub.add_parser("har", help="크롬 개발자도구에서 저장한 HAR 파일 가져오기")
    ph.add_argument("har")
    ph.set_defaults(fn=cmd_har)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
