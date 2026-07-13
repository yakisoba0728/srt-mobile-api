#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from srt_mobile_api import SrtClient, SrtConfig, TrainSearchQuery
from srt_mobile_api.live import read_credentials_from_env, run_live_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SRT read-only app API smoke checks")
    parser.add_argument("--date", required=True, help="YYYYMMDD departure date")
    parser.add_argument("--depart-code", default="0551")
    parser.add_argument("--depart-name", default="수서")
    parser.add_argument("--arrive-code", default="0020")
    parser.add_argument("--arrive-name", default="부산")
    parser.add_argument("--device-key", default=os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF"))
    args = parser.parse_args()
    login_id, password = read_credentials_from_env()
    query = TrainSearchQuery(
        departure_station_code=args.depart_code,
        arrival_station_code=args.arrive_code,
        departure_date=args.date,
        departure_station_name=args.depart_name,
        arrival_station_name=args.arrive_name,
    )
    client = SrtClient(SrtConfig(device_key=args.device_key))
    try:
        result = run_live_smoke(client, login_id=login_id, password=password, query=query)
    finally:
        client.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
