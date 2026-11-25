"""CLI.

  python -m kal_award ui      [--out-month 2027-09 --in-month 2027-09]   # 화면 조작으로 조회
  python -m kal_award auto    [--origin ICN --dest CDG --from 2027-08-01]   # 자동 조회 + 결과 출력
  python -m kal_award import  kal_bonus_....json                            # 콘솔 스니펫 결과 가져오기
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


def cmd_auto(a):
    from .fetcher import FetchError, run_auto
    try:
        run = run_auto(a.origin, a.dest, date.fromisoformat(a.date_from), delay_s=a.delay)
    except FetchError as e:
        sys.exit(f"\n!! 조회 중단: {e}\n"
                 "자동화 브라우저가 막혔다면 README의 '콘솔 스니펫' 방법을 사용하세요.")
    a.run = str(run)
    cmd_dates(a)


def cmd_ui(a):
    from . import bonusseat
    from .parse import schema
    from .ui_search import run_ui
    om = date.fromisoformat(a.out_month + "-01")
    im = date.fromisoformat((a.in_month or a.out_month) + "-01")
    try:
        run, dom = run_ui(a.origin, a.dest, om, im, headless=a.headless)
    except RuntimeError as e:
        sys.exit(f"\n!! {e}")
    caps = [c for c in load_captures(run) if bonusseat.is_bonus_capture(c)]
    print(f"\n=== bonusSeatView 응답 {len(caps)}건 저장: {run} ===")
    for c in caps:
        print(f"요청: {c['request_post_data']}")
    if caps:
        print("응답 구조 (첫 번째):")
        print(schema(caps[0]["response_json"]))
    a.run, a.date_from, a.date_to = str(run), None, None
    cmd_dates(a)
    if dom:
        avail, _ = bonusseat.parse(caps, "P")
        print("\n=== 화면(버튼 라벨) 대조: '프레스티지석 보너스' ===")
        for tab, key in (("가는 날", f"{a.origin}-{a.dest}"), ("오는 날", f"{a.dest}-{a.origin}")):
            api_days = sorted(avail.get(key, {}))
            dom_days = dom.get(tab)
            if dom_days is None:
                print(f"  {tab}: 탭을 읽지 못함")
            elif dom_days == api_days:
                print(f"  {tab}: 일치 ({len(dom_days)}일)")
            else:
                print(f"  {tab}: !! 불일치 API={[d.day for d in api_days]} 화면={[d.day for d in dom_days]}")


def cmd_import(a):
    import json
    from .fetcher import save_records
    import time
    data = json.loads(Path(a.file).read_text(encoding="utf-8-sig"))
    recs = data["records"] if isinstance(data, dict) else data
    run = save_records(recs, Path("captures") / (time.strftime("%Y%m%d-%H%M%S") + "-import"))
    print(f"imported {len(recs)} responses -> {run}")
    a.run = str(run)
    cmd_dates(a)


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
    cabin_name = {"E": "일반석 보너스", "R": "프리미엄석 보너스", "G": "프리미엄석 좌석승급",
                  "P": "프레스티지 보너스", "U": "프레스티지 좌석승급",
                  "F": "일등석 보너스/좌석승급"}.get(a.cabin, a.cabin)

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
    in_range = lambda k: [d for d in covered.get(k, ()) if start <= d <= end]
    out_m, in_m = set(_months(in_range(fwd))), set(_months(in_range(rev)))
    if out_m != in_m:
        print(f"\n!! 가는 편/오는 편 조회 월이 다릅니다. 가는 편만: {sorted(out_m - in_m) or '-'}"
              f", 오는 편만: {sorted(in_m - out_m) or '-'}  → 빠진 달도 달력에서 넘겨 캡처해야 왕복 매칭이 정확합니다.")

    trips = round_trips(picked[fwd], picked[rev], a.min_stay, a.max_stay)
    print(f"\n[왕복 조합] 체류 {a.min_stay}~{a.max_stay}일: {len(trips)}건")
    for o, b, n in trips:
        print(f"   {fmt(o)} → {fmt(b)}  ({n}박)")


def _result_args(p):
    p.add_argument("--from", dest="date_from", default="2027-08-01")
    p.add_argument("--to", dest="date_to")
    p.add_argument("--min-stay", type=int, default=7)
    p.add_argument("--max-stay", type=int, default=14)
    p.add_argument("--cabin", default="P",
                   help="E 일반석, R 프리미엄석, G 프리미엄 승급, P 프레스티지(기본), U 프레스티지 승급, F 일등석")
    p.add_argument("--map")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kal_award")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ui", "auto", "import", "capture", "analyze", "dates"):
        p = sub.add_parser(name)
        p.add_argument("--origin", default="ICN")
        p.add_argument("--dest", default="CDG")
        if name == "ui":
            _result_args(p)
            p.add_argument("--out-month", default="2027-09", help="가는 달 YYYY-MM")
            p.add_argument("--in-month", help="오는 달 YYYY-MM (생략 시 가는 달과 같음)")
            p.add_argument("--headless", action="store_true")
            p.set_defaults(fn=cmd_ui)
        elif name == "auto":
            _result_args(p)
            p.add_argument("--delay", type=float, default=2.0, help="요청 간격(초), 최소 1")
            p.set_defaults(fn=cmd_auto)
        elif name == "import":
            p.add_argument("file")
            _result_args(p)
            p.set_defaults(fn=cmd_import)
        elif name == "capture":
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
            _result_args(p)
            p.set_defaults(fn=cmd_dates)
    ph = sub.add_parser("har", help="크롬 개발자도구에서 저장한 HAR 파일 가져오기")
    ph.add_argument("har")
    ph.set_defaults(fn=cmd_har)
    a = ap.parse_args(argv)
    if getattr(a, "delay", 2.0) < 1:
        a.delay = 1.0
    a.fn(a)


if __name__ == "__main__":
    main()
