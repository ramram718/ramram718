"""Offline tests on SYNTHETIC captures (invented shapes, not real Korean Air
responses). They check the detection/parse/match logic only."""
import json
from datetime import date, timedelta
from pathlib import Path

from kal_award.match import round_trips
from kal_award.parse import FieldMap, detect_field_map, extract, load_captures
from kal_award.__main__ import main


def _write(d: Path, i: int, url: str, body, post=None):
    rec = {"url": url, "method": "POST" if post else "GET", "status": 200,
           "resource_type": "xhr", "request_post_data": post, "response_json": body}
    (d / f"{i:03d}.json").write_text(json.dumps(rec), encoding="utf-8")


OUT_OK = {date(2027, 8, 3), date(2027, 8, 10), date(2027, 9, 1)}
IN_OK = {date(2027, 8, 12), date(2027, 8, 20), date(2027, 8, 30), date(2027, 9, 9)}


def days(start=date(2027, 7, 25), n=60):
    return [start + timedelta(i) for i in range(n)]


def shape_a(tmp):
    """Route fields on records, cabins nested per day."""
    segs = []
    for o, t, ok in (("ICN", "CDG", OUT_OK), ("CDG", "ICN", IN_OK)):
        segs.append({"departureAirport": o, "arrivalAirport": t, "calendar": [
            {"departureDate": d.isoformat(), "cabins": [
                {"cabinClass": "ECONOMY", "seatStatus": "Y"},
                {"cabinClass": "PRESTIGE", "seatStatus": "Y" if d in ok else "N"}]}
            for d in days()]})
    _write(tmp, 0, "https://www.koreanair.com/api/i18n/ko", {"hello": "x"})
    _write(tmp, 1, "https://www.koreanair.com/api/award/calendar", {"data": {"segments": segs}})


def shape_b(tmp):
    """Direction only in request body, flags as YN columns, dates YYYYMMDD."""
    for i, (o, t, ok) in enumerate((("ICN", "CDG", OUT_OK), ("CDG", "ICN", IN_OK))):
        body = {"result": [{"flightDate": d.strftime("%Y%m%d"), "economyYn": "Y",
                            "prestigeYn": "Y" if d in ok else "N", "seq": k}
                           for k, d in enumerate(days())]}
        _write(tmp, i, "https://www.koreanair.com/api/award/avail",
               body, post=json.dumps({"from": o, "to": t, "cabin": "C"}))


def check(tmp):
    caps = load_captures(tmp)
    fm = detect_field_map(caps)
    res = extract(caps, fm, date_from=date(2027, 8, 1))
    got_out = {d for d, ok in res["ICN-CDG"].items() if ok}
    got_in = {d for d, ok in res["CDG-ICN"].items() if ok}
    assert got_out == OUT_OK and got_in == IN_OK, (fm, got_out, got_in)
    assert min(res["ICN-CDG"]) == date(2027, 8, 1)  # --from filter applied
    return fm


def test_shape_a(tmp_path):
    shape_a(tmp_path)
    fm = check(tmp_path)
    assert fm.avail_key == "seatStatus" and fm.cabin_key == "cabinClass"


def test_shape_b(tmp_path):
    shape_b(tmp_path)
    fm = check(tmp_path)
    assert fm.avail_key == "prestigeYn"


def test_pinned_map(tmp_path):
    shape_b(tmp_path)
    fm = FieldMap(date_key="flightDate", avail_key="prestigeYn")
    res = extract(load_captures(tmp_path), fm)
    assert {d for d, ok in res["ICN-CDG"].items() if ok} == OUT_OK


def test_round_trips():
    trips = round_trips(sorted(OUT_OK), sorted(IN_OK))
    assert trips == [(date(2027, 8, 3), date(2027, 8, 12), 9),
                     (date(2027, 8, 10), date(2027, 8, 20), 10),
                     (date(2027, 9, 1), date(2027, 9, 9), 8)]


def test_cli_dates(tmp_path, capsys):
    shape_a(tmp_path)
    main(["dates", str(tmp_path)])
    out = capsys.readouterr().out
    assert "프레스티지 가능 3일" in out and "2027-08-03(화) → 2027-08-12(목)  (9박)" in out


def test_menu_and_blocked_search_not_misdetected(tmp_path):
    """Regression for the first real run: only menus/holidays plus a blocked
    (non-JSON) search came back. Must not pick menu `updateDate`/`menuYn`,
    and must surface the blocked call."""
    from kal_award.parse import describe
    menu = {"gnb": {"menuList": [{"menuYn": "Y" if i % 9 else "N", "updateDate": "2024-07-29 17:10",
                                  "menuText": f"m{i}"} for i in range(50)]}}
    _write(tmp_path, 0, "https://www.koreanair.com/api/hmp/main/getGnb?country=kr", menu)
    _write(tmp_path, 1, "https://www.koreanair.com/api/et/uiCommon/c/g/getHoliDeInfo?year=2027",
           {"holiDayItems": [{"date": "20270101", "dateName": "x"}]})
    rec = {"url": "https://www.koreanair.com/api/award/search", "method": "POST", "status": 403,
           "resource_type": "xhr", "request_post_data": "{}", "response_json": None,
           "response_text_preview": "<HTML>Access Denied</HTML>"}
    (tmp_path / "002.json").write_text(json.dumps(rec), encoding="utf-8")
    caps = load_captures(tmp_path)
    assert detect_field_map(caps, today=date(2026, 11, 25)) is None
    text = describe(caps)
    assert "Access Denied" in text and "002.json" in text


def test_har_import(tmp_path, monkeypatch):
    """HAR saved from the user's own Chrome -> same pipeline (synthetic)."""
    import base64
    from kal_award.har import import_har
    entries = []
    for o, t, ok in (("ICN", "CDG", OUT_OK), ("CDG", "ICN", IN_OK)):
        body = json.dumps({"result": [{"flightDate": d.strftime("%Y%m%d"), "prestigeYn": "Y" if d in ok else "N"}
                                      for d in days()]})
        entries.append({"request": {"method": "POST", "url": "https://www.koreanair.com/api/award/x",
                                    "postData": {"text": json.dumps({"from": o, "to": t})}},
                        "response": {"status": 200, "content": {"mimeType": "application/json",
                                     "encoding": "base64", "text": base64.b64encode(body.encode()).decode()}}})
    entries.append({"request": {"method": "GET", "url": "https://www.koreanair.com/main.js"},
                    "response": {"status": 200, "content": {"mimeType": "text/javascript", "text": "x"}}})
    entries.append({"request": {"method": "GET", "url": "https://other.example.com/api"},
                    "response": {"status": 200, "content": {"mimeType": "application/json", "text": "{}"}}})
    har = tmp_path / "a.har"
    har.write_text(json.dumps({"log": {"entries": entries}}), encoding="utf-8")
    run = import_har(har, tmp_path / "captures")
    assert len(list(run.glob("*.json"))) == 2
    check(run)
