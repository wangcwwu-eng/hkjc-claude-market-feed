# HKJC Claude Market Feed

Public, read-only HKJC football market feed for **independent Claude analysis**.

This repository deliberately contains **market data only**. It does not publish or import PPS, GGS, C2, H3, ChatGPT picks, Telegram signals, private model probabilities, or betting-account data.

## Live feed

Raw JSON:

`https://raw.githubusercontent.com/wangcwwu-eng/hkjc-claude-market-feed/main/data/latest.json`

The feed is refreshed by a standard public GitHub-hosted runner approximately every 10 minutes. GitHub scheduled jobs can start late; always use `frozen_at_hkt` inside the JSON as the actual point-in-time observation timestamp.

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

Only `PREEVENT` rows are published. In-play scores and running results are intentionally excluded.

## Independence contract

Every feed declares that it contains no model predictions, PPS, GGS, C2, H3, or betting selections. The collector calls HKJC's public football GraphQL endpoint directly and requires no HKJC login or betting-account credentials.

## Claude project instruction

> Before each prospective analysis, fetch the latest raw HKJC market feed from the fixed URL in this repository. Treat `frozen_at_hkt` as the PIT market timestamp. Use only the raw market information in this feed plus your own independently researched public information. Do not infer or request PPS, GGS, C2, H3, ChatGPT or other-model selections. If the feed cannot be fetched, has zero matches, or appears too stale for the analysis, state `HKJC MARKET FEED UNVERIFIED` and request screenshots only as fallback.

## Failure behavior

The collector fails closed: a zero-match pre-event result, malformed schema, duplicate fixture IDs, or a non-PREEVENT leak causes the workflow to fail rather than overwrite the last known good public feed.

The rolling feed is intentionally compact so Claude can retrieve it reliably. Full correct-score grids are not duplicated into the index; Claude can follow the per-match official HKJC all-odds URL when it needs that detail.\n\nNo Actions artifacts or large runners are used. Historical PIT states remain recoverable from ordinary Git history.\n