"""Open the Korean Air award-seat page in a real browser and record every
XHR/Fetch JSON exchange to disk.

The browser uses a persistent profile (.browser_profile/), so you log in to
SKYPASS once by hand and later runs reuse the session. The script never types
credentials and does nothing to hide that it is automated.

Each captured exchange is written to captures/<run>/NNN.json as:
    {"url", "method", "status", "resource_type", "request_post_data",
     "response_json"}
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

URL = "https://www.koreanair.com/booking/book-and-manage/award-seat-availability"
HOST_RE = re.compile(r"^https://([a-z0-9-]+\.)*koreanair\.com/", re.I)
# Static/analytics responses that are never availability data.
NOISE_RE = re.compile(r"(analytics|adobe|gtm|tag|log|i18n|message|banner|notice|\.js|\.css)", re.I)


@dataclass
class SearchCondition:
    origin: str = "ICN"
    destination: str = "CDG"
    cabin_label: str = "프레스티지"
    adults: int = 1


def _try(step: str, fn) -> bool:
    try:
        fn()
        print(f"  [auto] {step}: ok")
        return True
    except Exception as e:  # selectors are best effort; manual fallback follows
        print(f"  [auto] {step}: skipped ({type(e).__name__})")
        return False


def try_autofill(page, cond: SearchCondition) -> None:
    """Best-effort form fill using visible text/roles.

    The site's DOM is not documented and changes, so every step may fail; you
    then finish the form by hand in the open browser window.
    """
    t = 4000

    def airport(label: str, code: str):
        page.get_by_text(label, exact=False).first.click(timeout=t)
        page.wait_for_timeout(500)
        page.keyboard.type(code, delay=80)  # types into whatever search box opened
        page.wait_for_timeout(1000)
        page.get_by_text(re.compile(rf"\b{code}\b")).first.click(timeout=t)

    _try("출발지 " + cond.origin, lambda: airport("출발지", cond.origin))
    _try("도착지 " + cond.destination, lambda: airport("도착지", cond.destination))
    _try("좌석 등급 " + cond.cabin_label,
         lambda: page.get_by_text(cond.cabin_label, exact=False).first.click(timeout=t))


def capture(out_dir: Path, headless: bool = False, autofill: bool = True,
            profile_dir: Path = Path(".browser_profile"),
            cond: SearchCondition | None = None, max_wait_s: int = 900) -> Path:
    from playwright.sync_api import sync_playwright

    cond = cond or SearchCondition()
    run_dir = out_dir / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    pending: list = []
    saved = 0

    done = threading.Event()

    def wait_enter():
        try:
            input()
        except EOFError:
            pass
        done.set()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile_dir), headless=headless, locale="ko-KR",
            timezone_id="Asia/Seoul", viewport={"width": 1400, "height": 950},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            rt = resp.request.resource_type
            if rt in ("xhr", "fetch") and HOST_RE.match(resp.url) and not NOISE_RE.search(resp.url.split("?")[0]):
                pending.append(resp)

        page.on("response", on_response)
        resp = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        status = resp.status if resp else None
        print(f"page status: {status}")
        if status and status >= 400:
            print("!! 사이트가 접근을 거부했습니다 (Akamai 차단 등). 브라우저 창에서 직접 확인하세요.")

        if autofill:
            page.wait_for_timeout(3000)
            try_autofill(page, cond)

        print(
            "\n=== 브라우저 창에서 진행하세요 ===\n"
            f" 1) (필요 시) SKYPASS 로그인\n"
            f" 2) {cond.origin} → {cond.destination}, {cond.cabin_label}석, 성인 {cond.adults}명 설정 후 [조회]\n"
            " 3) 달력을 2027년 8월 ~ 조회 가능한 마지막 달까지 넘겨 주세요 (가는 편/오는 편 모두)\n"
            " 4) 다 끝나면 이 터미널에서 Enter\n"
        )
        threading.Thread(target=wait_enter, daemon=True).start()

        deadline = time.time() + max_wait_s
        while not done.is_set() and time.time() < deadline:
            page.wait_for_timeout(500)  # pumps Playwright events
            while pending:
                saved += _save(pending.pop(0), run_dir, saved)
        page.wait_for_timeout(1000)
        while pending:
            saved += _save(pending.pop(0), run_dir, saved)
        ctx.close()

    print(f"\nsaved {saved} JSON exchanges -> {run_dir}")
    return run_dir


def _save(resp, run_dir: Path, idx: int) -> int:
    try:
        body = resp.json()
    except Exception:
        return 0  # not JSON
    req = resp.request
    rec = {
        "url": resp.url,
        "method": req.method,
        "status": resp.status,
        "resource_type": req.resource_type,
        "request_post_data": req.post_data,
        "response_json": body,
    }
    path = run_dir / f"{idx:03d}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  captured {path.name}: {req.method} {resp.status} {resp.url[:110]}")
    return 1
