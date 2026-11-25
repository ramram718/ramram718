"""Round-trip pairing of outbound / inbound available dates."""
from __future__ import annotations

from datetime import date


def round_trips(outbound: list[date], inbound: list[date],
                min_stay: int = 7, max_stay: int = 14) -> list[tuple[date, date, int]]:
    """All (out, back, nights) with min_stay <= (back - out).days <= max_stay."""
    back_set = sorted(set(inbound))
    res = []
    for o in sorted(set(outbound)):
        for b in back_set:
            n = (b - o).days
            if n > max_stay:
                break
            if n >= min_stay:
                res.append((o, b, n))
    return res
