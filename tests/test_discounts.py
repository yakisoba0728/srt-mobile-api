"""The 할인 code tables, and the claims their module docstring makes.

These are pinning tests, not behaviour tests: the tables are copies of the app's
own data, so what can go wrong is a copy that quietly stops matching the source
or an accessor that starts inventing entries. Both are checked here.
"""

import pytest

from srt_mobile_api.discounts import (
    DISCOUNT_KIND_NAMES_BY_CODE,
    PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE,
    PUBLIC_DISCOUNT_NAMES_BY_CODE,
    PUBLIC_DISCOUNT_YOUTH_CODE,
    YOUTH_PASSENGER_TYPE_CODE,
    discount_kind_name,
    public_discount_name,
)


def test_discount_kind_table_size_and_shape():
    # 173, not 171: the two rows commCode.js leaves without a code_group_cd
    # (133, 191) are inside the dcntKndCd run and are included deliberately.
    assert len(DISCOUNT_KIND_NAMES_BY_CODE) == 173
    assert DISCOUNT_KIND_NAMES_BY_CODE["133"] == "기본 특별할인(기준)"
    assert DISCOUNT_KIND_NAMES_BY_CODE["191"] == "정차역 할인"
    assert all(
        isinstance(code, str) and code and isinstance(name, str) and name
        for code, name in DISCOUNT_KIND_NAMES_BY_CODE.items()
    )


def test_discount_kind_table_carries_the_welfare_codes_passengercounts_can_express():
    # The five passenger types PassengerCounts already carries have discount
    # codes in this table, which is the join between the two vocabularies:
    # a psgTpCd selects WHO, a dcntKndCd is what the fare engine then applied.
    assert DISCOUNT_KIND_NAMES_BY_CODE["201"] == "어린이 할인"
    assert DISCOUNT_KIND_NAMES_BY_CODE["204"] == "경로 할인"
    assert DISCOUNT_KIND_NAMES_BY_CODE["205"] == "1-3급 장애인 할인"
    assert DISCOUNT_KIND_NAMES_BY_CODE["206"] == "4-6급 장애인할인"
    # ...and codes for things it CANNOT express, which is the gap.
    assert DISCOUNT_KIND_NAMES_BY_CODE["202"] == "동반유아 할인"
    assert DISCOUNT_KIND_NAMES_BY_CODE["P11"] == "청소년"


def test_discount_kind_name_resolves_and_refuses_to_invent():
    assert discount_kind_name("000") == "일반"
    assert discount_kind_name(" 204 ") == "경로 할인"
    assert discount_kind_name("ZZ8") == "영업할인6"
    assert discount_kind_name("nope") == ""
    assert discount_kind_name("") == ""
    assert discount_kind_name(None) == ""
    assert discount_kind_name(204) == ""


def test_public_discount_table_is_the_six_the_popup_names():
    assert PUBLIC_DISCOUNT_NAMES_BY_CODE == {
        "01": "다자녀",
        "02": "임산부",
        "03": "기초생활",
        "04": "청소년",
        "05": "모범 납세자",
        "06": "3세대 동행할인",
    }
    # 07 and 08 have branches on the 할인 승차권 page and no name anywhere, so
    # they must stay unknown rather than be guessed at.
    assert public_discount_name("07") == ""
    assert public_discount_name("08") == ""


def test_public_discount_name_resolves_and_refuses_to_invent():
    assert public_discount_name("01") == "다자녀"
    assert public_discount_name(" 06 ") == "3세대 동행할인"
    assert public_discount_name("99") == ""
    assert public_discount_name(None) == ""
    assert public_discount_name(1) == ""


def test_three_person_minimum_belongs_to_exactly_다자녀_and_3세대():
    assert PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE == {"01": 3, "06": 3}
    assert set(PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE) <= set(PUBLIC_DISCOUNT_NAMES_BY_CODE)


def test_youth_constants_name_the_one_discount_that_changes_the_passenger_vocabulary():
    assert PUBLIC_DISCOUNT_YOUTH_CODE == "04"
    assert PUBLIC_DISCOUNT_NAMES_BY_CODE[PUBLIC_DISCOUNT_YOUTH_CODE] == "청소년"
    # psgTpCd 6, which is in NEITHER copy of commCode.js -- see the module
    # docstring. Recorded as a constant, and deliberately not wired into
    # PassengerCounts.
    assert YOUTH_PASSENGER_TYPE_CODE == "6"


def test_tables_are_not_shared_mutable_state_between_callers():
    # dict, like STATION_NAMES_BY_CODE, so this is a discipline check rather
    # than an enforcement: the accessors must not hand the table out.
    before = dict(DISCOUNT_KIND_NAMES_BY_CODE)
    discount_kind_name("204")
    public_discount_name("01")
    assert DISCOUNT_KIND_NAMES_BY_CODE == before


@pytest.mark.parametrize(
    "code, expected",
    [
        ("106", "입석 할인"),
        ("207", "국가유공자 할인"),
        ("210", "인도견 할인"),
        ("255", "특실 업그레이드 할인"),
        ("700", "KTX 환승할인"),
        ("P41", "경로"),
        ("P51", "동반유아"),
        ("G00", "단체"),
    ],
)
def test_spot_checks_across_the_whole_code_space(code, expected):
    assert discount_kind_name(code) == expected
