"""Every exported ``Literal`` alias must still name exactly the values the
runtime accepts.

A ``Literal`` alias is a hand-written copy of a set that lives somewhere else —
a frozenset a builder validates against, or the ``allow_*`` flag table a consent
gate reads. Copies drift, and a drifted alias is worse than no alias: the type
checker starts refusing a value the library itself accepts, so the caller's only
escape is ``# type: ignore``. Each test below pins one alias to the runtime
structure that decides the same question, so widening one without the other
fails here.
"""

from typing import get_args

from srt_mobile_api.consent import _CONSENT_FLAG_BY_CATEGORY, MutationCategory
from srt_mobile_api.models import SrtSeatAttrCode, SrtTrainGroupCode
from srt_mobile_api.payloads import (
    SRT_REQUEST_SEAT_ATTR_CODES,
    TRAIN_GROUP_OPTIONS,
)


def test_seat_attr_code_alias_matches_the_validated_set():
    assert set(get_args(SrtSeatAttrCode)) == SRT_REQUEST_SEAT_ATTR_CODES


def test_train_group_code_alias_matches_the_option_table():
    # train_group_selector_payload validates against TRAIN_GROUP_OPTIONS and
    # TrainSearchQuery.__post_init__ against its own literal set; the table is
    # the wider of the two only if they ever disagree, which they must not.
    assert set(get_args(SrtTrainGroupCode)) == set(TRAIN_GROUP_OPTIONS)


def test_mutation_category_alias_matches_the_consent_flag_table():
    assert set(get_args(MutationCategory)) == set(_CONSENT_FLAG_BY_CATEGORY)
