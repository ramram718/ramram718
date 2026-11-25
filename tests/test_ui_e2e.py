"""End-to-end run of `python -m kal_award ui` against the local fake page."""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def test_ui_flow_against_fake_site(tmp_path, monkeypatch, capsys):
    pytest.importorskip("playwright")
    import fake_ui_site as f
    import kal_award.ui_search as u
    from kal_award.__main__ import main

    threading.Thread(target=f.srv.serve_forever, daemon=True).start()
    port = f.srv.server_address[1]
    orig = u.run_ui

    def patched(*a, **k):
        k.update(page_url=f"http://127.0.0.1:{port}/award", headless=True,
                 profile_dir=tmp_path / "prof", out_dir=tmp_path / "captures", response_timeout_s=8)
        return orig(*a, **k)

    monkeypatch.setattr(u, "run_ui", patched)
    try:
        main(["ui"])
    except Exception as e:  # no browser available in this environment
        if "Executable doesn't exist" in str(e):
            pytest.skip("chromium not installed")
        raise
    finally:
        f.srv.shutdown()
    out = capsys.readouterr().out
    assert "2027-09-03(금)  KE901" in out and "2027-09-17(금)" in out      # P open (17 also has U)
    assert "2027-09-05" not in out and "2027-09-06" not in out            # U-only days excluded
    assert "2027-09-03(금) → 2027-09-12(일)  (9박)" in out
    assert "쿠키 안내 닫음: [필수 쿠키만 허용]" in out
    assert "가는 날: 일치 (2일)" in out and "오는 날: 일치 (2일)" in out
