#!/usr/bin/env python3
"""Drive the live SRT READ surface once and capture every RAW response.

This is the read-side counterpart to
``scripts/verify_reserve_cancel_roundtrip.py``. It logs in once, reuses the one
session, and walks as much of :class:`~srt_mobile_api.client.SrtClient`'s public
read surface as can be reached with arguments derived from real responses
(search picks a real train, and the seat/timetable/fare reads are then issued
for THAT train). Every exchange is written to disk **before** it is parsed, so a
parser that raises still leaves the evidence behind — which is the whole point:
the offline fixture bundle cannot show HTML shape drift, and only a real
response can.

**It sends nothing that changes state.** Every call it makes goes through the
read-only path, which ``srt_mobile_api.safety.assert_read_only_request`` pins to
an allowlist; the four mutation routes are rejected there by construction. No
reservation is created, nothing is paid for, and nothing is cancelled.

Three opt-ins are required, all explicit::

    SRT_MOBILE_API_LIVE=1        # the normal live flag
    SRT_LIVE_READ_CAPTURE=1      # this script only
    SRT_LIVE_CAPTURE_DIR=<dir>   # where the raw bodies go

The second exists so a capture run can never fire from an ordinary live smoke.
The third has no default on purpose: raw bodies carry the account's own data
(member id, ticket history, session ids), so the operator must name the
destination rather than have one chosen for them, and the script REFUSES a
destination inside the repository working tree.

Pacing is deliberate. NetFunnel queueing sits in front of search and
macro-shaped traffic risks an IP ban, so every request is spaced by
``SRT_LIVE_CAPTURE_PACE_SECONDS`` (default 2.5s) and the search-shaped steps get
a longer gap. One careful pass, no retry loops. When a follow-up pass needs only
some of the surface — re-reading one page on a different route, say — name those
steps in ``SRT_LIVE_CAPTURE_STEPS`` (comma-separated) instead of paying for the
whole ~34-request walk again.

Its own stdout is safe to paste: every printed line goes through
``srt_mobile_api.redaction.redact_text``, the login id is masked, and response
bodies are never printed — only their size, status and content type.

Usage::

    SRT_MOBILE_API_LIVE=1 SRT_LIVE_READ_CAPTURE=1 \
    SRT_LIVE_CAPTURE_DIR=/tmp/srt-capture \
    SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... SRT_TEST_DATE=YYYYMMDD \
    python3 scripts/capture_live_read_surface.py

Exit code 0 means every step ran (a step may still have recorded a server-side
failure — that is data, not an error). Importing this module performs no I/O and
sends nothing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from srt_mobile_api import PassengerCounts, SrtClient, SrtConfig, TrainSearchQuery
from srt_mobile_api.live import (
    first_reservable_srt_train,
    live_enabled,
    read_credentials_from_env,
    read_device_key_from_env,
    read_query_from_env,
)
from srt_mobile_api.payloads import TRAIN_GROUP_OPTIONS
from srt_mobile_api.redaction import redact_text


CAPTURE_ENV = "SRT_LIVE_READ_CAPTURE"
CAPTURE_DIR_ENV = "SRT_LIVE_CAPTURE_DIR"
PACE_ENV = "SRT_LIVE_CAPTURE_PACE_SECONDS"
STEPS_ENV = "SRT_LIVE_CAPTURE_STEPS"
DEFAULT_PACE_SECONDS = 2.5
SEARCH_PACE_MULTIPLIER = 2.0


def capture_enabled() -> bool:
    """The second, capture-specific opt-in.

    Separate from ``SRT_MOBILE_API_LIVE`` so a capture run — which writes the
    account's raw responses to disk — cannot happen as a side effect of the
    ordinary live smoke.
    """
    return os.environ.get(CAPTURE_ENV) == "1"


def mask_login_id(login_id: str) -> str:
    """Show just enough of the member id to confirm the right account."""
    if len(login_id) <= 2:
        return "*" * len(login_id)
    return f"{login_id[0]}{'*' * (len(login_id) - 2)}{login_id[-1]}"


def say(message: str) -> None:
    """Print one redacted line.

    Everything this script prints goes through here. ``redact_text`` masks
    keyed credentials, PNRs, NetFunnel keys, session ids and card-shaped digit
    runs, so the transcript of a run can be pasted into a report as-is.
    """
    print(redact_text(message), flush=True)


def resolve_capture_dir(root: Path) -> Path:
    """The directory raw bodies are written to; never inside the repository.

    Raw captures contain the account's own data. The repository is exactly
    where they must not land, so a destination inside ``root`` is refused rather
    than silently relocated.
    """
    raw = os.environ.get(CAPTURE_DIR_ENV)
    if not raw:
        raise RuntimeError(
            f"{CAPTURE_DIR_ENV} is required: raw captures carry personal data, "
            "so the destination must be named explicitly"
        )
    target = Path(raw).expanduser().resolve()
    if target == root or root in target.parents:
        raise RuntimeError(
            f"{CAPTURE_DIR_ENV} must point OUTSIDE the repository working tree; "
            "raw captures must never be committed"
        )
    return target


def resolve_selected_steps() -> frozenset[str] | None:
    """The step names to run, or ``None`` for the whole surface.

    A full pass is ~34 requests. Re-running all of it to re-read ONE page is
    exactly the macro-shaped traffic the rate limiter punishes, so a follow-up
    pass can name only the steps it needs (comma-separated in
    ``SRT_LIVE_CAPTURE_STEPS``). ``login`` is always run — nothing else is
    reachable without it.
    """
    raw = os.environ.get(STEPS_ENV, "").strip()
    if not raw:
        return None
    names = {item.strip() for item in raw.split(",") if item.strip()}
    return frozenset(names | {"login"}) if names else None


def resolve_pace_seconds() -> float:
    raw = os.environ.get(PACE_ENV)
    if not raw:
        return DEFAULT_PACE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_PACE_SECONDS
    # A floor, not a free knob: this is the rate-limit guard, and setting it to
    # zero is what turns a capture run into macro-shaped traffic.
    return max(value, 1.0)


@dataclass
class Exchange:
    """One request/response pair, recorded before anything parses it."""

    seq: int
    step: str
    method: str
    url: str
    request_body: str
    status: int
    content_type: str
    body: str

    def to_json(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "step": self.step,
            "method": self.method,
            "url": self.url,
            "requestBody": self.request_body,
            "status": self.status,
            "contentType": self.content_type,
            "bodyLength": len(self.body),
            "body": self.body,
        }


@dataclass
class Recorder:
    out_dir: Path
    exchanges: list[Exchange] = field(default_factory=list)
    step: str = "setup"

    def record(self, request: Any, response: Any) -> None:
        try:
            request_body = request.content.decode("utf-8", "replace")
        except Exception:  # 넓게 잡는다: 기록이 실행을 깨뜨려서는 안 된다
            request_body = "<unreadable>"
        exchange = Exchange(
            seq=len(self.exchanges) + 1,
            step=self.step,
            method=request.method,
            url=str(request.url),
            request_body=request_body,
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            body=response.text,
        )
        self.exchanges.append(exchange)
        name = f"{exchange.seq:03d}-{exchange.step}.json"
        path = self.out_dir / name
        path.write_text(
            json.dumps(exchange.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        say(
            f"    <- {exchange.method} {exchange.url.split('?', 1)[0]} "
            f"status={exchange.status} type={exchange.content_type!r} "
            f"bytes={len(exchange.body)}"
        )


def attach_recorder(client: SrtClient, recorder: Recorder) -> Callable[[], None]:
    """Tee every response into ``recorder``, returning an undo callable.

    Wraps ``httpx.Client.send`` on the client's own transport rather than
    installing a custom ``httpx.BaseTransport``. At the transport boundary a
    response body is still content-encoded, so recording there would mean
    decoding it and rebuilding the response — i.e. capturing something subtly
    different from what the parsers receive. Here the body is exactly the string
    the parser is about to be handed, which is the only version worth capturing.
    """
    transport = client.http._client  # 비공개 속성 접근: 이유는 docstring 참조
    original_send = transport.send

    def send(request, **kwargs):  # type: ignore[no-untyped-def]
        response = original_send(request, **kwargs)
        try:
            recorder.record(request, response)
        except Exception as exc:  # 넓게 잡는다: 라이브 실행을 절대 깨뜨리지 않는다
            say(f"    (recording failed: {type(exc).__name__}: {exc})")
        return response

    transport.send = send  # type: ignore[method-assign]

    def restore() -> None:
        transport.send = original_send  # type: ignore[method-assign]

    return restore


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


class ReadSurfaceCapture:
    """Runs the read surface once, recording and summarising each step."""

    def __init__(
        self,
        client: SrtClient,
        recorder: Recorder,
        pace: float,
        selected: frozenset[str] | None = None,
    ) -> None:
        self.client = client
        self.recorder = recorder
        self.pace = pace
        self.selected = selected
        self.results: list[StepResult] = []

    def run_step(
        self,
        name: str,
        action: Callable[[], Any],
        *,
        describe: Callable[[Any], str] | None = None,
        heavy: bool = False,
    ) -> Any:
        """Run one read, record it, and never let a failure end the pass.

        A step that raises is itself a finding — an unreachable read, or a
        parser that cannot handle what the server actually sent — so it is
        summarised and the walk continues to the next one.
        """
        if self.selected is not None and name not in self.selected:
            return None
        self.recorder.step = name
        say(f"[{name}]")
        time.sleep(self.pace * (SEARCH_PACE_MULTIPLIER if heavy else 1.0))
        try:
            value = action()
        except Exception as exc:  # 넓게 잡는다: 여기서는 실패도 데이터다
            detail = f"{type(exc).__name__}: {exc}"
            self.results.append(StepResult(name, False, detail))
            say(f"    !! {detail}")
            return None
        detail = describe(value) if describe else "ok"
        self.results.append(StepResult(name, True, detail))
        say(f"    ok {detail}")
        return value

    def summary(self) -> dict[str, Any]:
        return {
            "steps": [
                {"name": item.name, "ok": item.ok, "detail": item.detail}
                for item in self.results
            ],
            "exchangeCount": len(self.recorder.exchanges),
            "reached": sum(1 for item in self.results if item.ok),
            "unreached": sum(1 for item in self.results if not item.ok),
        }


def _describe_train(train: Any) -> str:
    return (
        f"trnNo={train.train_no} runDt={train.run_date} "
        f"dep={train.departure_date}/{train.departure_time} "
        f"arv={train.arrival_date}/{train.arrival_time} "
        f"general={train.general_seat_availability!r} "
        f"special={train.special_seat_availability!r}"
    )


def _late_night_query(query: TrainSearchQuery) -> TrainSearchQuery:
    """A same-route query late enough that the server should have nothing left.

    An empty result is one of the edge shapes the offline bundle cannot
    demonstrate, and asking for a departure after the last service is the
    cheapest way to make the real server produce one — no extra route, no extra
    date, one more search.
    """
    from dataclasses import replace

    return replace(query, departure_time="234500")


def run_capture(
    capture: ReadSurfaceCapture,
    *,
    login_id: str,
    password: str,
    query: TrainSearchQuery,
) -> None:
    client = capture.client
    group_name = TRAIN_GROUP_OPTIONS[query.train_group_code][0]

    capture.run_step(
        "login",
        lambda: client.login(login_id, password),
        describe=lambda session: f"userMap keys={len(session.user_map)}",
    )
    capture.run_step(
        "get_main",
        client.get_main,
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_booking_page",
        client.get_booking_page,
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_typed_notice_list",
        client.get_typed_notice_list,
        describe=lambda result: f"notices={len(result.notices)}",
    )
    capture.run_step(
        "get_notice_list",
        client.get_notice_list,
        describe=lambda data: f"keys={sorted(data)}",
    )
    capture.run_step(
        "get_ticket_list",
        client.get_ticket_list,
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_reservations",
        client.get_reservations,
        # Counts and envelope codes only. The rows carry PNRs and, on a
        # populated account, the seat the holder is sitting in; those belong in
        # the raw capture file (which never leaves the operator's disk), not on
        # a stdout line that is meant to be pasteable into a report.
        describe=lambda result: (
            f"reservations={len(result.reservations)} "
            f"strResult={result.status!r} msgCd={result.message_code!r} "
            f"rowCnt={result.row_count} totPageCnt={result.total_page_count}"
        ),
    )

    capture.run_step(
        "get_station_selector",
        lambda: client.get_station_selector(
            query.departure_station_name or query.departure_station_code,
            query.arrival_station_name or query.arrival_station_code,
            query.departure_station_code,
            query.arrival_station_code,
        ),
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_station_map_selector",
        client.get_station_map_selector,
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_date_selector",
        lambda: client.get_date_selector(query.departure_date),
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_passenger_selector",
        lambda: client.get_passenger_selector(query.passengers),
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_seat_option_selector",
        lambda: client.get_seat_option_selector(
            request_seat_attr_code=query.seat_attr_code
        ),
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_train_group_selector",
        lambda: client.get_train_group_selector(query.train_group_code, group_name),
        describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
    )
    capture.run_step(
        "get_mutual_verification",
        client.get_mutual_verification,
        describe=lambda result: (
            f"status={result.status!r} msgCd={result.message_code!r} "
            f"codeLength={len(result.verification_code)}"
        ),
    )

    search = capture.run_step(
        "search_trains",
        lambda: client.search_trains(query),
        describe=lambda result: (
            f"trains={len(result.trains)} "
            f"msgCd={result.metadata.message_code!r} "
            f"strResult={result.metadata.status!r} "
            f"qryCnqeCnt={result.metadata.query_count} "
            f"fllwPgExt={result.metadata.has_following_page}"
        ),
        heavy=True,
    )

    train = None
    if search is not None and search.trains:
        # Prefer a train the server currently reports as bookable. The seat page
        # is the read most sensitive to this: a sold-out train is answered with
        # an error shell rather than a seat map, so addressing the seat read with
        # the first row regardless would capture the error shape every time and
        # never the real one.
        train = first_reservable_srt_train(search.trains) or search.trains[0]
        say(f"    selected {_describe_train(train)}")

    if train is not None:
        capture.run_step(
            "get_seat_page",
            lambda: client.get_seat_page(train, passengers=query.passengers),
            describe=lambda page: f"text={len(page.text)} raw={len(page.raw)}",
        )
        capture.run_step(
            "get_timetable",
            lambda: client.get_timetable(train),
            describe=lambda page: f"rows={len(page.rows)} raw={len(page.raw)}",
        )
        capture.run_step(
            "get_fare",
            lambda: client.get_fare(train, query.passengers),
            describe=lambda page: (
                f"items={len(page.items)} semantic={len(page.semantic_items)}"
            ),
        )
    else:
        for skipped in ("get_seat_page", "get_timetable", "get_fare"):
            if capture.selected is not None and skipped not in capture.selected:
                continue
            capture.results.append(
                StepResult(skipped, False, "no train row available to address it")
            )
            say(f"[{skipped}]\n    !! no train row available to address it")

    capture.run_step(
        "iter_train_search_pages",
        lambda: [
            (len(page.trains), page.metadata.has_following_page if page.metadata else None)
            for page in client.iter_train_search_pages(query, max_pages=2)
        ],
        describe=lambda pages: f"pages={pages}",
        heavy=True,
    )
    capture.run_step(
        "search_group_trains",
        lambda: client.search_group_trains(
            TrainSearchQuery(
                departure_station_code=query.departure_station_code,
                arrival_station_code=query.arrival_station_code,
                departure_date=query.departure_date,
                departure_time=query.departure_time,
                passengers=PassengerCounts(adult=10),
                train_group_code=query.train_group_code,
                seat_attr_code=query.seat_attr_code,
                departure_station_name=query.departure_station_name,
                arrival_station_name=query.arrival_station_name,
            )
        ),
        describe=lambda result: (
            f"trains={len(result.trains)} "
            f"msgCd={result.metadata.message_code!r} "
            f"strResult={result.metadata.status!r}"
        ),
        heavy=True,
    )
    capture.run_step(
        "search_trains_empty_window",
        lambda: client.search_trains(_late_night_query(query)),
        describe=lambda result: (
            f"trains={len(result.trains)} "
            f"msgCd={result.metadata.message_code!r} "
            f"strResult={result.metadata.status!r} "
            f"msgTxtLength={len(result.metadata.message)}"
        ),
        heavy=True,
    )

    # Session-expiry edge, LAST because it destroys the session. Clearing the
    # cookie jar is the closest reproduction of an expired session available
    # without waiting one out, and it is what makes the server show us its
    # unauthenticated answer for both an HTML read and a JSON read.
    say("[expired-session probe] clearing the cookie jar")
    client.clear_session()
    capture.run_step(
        "get_ticket_list_expired",
        client.get_ticket_list,
        describe=lambda page: f"UNEXPECTEDLY parsed: text={len(page.text)}",
    )
    capture.run_step(
        "get_mutual_verification_expired",
        client.get_mutual_verification,
        describe=lambda result: f"UNEXPECTEDLY parsed: status={result.status!r}",
    )


def main(argv: list[str] | None = None) -> int:
    if argv:
        print(f"ERROR: unexpected arguments: {argv}", file=sys.stderr)
        return 2
    if not live_enabled():
        print("Set SRT_MOBILE_API_LIVE=1 to run the live capture", file=sys.stderr)
        return 2
    if not capture_enabled():
        print(
            f"Set {CAPTURE_ENV}=1 to allow this script to drive the live read "
            "surface and write raw responses to disk. SRT_MOBILE_API_LIVE alone "
            "is not enough.",
            file=sys.stderr,
        )
        return 2
    root = Path(__file__).resolve().parents[1]
    try:
        out_dir = resolve_capture_dir(root)
        login_id, password = read_credentials_from_env()
        query = read_query_from_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    pace = resolve_pace_seconds()
    selected = resolve_selected_steps()
    say(f"Capturing to {out_dir} at {pace}s pacing")
    if selected is not None:
        say(f"Running only: {', '.join(sorted(selected))}")
    say(f"Logged in as {mask_login_id(login_id)} (password never printed)")
    say(
        f"Query {query.departure_station_code}->{query.arrival_station_code} "
        f"on {query.departure_date} from {query.departure_time}, "
        f"{query.passengers.total} passenger(s)"
    )

    recorder = Recorder(out_dir=out_dir)
    client = SrtClient(SrtConfig(device_key=read_device_key_from_env()))
    restore = attach_recorder(client, recorder)
    capture = ReadSurfaceCapture(client, recorder, pace, selected)
    try:
        run_capture(capture, login_id=login_id, password=password, query=query)
    finally:
        restore()
        client.close()

    summary = capture.summary()
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    say("")
    say(
        f"Captured {summary['exchangeCount']} exchange(s); "
        f"{summary['reached']} step(s) reached, {summary['unreached']} not"
    )
    for item in summary["steps"]:
        say(f"  {'OK ' if item['ok'] else 'ERR'} {item['name']}: {item['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
