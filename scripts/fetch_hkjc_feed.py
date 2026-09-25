#!/usr/bin/env python3
"""Publish a sanitized, read-only HKJC football market feed.

Source: HKJC public GraphQL football endpoint.
Output: public pre-event market data only. No private model outputs, picks,
recommendations, account data, or betting-account credentials are used.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ENDPOINT = "https://info.cld.hkjc.com/graphql/base/"
HKT = ZoneInfo("Asia/Hong_Kong")
DEFAULT_ODDS_TYPES = ["HAD", "HDC", "HIL", "CRS"]

MATCH_LIST_QUERY = """
query matchList($startIndex: Int, $endIndex: Int,$startDate: String, $endDate: String, $matchIds: [String], $tournIds: [String], $fbOddsTypes: [FBOddsType]!, $fbOddsTypesM: [FBOddsType]!, $inplayOnly: Boolean, $featuredMatchesOnly: Boolean, $frontEndIds: [String], $earlySettlementOnly: Boolean, $showAllMatch: Boolean) {
    matches(startIndex: $startIndex,endIndex: $endIndex, startDate: $startDate, endDate: $endDate, matchIds: $matchIds, tournIds: $tournIds, fbOddsTypes: $fbOddsTypesM, inplayOnly: $inplayOnly, featuredMatchesOnly: $featuredMatchesOnly, frontEndIds: $frontEndIds, earlySettlementOnly: $earlySettlementOnly, showAllMatch: $showAllMatch) {
      id
      frontEndId
      matchDate
      kickOffTime
      status
      updateAt
      sequence
      esIndicatorEnabled
      homeTeam { id name_en name_ch }
      awayTeam { id name_en name_ch }
      tournament {
        id
        frontEndId
        nameProfileId
        isInteractiveServiceAvailable
        code
        name_en
        name_ch
      }
      isInteractiveServiceAvailable
      inplayDelay
      venue { code name_en name_ch }
      tvChannels { code name_en name_ch }
      liveEvents { id code }
      featureStartTime
      featureMatchSequence
      poolInfo {
        normalPools
        inplayPools
        sellingPools
        ntsInfo
        entInfo
        definedPools
      }
      runningResult {
        homeScore
        awayScore
        corner
        homeCorner
        awayCorner
      }
      runningResultExtra {
        homeScore
        awayScore
        corner
        homeCorner
        awayCorner
      }
      adminOperation { remark { typ } }
      foPools(fbOddsTypes: $fbOddsTypes) {
        id
        status
        oddsType
        instNo
        inplay
        name_ch
        name_en
        updateAt
        expectedSuspendDateTime
        lines {
          lineId
          status
          condition
          main
          combinations {
            combId
            str
            status
            offerEarlySettlement
            currentOdds
            selections {
              selId
              str
              name_ch
              name_en
            }
          }
        }
      }
    }
  }
"""


def _decode_response(raw: bytes, content_encoding: str | None) -> str:
    enc = (content_encoding or "").lower()
    if "gzip" in enc or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def graphql_request(variables: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    payload = json.dumps({"query": MATCH_LIST_QUERY, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
            "Origin": "https://bet.hkjc.com",
            "Referer": "https://bet.hkjc.com/ch/football/home",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = _decode_response(resp.read(), resp.headers.get("Content-Encoding"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = _decode_response(raw, exc.headers.get("Content-Encoding"))
        except Exception:
            detail = raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"HKJC GraphQL HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HKJC GraphQL connection failed: {exc}") from exc

    data = json.loads(body)
    if data.get("errors"):
        raise RuntimeError(
            "HKJC GraphQL errors: "
            + json.dumps(data["errors"], ensure_ascii=False)[:1000]
        )
    return data


def _variables(start_date: str | None, end_date: str | None, odds_types: list[str]) -> dict[str, Any]:
    return {
        "startIndex": None,
        "endIndex": None,
        "startDate": start_date,
        "endDate": end_date,
        "matchIds": None,
        "tournIds": None,
        "fbOddsTypes": odds_types,
        "fbOddsTypesM": odds_types,
        "featuredMatchesOnly": False,
        "frontEndIds": None,
        "earlySettlementOnly": False,
        "showAllMatch": False,
    }


def _match_date_iso(match: dict[str, Any]) -> str | None:
    value = match.get("matchDate")
    if not value:
        return None
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _invalid_argument_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "invalid queration arguments" in text or "invalid query arguments" in text


def fetch_window(start_date: str, end_date: str, odds_types: list[str]) -> list[dict[str, Any]]:
    try:
        data = graphql_request(_variables(start_date, end_date, odds_types))
        matches = (data.get("data") or {}).get("matches") or []
        if matches:
            return matches
    except RuntimeError as exc:
        if not _invalid_argument_error(exc):
            raise
        print(
            "WARN: HKJC rejected filtered arguments; retrying upcoming list without date filters",
            file=sys.stderr,
        )

    fallback = graphql_request(_variables(None, None, odds_types))
    rows = (fallback.get("data") or {}).get("matches") or []
    return [
        m
        for m in rows
        if (_match_date_iso(m) is None or start_date <= _match_date_iso(m) <= end_date)
    ]


def decimal_odds(value: Any) -> float | None:
    if value in (None, "", "---"):
        return None
    try:
        x = float(value)
        return x if x > 1.0 else None
    except (TypeError, ValueError):
        return None


def _team(team: dict[str, Any] | None) -> dict[str, Any]:
    team = team or {}
    return {
        "id": team.get("id"),
        "name_en": team.get("name_en"),
        "name_ch": team.get("name_ch"),
    }


def _tournament(tournament: dict[str, Any] | None) -> dict[str, Any]:
    tournament = tournament or {}
    return {
        "id": tournament.get("id"),
        "front_end_id": tournament.get("frontEndId"),
        "code": tournament.get("code"),
        "name_en": tournament.get("name_en"),
        "name_ch": tournament.get("name_ch"),
    }


def _selection(sel: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": sel.get("selId"),
        "code": sel.get("str"),
        "name_en": sel.get("name_en"),
        "name_ch": sel.get("name_ch"),
    }


def sanitize_pool(pool: dict[str, Any]) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for line in pool.get("lines") or []:
        combinations: list[dict[str, Any]] = []
        for comb in line.get("combinations") or []:
            odds = decimal_odds(comb.get("currentOdds"))
            if odds is None:
                continue
            combinations.append(
                {
                    "id": comb.get("combId"),
                    "code": comb.get("str"),
                    "status": comb.get("status"),
                    "odds": odds,
                    "selections": [_selection(s) for s in (comb.get("selections") or [])],
                }
            )
        if combinations:
            lines.append(
                {
                    "line_id": line.get("lineId"),
                    "status": line.get("status"),
                    "condition": line.get("condition"),
                    "main": line.get("main"),
                    "combinations": combinations,
                }
            )

    return {
        "id": pool.get("id"),
        "odds_type": pool.get("oddsType"),
        "status": pool.get("status"),
        "inplay": bool(pool.get("inplay")),
        "name_en": pool.get("name_en"),
        "name_ch": pool.get("name_ch"),
        "updated_at": pool.get("updateAt"),
        "expected_suspend_at": pool.get("expectedSuspendDateTime"),
        "lines": lines,
    }


def flatten_had(pools: list[dict[str, Any]]) -> dict[str, Any]:
    prices: dict[str, float] = {}
    updated_at = None
    for pool in pools:
        if pool.get("oddsType") != "HAD" or pool.get("inplay"):
            continue
        updated_at = pool.get("updateAt")
        for line in pool.get("lines") or []:
            for comb in line.get("combinations") or []:
                odd = decimal_odds(comb.get("currentOdds"))
                if odd is None:
                    continue
                labels = " ".join(
                    str(s.get("str") or s.get("name_en") or s.get("name_ch") or "")
                    for s in (comb.get("selections") or [])
                ).strip().lower()
                comb_str = str(comb.get("str") or "").strip().lower()
                text = f"{comb_str} {labels}"
                if comb_str in {"h", "home", "1"} or "home" in text or "主" in text:
                    prices.setdefault("home", odd)
                elif comb_str in {"d", "draw", "x"} or "draw" in text or "和" in text:
                    prices.setdefault("draw", odd)
                elif comb_str in {"a", "away", "2"} or "away" in text or "客" in text:
                    prices.setdefault("away", odd)
        if prices:
            break

    result: dict[str, Any] = {"odds": prices, "updated_at": updated_at}
    if all(k in prices for k in ("home", "draw", "away")):
        raw = {k: 1.0 / prices[k] for k in ("home", "draw", "away")}
        overround = sum(raw.values())
        result["overround"] = round(overround, 8)
        result["no_vig_prob"] = {
            k: round(raw[k] / overround, 8) for k in ("home", "draw", "away")
        }
    return result


def _compact_pool(pool: dict[str, Any]) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for line in pool.get("lines") or []:
        odds: dict[str, float] = {}
        for comb in line.get("combinations") or []:
            value = decimal_odds(comb.get("currentOdds"))
            if value is None:
                continue
            code = str(comb.get("str") or "").strip()
            if not code:
                selections = comb.get("selections") or []
                if selections:
                    code = str(selections[0].get("str") or "").strip()
            if code:
                odds[code] = value
        if odds:
            lines.append({
                "condition": line.get("condition"),
                "main": bool(line.get("main")),
                "odds": odds,
            })
    return {
        "updated_at": pool.get("updateAt"),
        "status": pool.get("status"),
        "lines": lines,
    }


def sanitize_match(match: dict[str, Any], allowed_odds_types: set[str]) -> dict[str, Any]:
    raw_pools = [
        p
        for p in (match.get("foPools") or [])
        if p.get("oddsType") in allowed_odds_types and not p.get("inplay")
    ]
    usable = [
        p for p in raw_pools
        if any(
            decimal_odds(c.get("currentOdds")) is not None
            for line in (p.get("lines") or [])
            for c in (line.get("combinations") or [])
        )
    ]
    by_type: dict[str, dict[str, Any]] = {}
    for pool in usable:
        typ = str(pool.get("oddsType") or "")
        if typ and typ not in by_type:
            by_type[typ] = pool

    match_id = str(match.get("id") or "")
    result = {
        "id": match.get("id"),
        "front_end_id": match.get("frontEndId"),
        "match_date": match.get("matchDate"),
        "kickoff": match.get("kickOffTime"),
        "status": match.get("status"),
        "updated_at": match.get("updateAt"),
        "home": _team(match.get("homeTeam")),
        "away": _team(match.get("awayTeam")),
        "tournament": _tournament(match.get("tournament")),
        "available_markets": sorted(by_type),
        "had": flatten_had(raw_pools),
        "hdc": _compact_pool(by_type["HDC"]) if "HDC" in by_type else None,
        "hil": _compact_pool(by_type["HIL"]) if "HIL" in by_type else None,
        "crs_available": "CRS" in by_type,
        "hkjc_all_odds_url": (
            f"https://bet.hkjc.com/ch/football/allodds/{match_id}" if match_id else None
        ),
    }
    return result

def build_feed(matches: list[dict[str, Any]], start_date: str, end_date: str, odds_types: list[str]) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    now_hkt = now_utc.astimezone(HKT)
    allowed = set(odds_types)

    preevent = [
        sanitize_match(m, allowed)
        for m in matches
        if str(m.get("status") or "").upper() == "PREEVENT"
    ]
    preevent = [m for m in preevent if m.get("id")]
    preevent.sort(key=lambda m: (str(m.get("kickoff") or ""), str(m.get("id") or "")))

    canonical_payload = json.dumps(
        preevent,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return {
        "schema_version": "hkjc-claude-market-feed-v1",
        "source": "HKJC public GraphQL",
        "source_endpoint": ENDPOINT,
        "scope": "PREEVENT_PUBLIC_MARKETS_ONLY",
        "independence_contract": {
            "contains_model_predictions": False,
            "contains_pps": False,
            "contains_ggs": False,
            "contains_c2": False,
            "contains_h3": False,
            "contains_betting_selections": False,
        },
        "frozen_at_utc": now_utc.isoformat(),
        "frozen_at_hkt": now_hkt.isoformat(),
        "window": {"start_date": start_date, "end_date": end_date},
        "odds_types": odds_types,
        "match_count": len(preevent),
        "market_payload_sha256": hashlib.sha256(canonical_payload).hexdigest(),
        "matches": preevent,
    }


def validate_feed(feed: dict[str, Any]) -> None:
    if feed.get("schema_version") != "hkjc-claude-market-feed-v1":
        raise ValueError("unexpected schema_version")
    if feed.get("scope") != "PREEVENT_PUBLIC_MARKETS_ONLY":
        raise ValueError("unexpected scope")
    if not feed.get("frozen_at_utc") or not feed.get("frozen_at_hkt"):
        raise ValueError("missing frozen timestamp")
    matches = feed.get("matches") or []
    if not matches:
        raise ValueError("HKJC returned zero PREEVENT matches; refusing false-success feed")
    ids = [str(m.get("id")) for m in matches]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate match ids")
    if any(str(m.get("status") or "").upper() != "PREEVENT" for m in matches):
        raise ValueError("non-PREEVENT match leaked into public feed")
    contract = feed.get("independence_contract") or {}
    keys = (
        "contains_model_predictions",
        "contains_pps",
        "contains_ggs",
        "contains_c2",
        "contains_h3",
        "contains_betting_selections",
    )
    if any(contract.get(k) is not False for k in keys):
        raise ValueError("independence contract failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", default="data/latest.json")
    parser.add_argument("--odds", nargs="+", default=DEFAULT_ODDS_TYPES)
    args = parser.parse_args()

    today_hkt = datetime.now(HKT).date()
    start_date = today_hkt.isoformat()
    end_date = (today_hkt + timedelta(days=max(args.days, 0))).isoformat()

    try:
        matches = fetch_window(start_date, end_date, args.odds)
        feed = build_feed(matches, start_date, end_date, args.odds)
        validate_feed(feed)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "matches": feed["match_count"],
                "frozen_at_hkt": feed["frozen_at_hkt"],
                "market_payload_sha256": feed["market_payload_sha256"],
                "out": str(out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
