"""Shared browser launch settings."""
import os

# Keep Chromium's sandbox on (avoids the "--no-sandbox" warning bar on
# Windows/macOS). Chromium refuses to sandbox as root on Linux, so only there
# fall back to Playwright's default.
SANDBOX = not (hasattr(os, "geteuid") and os.geteuid() == 0)
