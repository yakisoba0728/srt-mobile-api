"""The package root's ``__all__`` is a published contract, and this file is the
only thing that keeps it one.

The surface it guards did not arrive by design. Before this file existed,
``parsers.py`` defined 21 ``parse_*`` functions and exactly 12 of them were
re-exported at the root -- not the 12 a contract would have chosen, just the 12
that happened to be wired up first. That is chronology, not a boundary, and
chronology drifts back the moment nobody is looking. So the rule is written as
five checks that *derive* what belongs, rather than as a list of names somebody
has to remember to update:

1. every ``__all__`` entry is imported by ``__init__.py`` and every name
   ``__init__.py`` imports is in ``__all__``. Demoting a name means deleting
   BOTH lines; delete only one and half the demotion silently survives.
2. nothing defined in an internal module reaches ``__all__``. The *module* is
   the rule, not a name list -- a module added tomorrow is internal by default,
   because it is internal unless this file says otherwise.
3. no ``parse_*`` / ``pair_*`` name at the root, ever. The client calls those
   for the caller; importing one is reaching past the client into the wire.
4. reachability: every package-defined type you can reach from a public client
   method's annotations -- through unions, generics, dataclass fields and base
   classes -- must be exported. This is the check that bites when someone adds a
   method returning a type they forgot to publish.
5. every root name that is neither a class nor a function is a deliberate
   domain constant with a reason recorded below. Transport constants -- URLs,
   routes, headers, timeouts -- do not get to drift upward.

(1)-(3) and (5) read ``__init__.py`` from disk with ``ast``, so they judge the
source, not an in-memory ``__all__`` a conftest could have rewritten.

This file must be identical in the korail and SRT repositories from the ``shared
rule logic`` delimiter downward; everything above that delimiter is the
per-repository data the shared logic reads. Nothing in either repository checks
that today -- the cross-repository stage is what diffs the two files from the
delimiter down, and until it does, this paragraph is an intention, not a fact.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import typing
from pathlib import Path

import pytest

# --------------------------------------------------------------------------
# per-repository block -- the ONLY part that differs between the two packages
# --------------------------------------------------------------------------

PACKAGE = "srt_mobile_api"
CLIENT_CLASS = "SrtClient"

#: Modules whose contents may be re-exported at the root without further
#: qualification: the client, its configuration, the consent gate, the error
#: hierarchy, and the response models those three speak in.
PUBLIC_MODULES = frozenset(
    {
        "client",
        "config",
        "consent",
        "errors",
        "models",
    }
)

#: Modules that may publish *values* -- request dataclasses, domain constants --
#: but never functions. A module lands here when its dataclasses are things a
#: caller constructs while its functions are machinery the client drives.
#: SRT has none: every request dataclass it exports already lives in ``models``.
VALUE_ONLY_MODULES: frozenset[str] = frozenset()

#: Root names that are neither classes nor functions, each with the reason it is
#: a domain value a caller supplies or compares against rather than a transport
#: detail. SRT publishes none -- its station codes, route paths, timeouts and
#: header names are all reachable through ``SrtConfig`` defaults or belong to
#: the transport, so none of them belongs at the root.
DOMAIN_CONSTANTS: dict[str, str] = {}

#: Types the reachability walk in (4) must find. Without these, a traversal that
#: silently resolves nothing -- a swallowed ``get_type_hints`` failure, a
#: recursion that never descends -- would read as a pass.
REACHABILITY_CANARIES = frozenset(
    {
        "TrainSearchResult",  # search_trains return
        "SrtRefundTicketInfo",  # get_refund_ticket_info return
        "SeatGrid",  # nested inside SeatSelectionPage, not a return type
        "PassengerCounts",  # argument-side, reached through TrainSearchQuery
    }
)

#: Names this repository took off the root, and the module each still answers
#: from. A demotion that deletes is a different change from one that moves, and
#: only the move was agreed, so the defining path is pinned per name.
DEMOTED_NAMES: tuple[tuple[str, str], ...] = (
    ("pair_transfer_itineraries", "parsers"),
    ("parse_card_payment_response", "parsers"),
    ("parse_coupon_registration_response", "parsers"),
    ("parse_discount_coupon_page", "parsers"),
    ("parse_public_discount_page", "parsers"),
    ("parse_public_discount_search_response", "parsers"),
    ("parse_refund_response", "parsers"),
    ("parse_refund_ticket_info_response", "parsers"),
    ("parse_reservation_attempt_response", "parsers"),
    ("parse_reservation_hold_response", "parsers"),
    ("parse_reservation_list_response", "parsers"),
    ("parse_seat_grid_response", "parsers"),
    ("parse_unpaid_cancel_response", "parsers"),
    ("ReservationAttemptResult", "models"),
    ("ReservationRecord", "models"),
    ("ReservationTrain", "models"),
    ("SrtCouponRegistrationRequest", "models"),
)

# --------------------------------------------------------------------------
# shared rule logic: identical in both repositories from here down
# --------------------------------------------------------------------------

pkg = importlib.import_module(PACKAGE)
PACKAGE_ROOT = Path(pkg.__file__).parent
INIT_SOURCE = (PACKAGE_ROOT / "__init__.py").read_text(encoding="utf-8")
INIT_TREE = ast.parse(INIT_SOURCE)


def _init_import_map() -> dict[str, str]:
    """name -> submodule it is imported from, read out of ``__init__.py``."""
    mapping: dict[str, str] = {}
    for node in ast.walk(INIT_TREE):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0 or node.module is None:
            # ``from . import x`` and absolute imports are not name re-exports
            # this rule knows how to attribute; there are none today, and if one
            # appears it should be justified rather than silently classified.
            continue
        for alias in node.names:
            mapping[alias.asname or alias.name] = node.module
    return mapping


def _declared_all() -> list[str]:
    """``__all__`` as the source file spells it, not as the module object has it."""
    for node in INIT_TREE.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return [ast.literal_eval(e) for e in node.value.elts]
    raise AssertionError(f"{PACKAGE}/__init__.py declares no __all__")


def _submodules() -> frozenset[str]:
    return frozenset(
        p.stem
        for p in PACKAGE_ROOT.glob("*.py")
        if p.stem != "__init__"
    )


def _function_names(module: str) -> frozenset[str]:
    """Top-level ``def``s in a submodule, by ast -- no import side effects."""
    tree = ast.parse((PACKAGE_ROOT / f"{module}.py").read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


IMPORT_MAP = _init_import_map()
DECLARED_ALL = _declared_all()
INTERNAL_MODULES = _submodules() - PUBLIC_MODULES - VALUE_ONLY_MODULES


def _defining_module(name: str) -> str:
    """Where a root name really comes from.

    ``__module__`` first, so a name laundered through a re-export -- ``from
    .models import parse_foo`` where ``models`` itself imported it from
    ``parsers`` -- is attributed to ``parsers``, which is what (2) is about.
    Constants have no ``__module__``; for those the import line is all there is.
    """
    obj = getattr(pkg, name)
    module = getattr(obj, "__module__", None)
    if isinstance(module, str) and module.startswith(f"{PACKAGE}."):
        return module[len(PACKAGE) + 1 :]
    return IMPORT_MAP.get(name, "<unimported>")


# --- 1. the two halves of an export are deleted together, or not at all -------


def test_all_matches_the_import_lines_exactly():
    imported = set(IMPORT_MAP)
    exported = set(DECLARED_ALL)

    assert exported - imported == set(), (
        "in __all__ but not imported by __init__.py -- a name that cannot "
        "resolve, or one imported some way this rule cannot attribute"
    )
    assert imported - exported == set(), (
        "imported by __init__.py but absent from __all__ -- demotion residue: "
        "the __all__ entry went and the import line stayed, so the name is "
        "still reachable as an attribute"
    )
    assert len(DECLARED_ALL) == len(set(DECLARED_ALL)), "duplicate in __all__"
    assert set(DECLARED_ALL) == set(pkg.__all__)


# --- 2. modules are the rule, not names ---------------------------------------


def test_no_internal_module_reaches_the_public_surface():
    assert INTERNAL_MODULES, "the package has no internal modules; check the glob"

    leaked = sorted(
        (name, _defining_module(name))
        for name in DECLARED_ALL
        if _defining_module(name) in INTERNAL_MODULES
    )
    assert leaked == [], (
        "exported from an internal module. Either the name belongs at the "
        "defining path only, or the module belongs in PUBLIC_MODULES with a "
        "reason written down"
    )


def test_value_only_modules_export_no_functions():
    offenders = []
    for name in DECLARED_ALL:
        module = _defining_module(name)
        if module in VALUE_ONLY_MODULES and name in _function_names(module):
            offenders.append((name, module))
    assert sorted(offenders) == [], (
        "a function escaped from a value-only module: those modules publish "
        "request dataclasses and domain constants, not machinery"
    )


# --- 3. one line, no list to maintain ----------------------------------------


def test_no_parser_or_pairing_function_is_public():
    assert [n for n in DECLARED_ALL if n.startswith(("parse_", "pair_"))] == []


# --- 4. reachability: every type a caller can be handed is nameable ----------


def _is_package_class(obj: object) -> bool:
    return (
        inspect.isclass(obj)
        and getattr(obj, "__module__", "").split(".")[0] == PACKAGE
    )


def _flatten(hint: object, seen: set) -> None:
    """Every type mentioned anywhere inside an annotation.

    Unions, generics and their origins alike: ``Preview | Result`` must yield
    both arms, ``list[Row]`` must yield the row type inside it.
    """
    try:
        if hint in seen:
            return
        seen.add(hint)
    except TypeError:  # unhashable annotation object
        return
    for arg in typing.get_args(hint):
        _flatten(arg, seen)
    origin = typing.get_origin(hint)
    if origin is not None:
        _flatten(origin, seen)


def _reachable_types() -> tuple[set[str], list[str]]:
    client = getattr(pkg, CLIENT_CLASS)
    pending: list[type] = []
    unresolved: list[str] = []

    def harvest(owner: object, label: str) -> None:
        try:
            hints = typing.get_type_hints(owner)
        except Exception as exc:  # a string annotation that no longer resolves
            unresolved.append(f"{label}: {exc!r}")
            return
        seen: set = set()
        for hint in hints.values():
            _flatten(hint, seen)
        pending.extend(h for h in seen if _is_package_class(h))

    # ``dir`` rather than ``vars`` so a method inherited from a base counts,
    # and ``getattr_static`` so a property is examined as its getter instead of
    # being evaluated on the class. Neither shape exists in every package this
    # file guards, which is precisely why the walk must not assume its absence.
    for name in dir(client):
        if name.startswith("_"):
            continue
        try:
            member = inspect.getattr_static(client, name)
        except AttributeError:  # pragma: no cover - defensive
            continue
        if isinstance(member, property):
            member = member.fget
        elif isinstance(member, (staticmethod, classmethod)):
            member = member.__func__
        elif isinstance(member, functools.cached_property):
            member = member.func
        if not inspect.isfunction(member):
            continue
        harvest(member, f"{CLIENT_CLASS}.{name}")

    closure: set[type] = set()
    while pending:
        cls = pending.pop()
        if cls in closure:
            continue
        closure.add(cls)
        harvest(cls, cls.__name__)  # dataclass fields and annotated attributes
        pending.extend(b for b in cls.__mro__[1:] if _is_package_class(b))

    return {c.__name__ for c in closure}, unresolved


def test_every_reachable_type_is_exported():
    reachable, unresolved = _reachable_types()

    assert unresolved == [], (
        "an annotation could not be resolved, so the walk below it did not "
        "happen and this check is weaker than it looks"
    )
    # Without this the whole test passes vacuously when the walk finds nothing.
    assert REACHABILITY_CANARIES <= reachable, sorted(
        REACHABILITY_CANARIES - reachable
    )

    assert sorted(reachable - set(DECLARED_ALL)) == [], (
        "reachable from a public client method but not exported: a caller can "
        "be handed one of these and has no way to name its type"
    )


# --- 5. constants are justified one by one -----------------------------------


def test_public_constants_are_exactly_the_declared_domain_constants():
    bare = {
        name
        for name in DECLARED_ALL
        if not inspect.isclass(getattr(pkg, name))
        and not inspect.isfunction(getattr(pkg, name))
    }
    assert bare == set(DOMAIN_CONSTANTS), (
        "a value that is neither a class nor a function reached the root. "
        "Transport constants -- base URLs, route paths, header names, timeouts "
        "-- belong to their module; anything a caller genuinely passes in or "
        "compares against goes in DOMAIN_CONSTANTS with its reason"
    )
    assert all(DOMAIN_CONSTANTS.values()), "every domain constant needs a reason"


# --- the demotion this rule was written to make permanent --------------------


@pytest.mark.parametrize("name, module", DEMOTED_NAMES)
def test_demoted_names_moved_rather_than_disappeared(name, module):
    submodule = importlib.import_module(f"{PACKAGE}.{module}")
    assert hasattr(submodule, name)
    assert name not in pkg.__all__
    assert not hasattr(pkg, name)
