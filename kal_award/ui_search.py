"""Drive the award-seat page UI the way a person does, and record the
bonusSeatView responses the page itself requests.

Flow (selectors from someone who runs this page regularly):
  1. Wait for the heading "보너스 좌석 조회" (a 5-10 s "잠시만 기다려 주세요" loader comes first).
  2. From:  button "From 출발지" -> combobox "출발지 검색" -> option "서울/인천, 대한민국 ICN"
     To:    button "To 도착지"   -> combobox "도착지 검색" -> option "파리/샤를 드 골, 프랑스 CDG"
  3. button "탑승월 가는 달 오는 달" -> in group "2027" click "9월" (going) and "9월" (return)
     -> "선택". "선택"/"조회" are <kds-button_1> web components, so they are
     clicked with force=True, or at their on-screen centre if that fails.
  4. "조회" makes two POSTs to /api/hmp/bonusSeatView/bonusSeatView
     (outbound and return). Those responses are saved and parsed.
  5. Cross-check: each day button's accessible name lists its seat types,
     e.g. "1일, 수요일 일반석 보너스 프레스티지석 좌석승급"; days whose name has
     "프레스티지석 보너스" (not "좌석승급") are read from the 가는 날 / 오는 날 tabs.
"""
from __future__ import annotations

from .browser import SANDBOX

import json
import re
import threading
import time
from datetime import date
from pathlib import Path

PAGE_URL = "https://www.koreanair.com/booking/book-and-manage/award-seat-availability"
AIRPORT_OPTION = {
    "ICN": "서울/인천, 대한민국 ICN",
    "CDG": "파리/샤를 드 골, 프랑스 CDG",
}
DAY_NAME_RE = re.compile(r"^\s*(\d{1,2})일,\s*\S+요일")
PRESTIGE_AWARD = "프레스티지석 보너스"


COOKIE_BUTTONS = [  # narrowest consent first
    re.compile(r"필수.*(쿠키)?.*(허용|동의|저장)"),
    re.compile(r"(선택|설정).*(저장|확인)"),
    re.compile(r"(모두|전체|모든).*(허용|동의|수락)"),
]


def dismiss_cookie_banner(page) -> bool:
    """Close the '더 편리한 이용을 위해 쿠키를 사용합니다' layer if it is showing."""
    if not page.get_by_text("쿠키를 사용합니다").first.is_visible():
        return False
    for pat in COOKIE_BUTTONS:
        btn = page.get_by_role("button", name=pat)
        if btn.count() and btn.first.is_visible():
            name = btn.first.inner_text().strip()
            force_click(page, btn.first, "쿠키 " + name)
            print(f"  쿠키 안내 닫음: [{name}]")
            page.wait_for_timeout(800)
            return True
    return False


def wait_until_ready(page, timeout_s: int = 90) -> None:
    """Wait out the 5-10 s loader; close the cookie layer while waiting."""
    deadline = time.time() + timeout_s
    heading = page.get_by_role("heading", name="보너스 좌석 조회")
    from_btn = page.get_by_role("button", name="From 출발지")
    while time.time() < deadline:
        try:
            dismiss_cookie_banner(page)
        except Exception:
            pass
        if heading.first.is_visible() or from_btn.first.is_visible():
            dismiss_cookie_banner(page)
            return
        page.wait_for_timeout(1000)
    raise PageNotReady("'보너스 좌석 조회' 화면이 %d초 안에 나타나지 않았습니다" % timeout_s)


class PageNotReady(RuntimeError):
    pass


def dump_diagnostics(page, out_dir: Path) -> Path:
    """Screenshot + what is on screen, so a failure can be diagnosed remotely."""
    d = out_dir / (time.strftime("%Y%m%d-%H%M%S") + "-debug")
    d.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(d / "screen.png"), full_page=True)
    except Exception:
        pass
    info = {"url": page.url, "title": "", "headings": [], "buttons": [], "dialogs": []}
    try:
        info["title"] = page.title()
        info["headings"] = page.get_by_role("heading").all_inner_texts()[:40]
        info["buttons"] = [b.strip()[:60] for b in page.get_by_role("button").all_inner_texts() if b.strip()][:80]
        info["dialogs"] = [t.strip()[:200] for t in page.get_by_role("dialog").all_inner_texts()][:5]
    except Exception as e:
        info["error"] = repr(e)
    (d / "page.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n=== 진단 정보 ===")
    print(json.dumps(info, ensure_ascii=False, indent=1)[:3000])
    print(f"(화면 캡처: {d / 'screen.png'})")
    return d


def force_click(page, locator, what: str, timeout: int = 10000) -> None:
    """Click custom web-component buttons that swallow normal clicks."""
    locator.wait_for(state="visible", timeout=timeout)
    try:
        locator.click(force=True, timeout=timeout)
        return
    except Exception as e:
        print(f"  ({what}: force click failed: {type(e).__name__}; clicking by coordinates)")
    box = locator.bounding_box()
    if not box:
        raise RuntimeError(f"{what}: button not on screen")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def choose_airport(page, side: str, code: str) -> None:
    btn, box = ("From 출발지", "출발지 검색") if side == "from" else ("To 도착지", "도착지 검색")
    page.get_by_role("button", name=btn).click()
    combo = page.get_by_role("combobox", name=box)
    combo.wait_for(state="visible", timeout=10000)
    combo.fill(code)
    option_name = AIRPORT_OPTION.get(code)
    opt = (page.get_by_role("option", name=option_name) if option_name
           else page.get_by_role("option").filter(has_text=re.compile(rf"\b{code}$")))
    opt.first.click(timeout=10000)
    print(f"  {side}: {code}")


MONTH_TEXT_RE = re.compile(r"(20\d\d)\s*[.\-/년]\s*(\d{1,2})")


def _month_button(page):
    # Name changes after selection ("탑승월 가는 달 … 오는 달 …"), so match the prefix.
    return page.get_by_role("button", name=re.compile(r"^\s*탑승월")).first


def _selected_months(page) -> list[tuple[int, int]]:
    text = " ".join([_month_button(page).inner_text(), _month_button(page).get_attribute("aria-label") or ""])
    return [(int(y), int(m)) for y, m in MONTH_TEXT_RE.findall(text)]


def _click_month(page, m: date, which: str) -> None:
    dialog = page.get_by_role("dialog").last
    scope = dialog if dialog.count() and dialog.is_visible() else page
    tab = scope.get_by_role("tab", name=re.compile(which))  # e.g. a "오는 달" tab, if the modal has one
    if tab.count() and tab.first.is_visible():
        force_click(page, tab.first, f"{which} 탭")
        page.wait_for_timeout(500)
    btn = scope.get_by_role("group", name=str(m.year)).get_by_role("button", name=f"{m.month}월", exact=True)
    btn = btn.last if btn.count() > 1 else btn  # if 가는/오는 달 each have a month grid, the visible last one
    btn.click()
    page.wait_for_timeout(1000)  # let the modal switch from 가는 달 to 오는 달


def choose_months(page, out_month: date, in_month: date) -> None:
    want = [(out_month.year, out_month.month), (in_month.year, in_month.month)]
    for attempt in (1, 2):
        _month_button(page).click()
        page.wait_for_timeout(800)
        _click_month(page, out_month, "가는 달")
        _click_month(page, in_month, "오는 달")
        force_click(page, page.get_by_role("button", name="선택", exact=True), "선택")
        page.wait_for_timeout(800)
        got = _selected_months(page)
        shown = _month_button(page).inner_text().strip().replace("\n", " ")
        print(f"  탑승월 버튼 표시: {shown!r}")
        if len(got) >= 2 and got[:2] == want:
            print(f"  탑승월 확인: 가는 달 {out_month:%Y-%m}, 오는 달 {in_month:%Y-%m}")
            return
        if len(got) < 2 and attempt == 1:
            print("  !! 오는 달이 선택되지 않은 것 같아 다시 선택합니다")
            continue
        break
    if got != want:
        print(f"  !! 탑승월을 확인하지 못했습니다 (읽은 값 {got}); 조회 결과로 다시 확인합니다")


def read_prestige_days_from_dom(page, month: date) -> dict[str, list[date]]:
    """Return {tab name: [dates with 프레스티지석 보너스]} from day-button labels."""
    out: dict[str, list[date]] = {}
    tabs = page.get_by_role("tab")
    names = [tabs.nth(i).inner_text().strip() for i in range(tabs.count())]
    for i, name in enumerate(names):
        if not any(k in name for k in ("가는", "오는")):
            continue
        force_click(page, tabs.nth(i), f"tab {name}")
        page.wait_for_timeout(800)
        days = []
        for label in page.get_by_role("button", name=DAY_NAME_RE).evaluate_all(
                "els => els.map(e => e.getAttribute('aria-label') || e.innerText || '')"):
            m = DAY_NAME_RE.match(label)
            if m and PRESTIGE_AWARD in label:
                days.append(date(month.year, month.month, int(m[1])))
        out["가는 날" if "가는" in name else "오는 날"] = sorted(set(days))
    return out


def run_ui(origin: str = "ICN", dest: str = "CDG", out_month: date = date(2027, 9, 1),
           in_month: date | None = None, out_dir: Path = Path("captures"),
           profile_dir: Path = Path(".browser_profile"), headless: bool = False,
           page_url: str = PAGE_URL, executable_path: str | None = None,
           response_timeout_s: int = 40, login_wait_s: int = 600) -> tuple[Path, dict]:
    from playwright.sync_api import sync_playwright

    in_month = in_month or out_month
    responses: list = []
    with sync_playwright() as p:
        launch = dict(headless=headless, locale="ko-KR", timezone_id="Asia/Seoul",
                      viewport={"width": 1400, "height": 950},
                      chromium_sandbox=SANDBOX)  # no --no-sandbox warning bar
        if executable_path:
            ctx = p.chromium.launch_persistent_context(str(profile_dir), executable_path=executable_path, **launch)
        else:
            try:
                ctx = p.chromium.launch_persistent_context(str(profile_dir), channel="chrome", **launch)
            except Exception:
                ctx = p.chromium.launch_persistent_context(str(profile_dir), **launch)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", lambda r: "bonusSeatView" in r.url and responses.append(r))

        def search_once():
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            print("페이지 로딩 대기 (보너스 좌석 조회 제목)...")
            wait_until_ready(page)
            choose_airport(page, "from", origin)
            choose_airport(page, "to", dest)
            choose_months(page, out_month, in_month)
            responses.clear()
            force_click(page, page.get_by_role("button", name="조회", exact=True), "조회")
            print("조회 클릭, bonusSeatView 응답 대기...")
            end = time.time() + response_timeout_s
            while time.time() < end and len(responses) < 2:
                page.wait_for_timeout(500)
            if len(responses) == 1:
                print("  !! bonusSeatView 응답이 1건뿐입니다 — 오는 달이 선택되지 않았을 수 있습니다")
            return [r for r in responses]

        try:
            got = search_once()
        except Exception as e:
            print(f"\n!! 화면 조작 중 멈춤: {type(e).__name__}: {str(e).splitlines()[0]}")
            dump_diagnostics(page, out_dir)
            if not headless:
                print(">> 브라우저 창 상태를 확인한 뒤 이 터미널에서 Enter를 누르면 종료합니다.")
                done = threading.Event()
                threading.Thread(target=lambda: (input(), done.set()), daemon=True).start()
                while not done.is_set():
                    page.wait_for_timeout(500)
            ctx.close()
            raise RuntimeError("화면 조작 실패 — 위 진단 정보와 화면 캡처를 확인하세요") from None
        ok = [r for r in got if r.status == 200]
        if len(ok) < 2:
            print(f"\n!! bonusSeatView 정상 응답 {len(ok)}/2건 — 로그인이 필요할 수 있습니다.\n"
                  ">> 열린 브라우저 창에서 SKYPASS 로그인을 마친 뒤, 이 터미널에서 Enter를 누르세요.")
            done = threading.Event()
            threading.Thread(target=lambda: (input(), done.set()), daemon=True).start()
            deadline = time.time() + login_wait_s
            while not done.is_set() and time.time() < deadline:
                page.wait_for_timeout(500)  # keep the browser responsive
            if done.is_set():
                got = search_once()
                ok = [r for r in got if r.status == 200]
        records = []
        for r in got:
            try:
                body, preview = r.json(), None
            except Exception:
                body, preview = None, (r.text()[:600] if r.ok else f"HTTP {r.status}")
            records.append({"url": r.url, "method": r.request.method, "status": r.status,
                            "resource_type": r.request.resource_type,
                            "request_post_data": r.request.post_data,
                            "response_json": body, "response_text_preview": preview})
        dom = {}
        if out_month == in_month and len(ok) == 2:
            try:
                dom = read_prestige_days_from_dom(page, out_month)
            except Exception as e:
                print(f"  (화면 대조 생략: {type(e).__name__}: {e})")
        ctx.close()

    run = out_dir / (time.strftime("%Y%m%d-%H%M%S") + "-ui")
    run.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(records):
        (run / f"{i:03d}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(ok) < 2:
        raise RuntimeError(f"bonusSeatView 응답을 받지 못했습니다 (저장: {run})")
    return run, dom
