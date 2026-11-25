"""Import a HAR file saved from your own browser's DevTools.

Chrome: F12 -> Network tab -> run the search on the page -> right-click any
request -> "Save all as HAR with content". This module turns the JSON
responses in that file into the same captures/<run>/NNN.json layout that
`capture` writes, so `analyze` and `dates` work unchanged.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from .capture import HOST_RE, NOISE_RE, SENSOR_RE


def import_har(har_path: Path, out_dir: Path = Path("captures")) -> Path:
    har = json.loads(Path(har_path).read_text(encoding="utf-8-sig"))
    run_dir = out_dir / (time.strftime("%Y%m%d-%H%M%S") + "-har")
    run_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for e in har.get("log", {}).get("entries", []):
        req, resp = e.get("request", {}), e.get("response", {})
        url = req.get("url", "")
        base = url.split("?")[0]
        if not HOST_RE.match(base) or NOISE_RE.search(base) or SENSOR_RE.match(base):
            continue
        content = resp.get("content", {})
        text = content.get("text")
        if text is None:
            continue
        if content.get("encoding") == "base64":
            try:
                text = base64.b64decode(text).decode("utf-8", "replace")
            except Exception:
                continue
        try:
            body, preview = json.loads(text), None
        except ValueError:
            if "json" not in content.get("mimeType", "") and resp.get("status", 0) < 400:
                continue  # html/js/etc.
            body, preview = None, text[:600]
        rec = {
            "url": url,
            "method": req.get("method"),
            "status": resp.get("status", 0),
            "resource_type": e.get("_resourceType", "xhr"),
            "request_post_data": (req.get("postData") or {}).get("text"),
            "response_json": body,
            "response_text_preview": preview,
        }
        (run_dir / f"{n:03d}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(f"imported {n} koreanair.com API responses -> {run_dir}")
    return run_dir
