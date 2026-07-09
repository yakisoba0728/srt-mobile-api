# srt-mobile-api

SRT Android app WebView API analysis workspace.

The final merged library-oriented specification is:

- `docs/analysis/srt-app-api-library-spec-2026-07-09.md`

The reusable smoke/negative test harness is:

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
environment variables and avoids valid reservation/payment authorization by
default.

