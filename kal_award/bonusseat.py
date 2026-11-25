"""Parser for Korean Air's award-seat API, confirmed from a real HAR capture.

Endpoint:  POST https://www.koreanair.com/api/hmp/bonusSeatView/bonusSeatView
Request:   {"departureAirport": "ICN", "arrivalAirport": "CDG", "departureDate": "20270801"}
           - one call returns the whole calendar month of departureDate
           - one direction per call; no cabin parameter (all cabins come back)
           - the browser sends session headers (ksessionId, ...) — must be logged in
Response:
  {
    "departureAirport": "ICN", "arrivalAirport": "CDG",
    "departureAirportName": "...", "arrivalAirportName": "...",
    "flightList": [
      {"departureDate": "20270801",
       "flightDetailList": [
         {"departureTime": "10:05", "flightNumber": "KE901",
          "availableSeat": true,          # award seat open for this flight/cabin
          "bookingClass": "X",            # award booking class
          "frontBookingClass": "E"},      # cabin shown in the UI
         ...]}]}

Cabin codes observed (frontBookingClass / bookingClass):
  E / X  일반석 (economy)
  P / O  프레스티지석 (prestige)
  F / A  일등석 (first) — only on flights that have a first cabin
  U / Z  not yet confirmed against the UI (present on every ICN-CDG flight)
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

ENDPOINT = "/api/hmp/bonusSeatView/bonusSeatView"
CABINS = {"economy": "E", "prestige": "P", "first": "F"}


@dataclass(frozen=True)
class Flight:
    flight_number: str
    departure_time: str
    booking_class: str


def is_bonus_capture(cap: dict) -> bool:
    return ENDPOINT in cap.get("url", "") and isinstance(cap.get("response_json"), dict)


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def parse(captures: list[dict], cabin: str = "P"):
    """Return (available, covered).

    available: {"ICN-CDG": {date: [Flight, ...]}} — only dates with >=1 open flight
    covered:   {"ICN-CDG": set(dates the response listed at all)}
    """
    available: dict[str, dict[date, list[Flight]]] = defaultdict(lambda: defaultdict(list))
    covered: dict[str, set[date]] = defaultdict(set)
    for cap in captures:
        if not is_bonus_capture(cap):
            continue
        body = cap["response_json"]
        route = f"{body['departureAirport']}-{body['arrivalAirport']}"
        for day in body.get("flightList") or []:
            d = _d(day["departureDate"])
            covered[route].add(d)
            for f in day.get("flightDetailList") or []:
                if f.get("frontBookingClass") == cabin and f.get("availableSeat") is True:
                    fl = Flight(f["flightNumber"], f.get("departureTime", ""), f.get("bookingClass", ""))
                    if fl not in available[route][d]:
                        available[route][d].append(fl)
    return ({r: dict(v) for r, v in available.items()}, dict(covered))


def request_body(origin: str, dest: str, month_first_day: date) -> str:
    return json.dumps({"arrivalAirport": dest, "departureAirport": origin,
                       "departureDate": month_first_day.strftime("%Y%m%d")}, separators=(",", ":"))
