"""Fetch award-seat months automatically from a logged-in browser session.

How it works
  1. Open the award-seat page in a browser window that keeps its own profile
     (.browser_profile/), so you log in once and later runs stay logged in.
  2. The page's own API calls carry the session header `ksessionId`; we read
     it from those requests (no clicking needed).
  3. From inside the page we POST the same API the calendar uses,
     /api/hmp/bonusSeatView/bonusSeatView, one month and one direction at a
     time, pausing between calls (default 2 s — slower than clicking through
     the calendar by hand).
  4. A direction stops at the last bookable date (when a month comes back
     short or empty). Responses go to captures/<run>-auto/ like any capture.

Nothing here hides that the browser is automated; if the site refuses a call
the run stops and reports it rather than retrying.
"""
from __future__ import annotations

import calendar
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .bonusseat import ENDPOINT, request_body

PAGE_URL = "https://www.koreanair.com/booking/book-and-manage/award-seat-availability"
API_URL = "https://www.koreanair.com" + ENDPOINT

# (status, text) for one POST body
PostFn = Callable[[str], tuple[int, str]]


class FetchError(RuntimeError):
    pass


def month_starts(first: date, limit: int = 14):
    y, m = first.year, first.month
    for _ in range(limit):
        yield date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_direction(post: PostFn, origin: str, dest: str, from_date: date,
                    delay_s: float = 2.0, sleep=time.sleep, log=print) -> list[dict]:
    """Fetch months from from_date until the booking window ends."""
    records = []
    for i, m in enumerate(month_starts(from_date)):
        if i:
            sleep(delay_s)
        body = request_body(origin, dest, m)
        status, text = post(body)
        try:
            js = json.loads(text)
        except ValueError:
            js = None
        if status != 200 or not isinstance(js, dict) or "flightList" not in js:
            raise FetchError(f"{origin}->{dest} {m:%Y-%m}: HTTP {status}, {text[:300]!r}")
        records.append({"url": API_URL, "method": "POST", "status": status, "resource_type": "fetch",
                        "request_post_data": body, "response_json": js, "response_text_preview": None})
        fl = js.get("flightList") or []
        last = max((datetime.strptime(d["departureDate"], "%Y%m%d").date() for d in fl), default=None)
        month_end = date(m.year, m.month, calendar.monthrange(m.year, m.month)[1])
        log(f"  {origin}->{dest} {m:%Y-%m}: {len(fl)}일" + (f" (마지막 {last})" if last else ""))
        if last is None or last < month_end:
            break  # booking window ends inside this month
    return records


def save_records(records: list[dict], run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(records):
        (run_dir / f"{i:03d}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return run_dir


# ------------------------------------------------------------- browser part
_JS_POST = """async ({url, body, ks}) => {
  const r = await fetch(url, {method: 'POST', credentials: 'same-origin', body,
    headers: {'Content-Type': 'application/json', 'Accept': 'application/json',
              'channel': 'pc', 'ksessionId': ks, 'timestamp': String(Date.now())}});
  return [r.status, await r.text()];
}"""


def run_auto(origin: str, dest: str, from_date: date, out_dir: Path = Path("captures"),
             profile_dir: Path = Path(".browser_profile"), delay_s: float = 2.0,
             login_wait_s: int = 600, headless: bool = False,
             page_url: str = PAGE_URL, executable_path: str | None = None) -> Path:
    from playwright.sync_api import sync_playwright

    session = {"ks": None}

    def on_request(req):
        ks = req.headers.get("ksessionid")
        if ks and "/api/" in req.url:
            session["ks"] = ks

    with sync_playwright() as p:
        launch = dict(headless=headless, locale="ko-KR", timezone_id="Asia/Seoul",
                      viewport={"width": 1300, "height": 900})
        if executable_path:
            ctx = p.chromium.launch_persistent_context(str(profile_dir), executable_path=executable_path, **launch)
        else:
            try:  # prefer the installed Google Chrome; fall back to Playwright's Chromium
                ctx = p.chromium.launch_persistent_context(str(profile_dir), channel="chrome", **launch)
            except Exception:
                ctx = p.chromium.launch_persistent_context(str(profile_dir), **launch)
        ctx.on("request", on_request)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)

        def post(body: str):
            st, tx = page.evaluate(_JS_POST, {"url": ENDPOINT, "body": body, "ks": session["ks"] or ""})
            return st, tx

        # Wait until a probe call works (i.e. the user is logged in).
        probe = request_body(origin, dest, from_date.replace(day=1))
        deadline, told = time.time() + login_wait_s, False
        while True:
            page.wait_for_timeout(3000)
            if session["ks"]:
                st, tx = post(probe)
                if st == 200 and '"flightList"' in tx:
                    break
            if not told:
                print("\n>> 열린 브라우저 창에서 SKYPASS 로그인을 해 주세요. "
                      "로그인되면 자동으로 조회를 시작합니다. (한 번 로그인하면 다음부터는 생략)")
                told = True
            if time.time() > deadline:
                ctx.close()
                raise FetchError("로그인 대기 시간 초과")

        print("로그인 확인. 조회 시작 (요청 간격 %.1f초)" % delay_s)
        records, error = [], None
        try:
            for o, d in ((origin, dest), (dest, origin)):
                records += fetch_direction(post, o, d, from_date, delay_s,
                                           sleep=lambda s: page.wait_for_timeout(int(s * 1000)))
        except FetchError as e:  # keep what we got, then report
            error = e
        finally:
            ctx.close()
    run = save_records(records, out_dir / (time.strftime("%Y%m%d-%H%M%S") + "-auto"))
    if error:
        raise FetchError(f"{error}  (그때까지 받은 {len(records)}건은 {run}에 저장)")
    return run
