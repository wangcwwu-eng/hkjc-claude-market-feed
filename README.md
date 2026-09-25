# HKJC Claude Market Feed

Public, read-only HKJC football market feed for **independent Claude analysis**.

This repository deliberately contains **market data only**. It does not publish or import PPS, GGS, C2, H3, ChatGPT picks, Telegram signals, private model probabilities, or betting-account data.

## Live feed

Raw JSON:

`https://raw.githubusercontent.com/wangcwwu-eng/hkjc-claude-market-feed/main/data/latest.json`

The feed targets a refresh approximately every 5 minutes on a standard public GitHub-hosted runner. GitHub scheduled jobs can start late; always use `frozen_at_hkt` inside the JSON as the actual point-in-time observation timestamp.

## Published fields

- HKJC fixture / front-end IDs
- kickoff and match status
- home / away teams
- tournament
- compact public HKJC pre-event HAD, HDC and HIL prices
- CRS availability flag plus the official HKJC all-odds URL for on-demand detail
- deterministic HAD overround and no-vig market probabilities
- HKJC market update timestamps where supplied
- `market_payload_sha256` for change/provenance checks
- `last_seen_markets` for a recently disappeared HAD/HDC/HIL market, always explicitly tagged `STALE_LAST_SEEN` with its original PIT and age

Only `PREEVENT` rows are published. In-play scores and running results are intentionally excluded.

## Independence contract

Every feed declares that it contains no model predictions, PPS, GGS, C2, H3, or betting selections. The collector calls HKJC's public football GraphQL endpoint directly and requires no HKJC login or betting-account credentials.

## Claude project instruction

> Before each prospective analysis, fetch the latest raw HKJC market feed from the fixed URL in this repository. Treat `frozen_at_hkt` as the PIT market timestamp. Never treat a fixture as prospective once your current time is at or after its scheduled kickoff, even if the feed still says `PREEVENT`. If a market is absent from the latest feed, that means HKJC did not return valid current odds for that market at that PIT; it does not prove the market was never offered earlier. A `last_seen_markets` entry is historical context only and must never be treated as a current price. Use the per-match `hkjc_all_odds_url` for a fresh official check before asking for a screenshot. Use only the raw market information in this feed plus your own independently researched public information. Do not infer or request PPS, GGS, C2, H3, ChatGPT or other-model selections. If the feed cannot be fetched, has zero matches, or is older than about 8 minutes, state `HKJC MARKET FEED UNVERIFIED`; retry the official source first and request screenshots only as final fallback.

## Failure behavior

The collector fails closed: a zero-match pre-event result, malformed schema, duplicate fixture IDs, or a non-PREEVENT leak causes the workflow to fail rather than overwrite the last known good public feed.

The rolling feed is intentionally compact so Claude can retrieve it reliably. Full correct-score grids are not duplicated into the index; Claude can follow the per-match official HKJC all-odds URL when it needs that detail.

No Actions artifacts or large runners are used. Historical PIT states remain recoverable from ordinary Git history.

## Last-seen market semantics

If HAD, HDC or HIL disappears from a later HKJC snapshot, the feed can carry the most recent prior payload for up to six hours under `last_seen_markets`. Every such item is labelled `STALE_LAST_SEEN`, includes `observed_at_hkt` and `age_minutes_at_freeze`, and is informational only. It must not be used as a current executable price or silently substituted for a missing live market.
