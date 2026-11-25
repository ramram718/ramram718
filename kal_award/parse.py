"""Find and parse the per-date award availability in captured JSON.

The real response schema is not known in advance, so this module
  1. summarises the structure of every captured response (`describe`),
  2. auto-detects which keys hold the date / availability / cabin / route
     (`detect_field_map`), printing the evidence so a human can confirm it,
  3. extracts {direction: sorted dates} with that (or a hand-written) map.
Once the real field names are confirmed, pin them in a map JSON file
(see field_map.example.json) and pass --map so nothing is guessed.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterator

DATE_RE = re.compile(r"^(\d{4})-?(\d{2})-?(\d{2})(?:$|[T ])")
AVAIL_KEY_RE = re.compile(r"(avail|seat|remain|status|open|yn$|flag|cnt|count|sold|award|bonus)", re.I)
DATE_KEY_RE = re.compile(r"(date|dt$|day|ymd)", re.I)
CABIN_KEY_RE = re.compile(r"(cabin|class|grade|cos$|bookingclass)", re.I)
ORIGIN_KEY_RE = re.compile(r"(origin|depart(ure)?(airport|loc|city)?(code)?$|^dep|^from|board)", re.I)
DEST_KEY_RE = re.compile(r"(dest|arriv(al)?(airport|loc|city)?(code)?$|^arr|^to$|^to[A-Z_]|off)", re.I)
PRESTIGE_RE = re.compile(r"(prestige|business|biz|^c$|^prs?$|^j$)", re.I)

TRUE_STR = {"y", "yes", "true", "o", "open", "available", "avail", "a", "1"}
FALSE_STR = {"n", "no", "false", "x", "closed", "soldout", "sold_out", "close",
             "notavailable", "not_available", "unavailable", "na", "0", "", "none"}


# --------------------------------------------------------------------------- io
def load_captures(run_dir: Path) -> list[dict]:
    recs = []
    for p in sorted(Path(run_dir).glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["_file"] = p.name
        recs.append(rec)
    return recs


# --------------------------------------------------------------------- helpers
def parse_date(v: Any) -> date | None:
    if not isinstance(v, (str, int)):
        return None
    m = DATE_RE.match(str(v))
    if not m:
        return None
    try:
        d = date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return d if 2000 <= d.year <= 2100 else None


def as_available(v: Any) -> bool | None:
    """Interpret one availability value; None = not availability-like."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v > 0
    if isinstance(v, str):
        s = v.strip().lower().replace(" ", "")
        if s in TRUE_STR:
            return True
        if s in FALSE_STR:
            return False
        if s.isdigit():
            return int(s) > 0
    return None


def walk(obj: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def norm_path(path: str) -> str:
    return re.sub(r"\[\d+\]", "[]", path)


def flat_records(obj: Any) -> Iterator[tuple[str, dict, dict]]:
    """Yield (path, record, ancestors_scalars) for every dict.

    Each record is the dict's own scalar fields, plus — for each list of
    dicts directly under it — one merged record per child, so that
    {"date": .., "cabins": [{"cabin": "C", "avail": "Y"}]} becomes
    {"date": .., "cabin": "C", "avail": "Y"}. Ancestor scalars (e.g. a route
    header above a list of days) are carried separately.
    """
    def rec(o, path, anc):
        if isinstance(o, dict):
            own = {k: v for k, v in o.items() if not isinstance(v, (dict, list))}
            child_lists = [(k, v) for k, v in o.items()
                           if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
            yield norm_path(path), own, anc
            for k, lst in child_lists:
                for c in lst:
                    cs = {ck: cv for ck, cv in c.items() if not isinstance(cv, (dict, list))}
                    if cs:
                        yield norm_path(f"{path}.{k}[]") + "+parent", {**own, **cs}, anc
            new_anc = {**anc, **own}
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    yield from rec(v, f"{path}.{k}", new_anc)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from rec(v, f"{path}[{i}]", anc)

    yield from rec(obj, "$", {})


# ------------------------------------------------------------------ describe
def schema(obj: Any, depth: int = 0, max_depth: int = 6, indent: str = "") -> str:
    """Compact type tree; lists show only their first element."""
    if depth > max_depth:
        return indent + "…\n"
    out = ""
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:40]:
            if isinstance(v, (dict, list)):
                tag = f"list[{len(v)}]" if isinstance(v, list) else "object"
                out += f"{indent}{k}: {tag}\n"
                out += schema(v, depth + 1, max_depth, indent + "  ")
            else:
                out += f"{indent}{k}: {type(v).__name__} = {json.dumps(v, ensure_ascii=False)[:60]}\n"
        if len(obj) > 40:
            out += f"{indent}… (+{len(obj) - 40} keys)\n"
    elif isinstance(obj, list) and obj:
        out += schema(obj[0], depth, max_depth, indent + "- ")
    return out


def date_bearing_score(body: Any) -> int:
    return sum(1 for _, v in walk(body) if parse_date(v))


def describe(captures: list[dict], top: int = 3) -> str:
    lines = []
    errs = [r for r in captures if r["status"] >= 400 or r.get("response_json") is None]
    if errs:
        lines.append("=== !! 에러/비-JSON 응답 (조회가 차단됐다면 여기에 나옵니다) ===")
        for r in errs:
            prev = (r.get("response_text_preview") or "").replace("\n", " ")[:200]
            lines.append(f"{r['_file']}  {r['method']:4} {r['status']}  {r['url'][:120]}\n      {prev}")
    cands = [r for r in captures if AWARD_URL_RE.search(r["url"]) and not UI_URL_RE.search(r["url"])]
    lines.append("\n=== 보너스 좌석 후보 엔드포인트 (URL 기준) ===")
    lines += [f"{r['_file']}  {r['method']:4} {r['status']}  {r['url'][:140]}" for r in cands] or [
        "(없음) — 조회 결과 API가 캡처되지 않았습니다."]
    body_caps = [r for r in captures if r.get("response_json") is not None and not UI_URL_RE.search(r["url"])]
    lines.append("\n=== 기타 API 응답 (날짜 값 개수순, UI/메뉴 제외) ===")
    ranked = sorted(body_caps, key=lambda r: -date_bearing_score(r["response_json"]))
    for r in ranked:
        lines.append(f"{r['_file']}  {r['method']:4} {r['status']}  dates={date_bearing_score(r['response_json']):4}  {r['url'][:120]}")
    shown = list(dict.fromkeys(id(r) for r in cands + ranked))
    by_id = {id(r): r for r in captures}
    for r in [by_id[i] for i in shown][:top]:
        if r.get("response_json") is None:
            continue
        lines.append(f"\n--- {r['_file']}  {r['method']} {r['url']}")
        if r.get("request_post_data"):
            lines.append("request body: " + str(r["request_post_data"])[:800])
        lines.append("response structure:")
        lines.append(schema(r["response_json"]))
    return "\n".join(lines)


# -------------------------------------------------------------- field map
@dataclass
class FieldMap:
    date_key: str
    avail_key: str
    cabin_key: str | None = None
    cabin_match: str | None = None     # regex the cabin value must match
    origin_key: str | None = None
    dest_key: str | None = None
    record_path: str | None = None     # normalised path the records live at
    evidence: dict = field(default_factory=dict)

    @classmethod
    def load(cls, p: Path) -> "FieldMap":
        return cls(**json.loads(Path(p).read_text(encoding="utf-8")))


UI_URL_RE = re.compile(r"(/uiCommon/|/api/hmp/main/|getHoliDeInfo|getGdprData|languageInfo|seoInfo)", re.I)
AWARD_URL_RE = re.compile(r"(award|bonus|mileage|avail|calendar|lowest|seat|redemption|skypass)", re.I)


def detect_field_map(captures: list[dict], today: date | None = None) -> FieldMap | None:
    """Score (record_path, date_key, avail_key) combos across all records.

    Only future dates count: seat availability is about upcoming flights,
    while menus/notices carry past `updateDate`-style stamps.
    """
    today = today or date.today()
    stats: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "vals": Counter(), "keys": Counter(),
                                                   "anc_keys": Counter(), "samples": []})
    for cap in captures:
        if cap.get("response_json") is None or UI_URL_RE.search(cap["url"]):
            continue
        for path, rec, anc in flat_records(cap["response_json"]):
            dkeys = [k for k, v in rec.items() if (d := parse_date(v)) and d >= today]
            if not dkeys:
                continue
            dkeys.sort(key=lambda k: (not DATE_KEY_RE.search(k), len(k)))
            dk = dkeys[0]
            for k, v in rec.items():
                if k == dk or as_available(v) is None:
                    continue
                s = stats[(path, dk, k)]
                s["n"] += 1
                s["vals"][str(v)] += 1
                s["keys"].update(rec.keys())
                s["anc_keys"].update(anc.keys())
                if len(s["samples"]) < 3:
                    s["samples"].append(rec)
    if not stats:
        return None

    def score(item):
        (path, dk, ak), s = item
        sc = s["n"]
        if AVAIL_KEY_RE.search(ak):
            sc *= 4
        if PRESTIGE_RE.search(ak):
            sc *= 3
        if len(s["vals"]) < 2:
            sc *= 0.3            # constant column: probably not availability
        if re.search(r"(price|amount|fare|mile|tax|fee|seq|no$|id$|index)", ak, re.I):
            sc *= 0.05
        return sc

    (path, dk, ak), s = max(stats.items(), key=score)
    keys = list(s["keys"]) + [k for k in s["anc_keys"] if k not in s["keys"]]
    cabin = next((k for k in keys if CABIN_KEY_RE.search(k)), None)
    origin = next((k for k in keys if ORIGIN_KEY_RE.search(k) and k not in (dk, ak)), None)
    dest = next((k for k in keys if DEST_KEY_RE.search(k) and k not in (dk, ak, origin)), None)
    return FieldMap(
        date_key=dk, avail_key=ak, cabin_key=cabin,
        cabin_match=PRESTIGE_RE.pattern if cabin else None,
        origin_key=origin, dest_key=dest, record_path=path,
        evidence={"records": s["n"], "avail_values": dict(s["vals"].most_common(8)),
                  "samples": s["samples"]},
    )


# --------------------------------------------------------------- extract
def _route_from_request(cap: dict, origin: str, dest: str) -> str | None:
    """Direction from the request when records carry no route fields."""
    text = (cap.get("url") or "") + " " + str(cap.get("request_post_data") or "")
    i, j = text.find(origin), text.find(dest)
    if i < 0 or j < 0:
        return None
    return f"{origin}-{dest}" if i < j else f"{dest}-{origin}"


def extract(captures: list[dict], fm: FieldMap, origin: str = "ICN", dest: str = "CDG",
            date_from: date | None = None, date_to: date | None = None) -> dict[str, dict[date, bool]]:
    """Return {"ICN-CDG": {date: available}, "CDG-ICN": {...}, maybe "unknown"}.

    A date is available if *any* matching record for that date says so
    (a day can have several flights).
    """
    cab_re = re.compile(fm.cabin_match, re.I) if fm.cabin_match else None
    out: dict[str, dict[date, bool]] = defaultdict(dict)
    for cap in captures:
        if cap.get("response_json") is None:
            continue
        req_dir = _route_from_request(cap, origin, dest)
        for path, rec, anc in flat_records(cap["response_json"]):
            if fm.record_path and path != fm.record_path:
                continue
            if fm.date_key not in rec or fm.avail_key not in rec:
                continue
            d = parse_date(rec[fm.date_key])
            av = as_available(rec[fm.avail_key])
            if d is None or av is None:
                continue
            if date_from and d < date_from or date_to and d > date_to:
                continue
            if fm.cabin_key and cab_re:
                cv = rec.get(fm.cabin_key, anc.get(fm.cabin_key))
                if cv is not None and not cab_re.search(str(cv)):
                    continue
            ctx = {**anc, **rec}
            o = str(ctx.get(fm.origin_key, "")).upper() if fm.origin_key else ""
            t = str(ctx.get(fm.dest_key, "")).upper() if fm.dest_key else ""
            if o and t and {o[:3], t[:3]} == {origin, dest}:
                direction = f"{o[:3]}-{t[:3]}"
            else:
                direction = req_dir or "unknown"
            out[direction][d] = out[direction].get(d, False) or av
    return dict(out)


def fm_to_json(fm: FieldMap) -> str:
    d = asdict(fm)
    d.pop("evidence", None)
    return json.dumps(d, ensure_ascii=False, indent=2)
