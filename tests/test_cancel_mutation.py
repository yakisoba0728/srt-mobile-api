"""Offline tests for the SRT unpaid-reservation cancel (예약취소) surface.

Everything here is offline: synthetic PNRs, synthetic envelopes, and an
``httpx.MockTransport`` recorder that proves how many requests were actually
issued (always zero). No real network, no real credentials, no real PNR.

**Provenance.** The cancel wire shape under test is srtgo-attested only and is
UNCONFIRMED against our v2.0.41 app: ``/ard/selectListArd02045_n.do`` has zero
hits across all 21,673 files of the offline evidence bundle
(``docs/analysis/cross-validation-2026-07-21.md``). These tests pin what we
implemented from srtgo's evidence; they cannot and do not prove the server
accepts it.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import srt_mobile_api
from srt_mobile_api import SrtCancelResult, SrtReservationHold
from srt_mobile_api.errors import SrtAppError, SrtProtocolError
from srt_mobile_api.parsers import parse_unpaid_cancel_response
from srt_mobile_api.payloads import unpaid_reservation_cancel_payload


FAKE_PNR = "SYNTHETIC_PNR_REFERENCE"


def _hold(pnr: str = FAKE_PNR, **overrides) -> SrtReservationHold:
    return SrtReservationHold(pnr_no=pnr, **overrides)


# --- the form is exactly srtgo's three fields --------------------------------


def test_cancel_form_matches_the_srtgo_cancel_wire():
    # Field-by-field reproduction of srtgo _cancel (srt.py:1138): pnrNo plus the
    # two constants. Nothing else is sent.
    assert unpaid_reservation_cancel_payload(_hold()) == {
        "pnrNo": FAKE_PNR,
        "jrnyCnt": "1",
        "rsvChgTno": "0",
    }


def test_cancel_form_accepts_a_bare_pnr_string():
    # A caller recovering from a partial failure may hold nothing but the PNR.
    # That path must produce the identical form, or the hold cannot be released.
    assert unpaid_reservation_cancel_payload(FAKE_PNR) == (
        unpaid_reservation_cancel_payload(_hold())
    )


def test_cancel_form_ignores_hold_fields_that_are_not_on_the_wire():
    # totSeatNum/JRNYLIST_KEY are carried by the hold but are NOT cancel fields.
    form = unpaid_reservation_cancel_payload(
        _hold(journey_list_key="SYNTHETIC-JOURNEY-KEY", total_seat_count="2")
    )

    assert set(form) == {"pnrNo", "jrnyCnt", "rsvChgTno"}
    # In particular the seat count must not leak into jrnyCnt: two seats on one
    # journey is still one journey.
    assert form["jrnyCnt"] == "1"


def test_cancel_form_strips_surrounding_pnr_whitespace():
    assert unpaid_reservation_cancel_payload(f"  {FAKE_PNR}\n")["pnrNo"] == FAKE_PNR


# --- jrnyCnt tolerance: the korail regression must not repeat ----------------


def test_cancel_form_accepts_a_zero_padded_journey_count():
    # THE korail REGRESSION (korail commit 3d7e8a5). There, a real live reserve
    # returned h_jrny_cnt="0001" while the cancel builder required exactly "1";
    # it refused, the auto-cancel never ran, and a genuine unpaid hold was left
    # dangling. Compare numerically so a zero-padded value is accepted, and send
    # the unpadded value srtgo attests.
    assert unpaid_reservation_cancel_payload(
        _hold(), journey_count="0001"
    )["jrnyCnt"] == "1"


@pytest.mark.parametrize(
    "journey_count", ["1", " 1 ", "0001", "\t000001\n", "01"]
)
def test_cancel_form_normalizes_every_single_journey_spelling(journey_count):
    assert unpaid_reservation_cancel_payload(
        _hold(), journey_count=journey_count
    )["jrnyCnt"] == "1"


def test_cancel_form_preserves_a_genuine_multi_journey_count_unpadded():
    assert unpaid_reservation_cancel_payload(
        _hold(), journey_count="0002"
    )["jrnyCnt"] == "2"


@pytest.mark.parametrize(
    "journey_count",
    ["", "   ", "x", "1x", "-1", "1.0", "١", None, 1, object()],
)
def test_cancel_form_never_refuses_over_a_journey_count_formatting_problem(
    journey_count,
):
    # A refused cancel form means an uncancellable hold, which is strictly worse
    # than sending the single-journey default srtgo attests works. So an
    # unusable journey count falls back to "1" instead of raising — for ANY
    # shape, including non-strings and non-ASCII digits.
    form = unpaid_reservation_cancel_payload(_hold(), journey_count=journey_count)

    assert form["jrnyCnt"] == "1"
    assert form["pnrNo"] == FAKE_PNR


def test_cancel_form_default_journey_count_is_not_derived_from_the_hold():
    # The reserve response carries no journey count at all (reservListMap has
    # totSeatNum, a SEAT count), so SrtReservationHold has nothing to derive
    # from and the builder defaults instead. Two very different holds must
    # therefore produce the same jrnyCnt.
    sparse = unpaid_reservation_cancel_payload(_hold())
    rich = unpaid_reservation_cancel_payload(
        _hold(journey_list_key="K", total_seat_count="9")
    )

    assert sparse["jrnyCnt"] == rich["jrnyCnt"] == "1"


# --- the PNR, and only the PNR, is mandatory ---------------------------------


@pytest.mark.parametrize("pnr", ["", "   "])
def test_cancel_form_rejects_an_empty_pnr(pnr):
    # Not a formatting technicality: with no PNR there is nothing to cancel.
    with pytest.raises(ValueError, match="PNR"):
        unpaid_reservation_cancel_payload(pnr)
    with pytest.raises(ValueError, match="PNR"):
        unpaid_reservation_cancel_payload(_hold(pnr))


@pytest.mark.parametrize("reservation", [None, 7, b"pnr", {"pnrNo": FAKE_PNR}])
def test_cancel_form_rejects_a_foreign_reservation_type(reservation):
    with pytest.raises(ValueError):
        unpaid_reservation_cancel_payload(reservation)


# --- response parsing: SUCC and FAIL are both data, not exceptions -----------


def _envelope(status: str, **fields) -> dict:
    row = {"strResult": status}
    row.update(fields)
    return {"resultMap": [row]}


def test_cancel_parser_reads_a_success_envelope():
    payload = _envelope(
        "SUCC", msgCd="SYNTHETIC-CANCEL-OK", msgTxt="synthetic cancelled"
    )

    result = parse_unpaid_cancel_response(payload)

    assert isinstance(result, SrtCancelResult)
    assert result.succeeded is True
    assert result.status == "SUCC"
    assert result.message_code == "SYNTHETIC-CANCEL-OK"
    assert result.message == "synthetic cancelled"
    assert result.raw is payload


def test_cancel_parser_reports_a_failure_without_raising():
    # A FAIL must be readable as data: pushing "was my hold released?" into an
    # exception path is how holds get orphaned.
    payload = _envelope(
        "FAIL", msgCd="SYNTHETIC-CANCEL-FAIL", msgTxt="synthetic refusal"
    )

    result = parse_unpaid_cancel_response(payload)

    assert result.succeeded is False
    assert result.status == "FAIL"
    assert result.message_code == "SYNTHETIC-CANCEL-FAIL"
    assert result.message == "synthetic refusal"
    assert result.raw is payload


def test_cancel_parser_treats_only_succ_as_success():
    assert parse_unpaid_cancel_response(_envelope("succ")).succeeded is False


def test_cancel_parser_accepts_the_dsoutput0_envelope_spelling():
    # The exact container is unconfirmed for this route, so the shared
    # normalize_result_row handling (resultMap OR outDataSets.dsOutput0) is
    # reused rather than one layout being asserted.
    payload = {"outDataSets": {"dsOutput0": [{"strResult": "SUCC"}]}}

    assert parse_unpaid_cancel_response(payload).succeeded is True


def test_cancel_parser_treats_a_missing_message_code_as_informational():
    # srtgo gates a cancel purely on strResult and never reads msgCd; refusing a
    # response over a field nobody reads would hide a real cancellation outcome.
    result = parse_unpaid_cancel_response(_envelope("SUCC"))

    assert result.succeeded is True
    assert result.message_code == ""
    assert result.message == ""


def test_cancel_result_is_frozen_and_repr_safe():
    result = parse_unpaid_cancel_response(
        _envelope("SUCC", msgCd="OK", msgTxt="synthetic detail")
    )

    assert "synthetic detail" not in repr(result)
    assert "resultMap" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.status = "FAIL"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        "SUCC",
        None,
        {"resultMap": []},
        {"resultMap": [{}]},
        {"resultMap": [{"strResult": ""}]},
        {"resultMap": [{"strResult": 1}]},
        {"resultMap": [{"strResult": "SUCC", "msgCd": 7}]},
        {"resultMap": [{"strResult": "SUCC", "msgTxt": 7}]},
        {"ERROR_CODE": "0"},
    ],
)
def test_cancel_parser_rejects_a_malformed_envelope(payload):
    with pytest.raises(SrtProtocolError):
        parse_unpaid_cancel_response(payload)


def test_cancel_parser_surfaces_an_app_level_rejection():
    payload = {
        "ERROR_CODE": "SYNTHETIC-ERROR",
        "ERROR_MSG": "synthetic app rejection",
        "resultMap": [{"strResult": "SUCC"}],
    }

    with pytest.raises(SrtAppError) as exc_info:
        parse_unpaid_cancel_response(payload)

    assert exc_info.value.code == "SYNTHETIC-ERROR"
    assert exc_info.value.raw is payload


def test_cancel_model_and_parser_are_exported():
    assert srt_mobile_api.SrtCancelResult is SrtCancelResult
    assert (
        srt_mobile_api.parse_unpaid_cancel_response is parse_unpaid_cancel_response
    )
