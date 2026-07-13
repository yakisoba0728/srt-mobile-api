# srt-mobile-api

SRT Android app WebView API analysis workspace.

The final merged library-oriented specification is:

- `docs/analysis/srt-app-api-library-spec-2026-07-09.md`

The reusable read-only smoke runner is:

- `scripts/srt_app_api_smoke.py`

## Scope

This repository documents SRT Android app APIs under `app.srail.or.kr` and the
NetFunnel helper required by the app flow. It excludes external web APIs, real
payment authorization, and automatic production reservation creation.

## Local Artifacts

`srt.apk` and `build/` are intentionally ignored. They are local evidence
artifacts, not retained source files.

Expected APK identity if static evidence needs to be regenerated:

| Item | Value |
|---|---|
| SHA-256 | `60e894aef1e0345444bd6fd22e1ac87a15b27ac60211b2a21dc6c7738b9c50b9` |
| Size | `26,427,764` bytes |
| Package | `kr.co.srail.newapp` |
| Version | `2.0.41` / `versionCode=150` |

Regenerate evidence locally only when needed:

```bash
mkdir -p build
zipinfo -1 srt.apk | sort > build/apk-file-list.txt
apktool d -f srt.apk -o build/apktool
jadx -d build/jadx srt.apk
```

## Safety

Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or
card-shaped values in the repository. The smoke script reads credentials from
environment variables and does not issue reservation or payment requests.
`SrtConfig` pins app and NetFunnel traffic to the documented production HTTPS
origins; its host fields cannot be used to redirect requests to alternate servers.

## Python Package MVP

This repository now contains an installable Python client package under `src/srt_mobile_api`.

Default tests are offline:

```bash
pip install -e ".[test]"
pytest
```

### Read-only selector popups

`SrtClient` exposes the six runtime-evidenced selector popup reads:

- `get_station_selector(...)`
- `get_station_map_selector()`
- `get_date_selector(...)`
- `get_passenger_selector(...)`
- `get_seat_option_selector(...)`
- `get_train_group_selector(...)`

Each method posts only to its exact allowlisted `/common/ARA/` route and returns
the existing `HtmlPage`, so callers retain compatible `text` and `raw` access.
The live helper calls all six after booking-page hydration and reports only the
bounded integer `selectorLoadedCount`; it never emits popup HTML or extracted
popup text.

These APIs select search-form preferences only. The physical seat-selection
page, reservation, payment, refund, cancellation, `act_19`, ATA/ARD, native
bridges, and external seat maps remain excluded.

### Mutual verification

`get_mutual_verification()` manually performs the evidenced empty-form mutual
verification read and returns a repr-safe `MutualVerificationResult`. It is not
called automatically by login or search and does not start seat selection or a
reservation. The opted-in live helper calls it only after personal search and
reports `mutualVerificationLoaded`, never the verification value or raw JSON.

Live smoke is opt-in and limited to login plus read/query calls:

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
export SRT_TEST_DATE="<YYYYMMDD>"
export SRT_DEVICE_KEY="<device-key>"
export SRT_CHILD_COUNT=1
python3 -c "from srt_mobile_api.live import run_live_smoke_from_env; print(run_live_smoke_from_env())"
```

The live helper reports only booleans and bounded counts. It exercises one
non-adult passenger mapping in the example above and contains no `act_19` or
reservation path.

Reservation, payment, refund, cancellation, ARD, ATA, and native bridge flows are not implemented in this package version.
