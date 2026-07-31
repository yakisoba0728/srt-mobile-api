from __future__ import annotations

import os
import re
import stat
import struct
import subprocess
import sys
import tarfile
import tomllib
import warnings
import zipfile
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path

import pytest

from srt_mobile_api.safety import READ_ONLY_ROUTES


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "srt_mobile_api"
PROJECT_NAME = "srt-mobile-api"
EXPECTED_KEYWORDS = ['srt','read-only-by-default','mobile-api']
LIVE_ENV = "SRT_MOBILE_API_LIVE"
CLIENT_NAME = "SrtClient"
# The audit log the README used to be. See the comment above
# test_repository_truth_and_full_mutation_policy for which pins live here now.
VERIFICATION_DOCUMENT = "docs/VERIFICATION.md"
FAILURE_MESSAGE = "distribution verification failed\n"
EXPECTED_CLASSIFIERS = {
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Typing :: Typed",
}
# There is deliberately no "License :: ..." classifier here: PEP 639 makes the
# SPDX `license` string and the classifier mutually exclusive.
EXPECTED_LICENSE = "Apache-2.0"
LICENSE_FILE = "LICENSE"
EXPECTED_AUTHORS = [
    {"name": "yakisoba0728", "email": "yakihyuk0728@gmail.com"},
]
EXPECTED_AUTHOR_EMAIL = "yakisoba0728 <yakihyuk0728@gmail.com>"
CANONICAL_URL = "https://github.com/yakisoba0728/srt-mobile-api"
EXPECTED_URLS = {
    "Homepage": CANONICAL_URL,
    "Repository": CANONICAL_URL,
    "Issues": f"{CANONICAL_URL}/issues",
    "Changelog": f"{CANONICAL_URL}/blob/main/CHANGELOG.md",
}
EXPECTED_PROJECT_URLS = [f"{label}, {url}" for label, url in EXPECTED_URLS.items()]
# Every header a correct build still must NOT emit. `License-Expression`,
# `Author-email` and `Project-URL` left this tuple when the project grew owner
# metadata, and each moved into an exact-value check rather than out of the
# contract -- see the singleton parametrization and
# test_requires_the_exact_project_url_set_without_duplicates below.
FORBIDDEN_METADATA_HEADERS = (
    "License",
    "Author",
    "Maintainer",
    "Maintainer-email",
    "Home-page",
    "Download-URL",
)

with (ROOT / "pyproject.toml").open("rb") as stream:
    CONFIGURATION = tomllib.load(stream)
PROJECT = CONFIGURATION["project"]
VERSION = PROJECT["version"]
LICENSE_TEXT = (ROOT / LICENSE_FILE).read_bytes()
#: Every path named by ``license-files``. ``LICENSE_FILE`` stays the primary and
#: remains the target of the adversarial licence-content cases below; NOTICE
#: rides along because Apache-2.0 section 4(d) obliges a redistributor to carry
#: the attribution notices forward, which a wheel carrying only LICENSE makes
#: impossible. The notice is load-bearing here: it records which prior-art
#: checkouts were read and that no code came from them.
EXPECTED_LICENSE_FILES = [LICENSE_FILE, "NOTICE"]
LICENSE_PAYLOADS = {name: (ROOT / name).read_bytes() for name in EXPECTED_LICENSE_FILES}
#: The declared files other than the one the licence-content cases mutate.
COMPANION_LICENSE_PAYLOADS = {
    name: payload
    for name, payload in LICENSE_PAYLOADS.items()
    if name != LICENSE_FILE
}
REQUIRES_PYTHON = PROJECT["requires-python"]
DEPENDENCIES = list(PROJECT["dependencies"])
NORMALIZED_PROJECT = re.sub(r"[-_.]+", "_", PROJECT_NAME).casefold()
DIST_INFO = f"{NORMALIZED_PROJECT}-{VERSION}.dist-info"
SDIST_ROOT = f"{NORMALIZED_PROJECT}-{VERSION}"

SPEC = spec_from_file_location(
    f"_verify_distribution_{PACKAGE_NAME}",
    ROOT / "scripts/verify_distribution.py",
)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


#: The metadata headers this project emits exactly once, with the value each
#: must carry. Keeping them in one tuple is what lets the missing/duplicate/
#: wrong parametrization below cover the owner metadata for free.
SINGLETON_METADATA = (
    ("Name", PROJECT_NAME),
    ("Version", VERSION),
    ("Requires-Python", REQUIRES_PYTHON),
    ("License-Expression", EXPECTED_LICENSE),
    ("Author-email", EXPECTED_AUTHOR_EMAIL),
)
# `License-File` used to live in the tuple above, and could, while `LICENSE`
# was the only declared licence. It moved out when NOTICE joined it: the header
# is emitted once per declared file, so asserting it appears exactly once would
# now assert the NOTICE is missing. Its missing/duplicate/wrong coverage did not
# move out with it — see test_rejects_a_wrong_license_file_header_set below.


def _metadata(
    *,
    singletons: dict[str, list[str]] | None = None,
    classifiers: list[str] | None = None,
    dependencies: list[str] | None = None,
    project_urls: list[str] | None = None,
    license_files: list[str] | None = None,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> bytes:
    singleton_values = {header: [value] for header, value in SINGLETON_METADATA}
    if singletons:
        singleton_values.update(singletons)

    lines = ["Metadata-Version: 2.4"]
    for header, _ in SINGLETON_METADATA:
        lines.extend(f"{header}: {value}" for value in singleton_values[header])
    lines.extend(
        f"License-File: {value}"
        for value in (
            EXPECTED_LICENSE_FILES if license_files is None else license_files
        )
    )
    lines.extend(
        f"Project-URL: {value}"
        for value in (
            EXPECTED_PROJECT_URLS if project_urls is None else project_urls
        )
    )
    lines.extend(
        f"Classifier: {value}"
        for value in (
            sorted(EXPECTED_CLASSIFIERS) if classifiers is None else classifiers
        )
    )
    lines.extend(
        f"Requires-Dist: {value}"
        for value in (DEPENDENCIES if dependencies is None else dependencies)
    )
    lines.extend(f"{header}: {value}" for header, value in extra_headers)
    return ("\n".join(lines) + "\n\n").encode()


def _zip_info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (mode | 0o644) << 16
    info.compress_type = zipfile.ZIP_STORED
    return info


def _write_wheel(
    directory: Path,
    *,
    metadata: bytes | None = None,
    include_metadata: bool = True,
    marker: bytes | None = b"",
    marker_info: zipfile.ZipInfo | None = None,
    license_text: bytes | None = LICENSE_TEXT,
    license_info: zipfile.ZipInfo | None = None,
    dist_info: str = DIST_INFO,
    extra_names: tuple[str, ...] = (),
    extra_infos: tuple[zipfile.ZipInfo, ...] = (),
    duplicate_name: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
    filename: str | None = None,
) -> Path:
    path = directory / (
        filename or f"{NORMALIZED_PROJECT}-{VERSION}-py3-none-any.whl"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, mode="w", compression=compression) as archive:
            if marker is not None:
                if marker_info is None:
                    archive.writestr(f"{PACKAGE_NAME}/py.typed", marker)
                else:
                    archive.writestr(marker_info, marker)
            if license_text is not None:
                if license_info is None:
                    archive.writestr(
                        f"{dist_info}/licenses/{LICENSE_FILE}", license_text
                    )
                else:
                    archive.writestr(license_info, license_text)
            # Written unconditionally, including when the case above withholds
            # LICENSE: the licence-content cases must fail because of the file
            # they target, not because a second declared file went missing too.
            for companion, payload in COMPANION_LICENSE_PAYLOADS.items():
                archive.writestr(f"{dist_info}/licenses/{companion}", payload)
            if include_metadata:
                archive.writestr(
                    f"{dist_info}/METADATA",
                    _metadata() if metadata is None else metadata,
                )
            for name in extra_names:
                archive.writestr(name, b"extra")
            for info in extra_infos:
                archive.writestr(info, b"target")
            if duplicate_name is not None:
                archive.writestr(duplicate_name, b"first")
                archive.writestr(duplicate_name, b"second")
    return path


def _tar_info(
    name: str,
    *,
    member_type: bytes = tarfile.REGTYPE,
    data: bytes = b"",
    linkname: str = "",
) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.type = member_type
    info.mode = 0o644
    info.linkname = linkname
    if member_type in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.CONTTYPE}:
        info.size = len(data)
    return info, data


def _write_sdist(
    directory: Path,
    *,
    metadata: bytes | None = None,
    include_metadata: bool = True,
    marker: bytes | None = b"",
    license_text: bytes | None = None,
    missing: tuple[str, ...] = (),
    root: str = SDIST_ROOT,
    extra_members: tuple[tuple[tarfile.TarInfo, bytes], ...] = (),
    overrides: dict[str, tuple[bytes, bytes, str]] | None = None,
    duplicate_name: str | None = None,
    gzip: bool = True,
) -> Path:
    path = directory / f"{NORMALIZED_PROJECT}-{VERSION}.tar.gz"
    files: dict[str, bytes] = {
        "README.md": b"readme\n",
        "CHANGELOG.md": b"changelog\n",
        "SECURITY.md": b"security\n",
        "docs/RELEASE.md": b"release\n",
        # Not filler like its neighbours: the verifier compares this against
        # the checkout's own LICENSE, so the valid fixture must carry the
        # real bytes.
        LICENSE_FILE: LICENSE_TEXT if license_text is None else license_text,
        **COMPANION_LICENSE_PAYLOADS,
        f"src/{PACKAGE_NAME}/py.typed": b"" if marker is None else marker,
        "PKG-INFO": _metadata() if metadata is None else metadata,
    }
    if marker is None:
        files.pop(f"src/{PACKAGE_NAME}/py.typed")
    if not include_metadata:
        files.pop("PKG-INFO")
    for relative_path in missing:
        files.pop(relative_path, None)

    mode = "w:gz" if gzip else "w"
    with tarfile.open(path, mode=mode) as archive:
        root_info = tarfile.TarInfo(root)
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        archive.addfile(root_info)

        override_values = overrides or {}
        for relative_path, data in files.items():
            if relative_path in override_values:
                member_type, override_data, linkname = override_values[relative_path]
                info, payload = _tar_info(
                    f"{root}/{relative_path}",
                    member_type=member_type,
                    data=override_data,
                    linkname=linkname,
                )
            else:
                info, payload = _tar_info(f"{root}/{relative_path}", data=data)
            archive.addfile(
                info,
                BytesIO(payload)
                if info.type in {
                    tarfile.REGTYPE,
                    tarfile.AREGTYPE,
                    tarfile.CONTTYPE,
                }
                else None,
            )

        for info, payload in extra_members:
            archive.addfile(
                info,
                BytesIO(payload)
                if info.type in {
                    tarfile.REGTYPE,
                    tarfile.AREGTYPE,
                    tarfile.CONTTYPE,
                }
                else None,
            )

        if duplicate_name is not None:
            for payload in (b"first", b"second"):
                info, data = _tar_info(duplicate_name, data=payload)
                archive.addfile(info, BytesIO(data))
    return path


def _valid_pair(directory: Path) -> tuple[Path, Path]:
    return _write_wheel(directory), _write_sdist(directory)


def _assert_rejected(
    capsys: pytest.CaptureFixture[str],
    arguments: list[Path | str],
) -> None:
    try:
        exit_code = VERIFIER.main([str(argument) for argument in arguments])
    except Exception as error:
        pytest.fail(f"ordinary exception escaped CLI boundary: {type(error).__name__}")
    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err == FAILURE_MESSAGE


def _pair_with_metadata(
    directory: Path,
    target: str,
    metadata: bytes,
) -> tuple[Path, Path]:
    wheel = _write_wheel(
        directory,
        metadata=metadata if target == "wheel" else _metadata(),
    )
    sdist = _write_sdist(
        directory,
        metadata=metadata if target == "sdist" else _metadata(),
    )
    return wheel, sdist


def _mark_zip_encrypted(path: Path) -> None:
    data = bytearray(path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = 0
        while True:
            position = data.find(signature, start)
            if position < 0:
                break
            flags = struct.unpack_from("<H", data, position + flag_offset)[0]
            struct.pack_into("<H", data, position + flag_offset, flags | 1)
            start = position + len(signature)
    path.write_bytes(data)


def test_source_release_metadata_is_exact() -> None:
    assert PROJECT["name"] == PROJECT_NAME
    assert PROJECT["version"] == "1.1.1"
    assert PROJECT["requires-python"] == ">=3.11"
    assert PROJECT["keywords"] == EXPECTED_KEYWORDS
    assert set(PROJECT["classifiers"]) == EXPECTED_CLASSIFIERS
    assert len(PROJECT["classifiers"]) == len(EXPECTED_CLASSIFIERS)
    # The three public-release blockers this project used to forbid outright.
    assert PROJECT["license"] == EXPECTED_LICENSE
    assert PROJECT["license-files"] == EXPECTED_LICENSE_FILES
    assert PROJECT["authors"] == EXPECTED_AUTHORS
    assert PROJECT["urls"] == EXPECTED_URLS
    # PEP 639 forbids pairing the SPDX expression with a License classifier,
    # and setuptools>=77 is the floor that understands either one.
    assert not any(
        value.casefold().startswith("license ::") for value in PROJECT["classifiers"]
    )
    assert CONFIGURATION["build-system"]["requires"] == ["setuptools>=77", "wheel"]
    # Still forbidden: setuptools would turn it into a `Maintainer-email`
    # header, which the distribution contract rejects.
    assert "maintainers" not in PROJECT
    assert CONFIGURATION["tool"]["setuptools"]["package-data"][PACKAGE_NAME] == [
        "py.typed"
    ]

    marker = ROOT / "src" / PACKAGE_NAME / "py.typed"
    assert marker.is_file()
    assert marker.read_bytes() == b""
    license_path = ROOT / LICENSE_FILE
    assert license_path.is_file()
    license_lines = license_path.read_text(encoding="utf-8").splitlines()
    assert license_lines[1].strip() == "Apache License"
    assert license_lines[2].strip() == "Version 2.0, January 2004"
    # The verbatim appendix placeholders stay as upstream ships them.
    assert "Copyright [yyyy] [name of copyright owner]" in "\n".join(license_lines)
    for relative_path in (
        "MANIFEST.in",
        "CHANGELOG.md",
        "SECURITY.md",
        "docs/RELEASE.md",
        # The README's verification record was moved here, not deleted, so the
        # file's existence is now itself a guarantee worth holding.
        VERIFICATION_DOCUMENT,
        "scripts/verify_distribution.py",
        ".github/workflows/ci.yml",
    ):
        assert (ROOT / relative_path).is_file()


def test_package_version_matches_project_metadata() -> None:
    """One version, two places that state it, and a gate between them.

    `srt_mobile_api.__version__` is what an installed caller can read; the
    pyproject `version` is what the wheel and sdist are named and stamped with.
    Nothing in the build derives one from the other, so a release that bumps
    only pyproject would ship a package that misreports itself.

    Deliberately a two-way check only. This package's default `User-Agent`
    impersonates the SRT Android app (config.py:5-9), so it is pinned to the
    app's version, not to the library's, and dragging it in here would be
    wrong.
    """
    import srt_mobile_api

    assert srt_mobile_api.__version__ == VERSION
    assert "__version__" not in srt_mobile_api.__all__


def test_only_repository_root_env_file_is_ignored() -> None:
    def is_ignored(path: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode in {0, 1}
        assert result.stdout == ""
        assert result.stderr == ""
        return result.returncode == 0

    assert is_ignored(".env")
    assert not is_ignored(".env.backup")
    assert not is_ignored("nested/.env")


def test_valid_pair_is_accepted_in_either_argument_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel, sdist = _valid_pair(tmp_path)
    assert VERIFIER.main([str(sdist), str(wheel)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        "distribution contract verified: "
        f"wheel={wheel.name} sdist={sdist.name}\n"
    )


# `scripts/verify_distribution.py` is a byte-identical file in this repository
# and in the sibling korail-mobile-api one -- it derives everything it checks
# from `pyproject.toml`, so there is nothing repo-specific left in it. The
# parsers below used to be covered on the korail side only, which meant half of
# the shared gate shipped here with no test behind it. These exercise the three
# pyproject readers directly, because reaching them through a built archive can
# only show that a good pyproject passes, never that a bad one is refused.
@pytest.mark.parametrize(
    "value",
    (
        None,
        [],
        ["LICEN[CS]E*"],
        ["LICENSE*"],
        ["LICENSE?"],
        [LICENSE_FILE, LICENSE_FILE],
        [""],
        [f"/{LICENSE_FILE}"],
        [b"LICENSE"],
        "LICENSE",
    ),
)
def test_license_files_must_be_unique_literal_paths(value: object) -> None:
    """A glob is legal PEP 639 and useless to a verifier.

    `license-files = ["LICEN[CS]E*"]` builds fine, but leaves this script unable
    to name the file it is supposed to require -- which is how a presence check
    quietly stops checking anything.
    """
    project = {} if value is None else {"license-files": value}
    with pytest.raises(VERIFIER.ContractError):
        VERIFIER._license_files(ROOT, project)


@pytest.mark.parametrize("problem", ("absent", "empty", "directory"))
def test_license_files_must_name_readable_non_empty_files_in_the_checkout(
    tmp_path: Path,
    problem: str,
) -> None:
    """The declared path is resolved against the checkout, not merely parsed.

    Those bytes are what both artifacts are later compared against, so a blank
    or missing licence in the checkout would make the comparison vacuous: an
    empty file copied into both archives matches itself.
    """
    if problem == "empty":
        (tmp_path / LICENSE_FILE).write_bytes(b"  \n\t\n")
    elif problem == "directory":
        (tmp_path / LICENSE_FILE).mkdir()
    with pytest.raises(VERIFIER.ContractError):
        VERIFIER._license_files(tmp_path, {"license-files": [LICENSE_FILE]})


def test_license_files_carries_the_checkouts_own_bytes() -> None:
    """The positive that makes the negatives above mean something."""
    declared = VERIFIER._license_files(ROOT, {"license-files": EXPECTED_LICENSE_FILES})
    assert declared == tuple(LICENSE_PAYLOADS.items())
    assert b"Apache License" in declared[0][1]
    assert b"Apache License" in dict(declared)["NOTICE"]


@pytest.mark.parametrize(
    "value",
    (
        None,
        [],
        [*EXPECTED_AUTHORS, {"name": "b", "email": "b@example.invalid"}],
        [{"name": "yakisoba0728"}],
        [{"email": "yakihyuk0728@gmail.com"}],
        [{"name": "", "email": "a@example.invalid"}],
        [{"name": "a", "email": ""}],
        [{"name": "a <b>", "email": "a@example.invalid"}],
        [{"name": "a, b", "email": "a@example.invalid"}],
        [{"name": "a", "email": "a@example.invalid, b@example.invalid"}],
        [{"name": " a ", "email": "a@example.invalid"}],
        [{"name": "a", "email": "a@example.invalid", "extra": "x"}],
    ),
)
def test_author_email_requires_exactly_one_unambiguous_owner(value: object) -> None:
    """Two authors become one comma-joined header whose order nothing pins.

    The `<`, `>` and `,` rejections matter for the same reason: they are the
    characters that would let a name forge a second address inside the single
    `Author-email` header this verifier asserts an exact value for.
    """
    project = {} if value is None else {"authors": value}
    with pytest.raises(VERIFIER.ContractError):
        VERIFIER._author_email(project)


@pytest.mark.parametrize(
    "value",
    (
        None,
        {},
        {"Homepage": CANONICAL_URL.replace("https://", "http://")},
        {"Home, page": CANONICAL_URL},
        {"Homepage": ""},
        {"Homepage": f" {CANONICAL_URL}"},
        {"Homepage": 1},
    ),
)
def test_project_urls_must_be_labelled_https_entries(value: object) -> None:
    """A comma in a label would split into a second, unasserted `Project-URL`."""
    project = {} if value is None else {"urls": value}
    with pytest.raises(VERIFIER.ContractError):
        VERIFIER._project_urls(project)


@pytest.mark.parametrize(
    "classifiers",
    (["License :: OSI Approved :: Apache Software License"],),
)
def test_license_expression_and_license_classifiers_are_mutually_exclusive(
    classifiers: list[str],
) -> None:
    with pytest.raises(VERIFIER.ContractError):
        VERIFIER._license_expression({"license": EXPECTED_LICENSE}, classifiers)


@pytest.mark.parametrize("value", (None, "", "   ", {"text": "Apache-2.0"}, 1))
def test_license_expression_must_be_a_non_empty_spdx_string(value: object) -> None:
    """The deprecated `license = {text = ...}` table must not come back."""
    project = {} if value is None else {"license": value}
    with pytest.raises(VERIFIER.ContractError):
        VERIFIER._license_expression(project, [])


def test_the_repository_pyproject_satisfies_every_contract_rule() -> None:
    """The negatives above are only meaningful if the positive still holds."""
    contract = VERIFIER._project_contract()
    assert contract.license_expression == EXPECTED_LICENSE
    assert contract.license_files == tuple(LICENSE_PAYLOADS.items())
    assert contract.author_email == EXPECTED_AUTHOR_EMAIL
    assert set(contract.project_urls) == set(EXPECTED_PROJECT_URLS)
    assert len(contract.project_urls) == len(EXPECTED_PROJECT_URLS)


def test_rejects_wrong_argument_count_and_artifact_types(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel, sdist = _valid_pair(tmp_path)
    unexpected = tmp_path / "unexpected.zip"
    unexpected.write_bytes(b"not an artifact")
    for arguments in (
        [],
        [wheel],
        [wheel, wheel],
        [sdist, sdist],
        [wheel, sdist, unexpected],
        [wheel, unexpected],
    ):
        _assert_rejected(capsys, list(arguments))


NONCANONICAL_NAMES = (
    r"segment\backslash.txt",
    "/absolute.txt",
    "C:/drive.txt",
    "segment//empty.txt",
    "segment/./dot.txt",
    "segment/../traversal.txt",
    "segment/control\x01.txt",
)


@pytest.mark.parametrize("archive_kind", ("wheel", "sdist"))
@pytest.mark.parametrize("bad_name", NONCANONICAL_NAMES)
def test_rejects_noncanonical_archive_member_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    archive_kind: str,
    bad_name: str,
) -> None:
    wheel, sdist = _valid_pair(tmp_path)
    name = bad_name.encode().decode("unicode_escape")
    if archive_kind == "wheel":
        wheel.unlink()
        wheel = _write_wheel(tmp_path, extra_names=(name,))
    else:
        sdist.unlink()
        if not name.startswith("/") and not re.match(r"^[A-Za-z]:", name):
            name = f"{SDIST_ROOT}/{name}"
        info, data = _tar_info(name, data=b"bad")
        sdist = _write_sdist(tmp_path, extra_members=((info, data),))
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("archive_kind", ("wheel", "sdist"))
def test_rejects_duplicate_normalized_member_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    archive_kind: str,
) -> None:
    wheel, sdist = _valid_pair(tmp_path)
    if archive_kind == "wheel":
        wheel.unlink()
        wheel = _write_wheel(tmp_path, duplicate_name="duplicate.txt")
    else:
        sdist.unlink()
        sdist = _write_sdist(
            tmp_path,
            duplicate_name=f"{SDIST_ROOT}/README.md",
        )
    _assert_rejected(capsys, [wheel, sdist])


FORBIDDEN_MEMBER_COMPONENTS = (
    ".local-live-smoke.env",
    ".local-live-smoke.env.backup",
    "application.apk",
    "application.apk.bak",
    ".DS_Store",
    ".DS_Store.backup",
    ".worktrees",
    ".worktrees.old",
    ".git",
    ".git.backup",
    "analysis",
    "analysis-copy",
    "build",
    "build_old",
    "dist",
    "dist~",
    "site",
    "site-old",
    ".pytest_cache",
    ".pytest_cache.backup",
    "__pycache__",
    "__pycache__.old",
    "module.pyc",
    "module.pyc.backup",
)


@pytest.mark.parametrize("archive_kind", ("wheel", "sdist"))
@pytest.mark.parametrize("component", FORBIDDEN_MEMBER_COMPONENTS)
def test_rejects_every_forbidden_member_family_and_backup_variant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    archive_kind: str,
    component: str,
) -> None:
    wheel, sdist = _valid_pair(tmp_path)
    if archive_kind == "wheel":
        wheel.unlink()
        wheel = _write_wheel(tmp_path, extra_names=(f"safe/{component}",))
    else:
        sdist.unlink()
        info, data = _tar_info(
            f"{SDIST_ROOT}/safe/{component}",
            data=b"bad",
        )
        sdist = _write_sdist(tmp_path, extra_members=((info, data),))
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize(
    "mode",
    (
        stat.S_IFLNK,
        stat.S_IFIFO,
        stat.S_IFCHR,
        stat.S_IFBLK,
        stat.S_IFSOCK,
    ),
)
def test_rejects_zip_links_and_special_member_types(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode: int,
) -> None:
    wheel = _write_wheel(
        tmp_path,
        extra_infos=(_zip_info("special-member", mode),),
    )
    sdist = _write_sdist(tmp_path)
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize(
    "member_type",
    (
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.FIFOTYPE,
        tarfile.CONTTYPE,
    ),
)
def test_rejects_tar_links_devices_fifos_and_special_types(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    member_type: bytes,
) -> None:
    wheel = _write_wheel(tmp_path)
    info, data = _tar_info(
        f"{SDIST_ROOT}/special-member",
        member_type=member_type,
        data=b"bad",
        linkname="target",
    )
    sdist = _write_sdist(tmp_path, extra_members=((info, data),))
    _assert_rejected(capsys, [wheel, sdist])


def test_rejects_non_gzip_sdist_with_tar_gz_suffix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _write_wheel(tmp_path)
    sdist = _write_sdist(tmp_path, gzip=False)
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("root_mode", ("wrong", "multiple"))
def test_requires_one_exact_project_version_sdist_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    root_mode: str,
) -> None:
    wheel = _write_wheel(tmp_path)
    if root_mode == "wrong":
        sdist = _write_sdist(tmp_path, root="wrong-project-9.9.9")
    else:
        extra_root = tarfile.TarInfo("other-root")
        extra_root.type = tarfile.DIRTYPE
        sdist = _write_sdist(tmp_path, extra_members=((extra_root, b""),))
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("marker_state", ("missing", "nonempty", "special"))
def test_requires_regular_zero_byte_typed_markers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    marker_state: str,
) -> None:
    wheel, sdist = _valid_pair(tmp_path)
    if target == "wheel":
        wheel.unlink()
        if marker_state == "special":
            info = _zip_info(f"{PACKAGE_NAME}/py.typed", stat.S_IFLNK)
            wheel = _write_wheel(tmp_path, marker=b"target", marker_info=info)
        else:
            wheel = _write_wheel(
                tmp_path,
                marker=None if marker_state == "missing" else b"not empty",
            )
    else:
        sdist.unlink()
        if marker_state == "special":
            sdist = _write_sdist(
                tmp_path,
                overrides={
                    f"src/{PACKAGE_NAME}/py.typed": (
                        tarfile.SYMTYPE,
                        b"",
                        "target",
                    )
                },
            )
        else:
            sdist = _write_sdist(
                tmp_path,
                marker=None if marker_state == "missing" else b"not empty",
            )
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize(
    "required_document",
    ("README.md", "CHANGELOG.md", "SECURITY.md", "docs/RELEASE.md", *EXPECTED_LICENSE_FILES),
)
def test_requires_each_exact_regular_sdist_document(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    required_document: str,
) -> None:
    wheel = _write_wheel(tmp_path)
    sdist = _write_sdist(tmp_path, missing=(required_document,))
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize(
    ("header", "expected", "wrong"),
    (
        ("Name", PROJECT_NAME, "wrong-project"),
        ("Version", VERSION, "9.9.9"),
        ("Requires-Python", REQUIRES_PYTHON, ">=99"),
        # The owner metadata. A build that says "MIT", credits somebody else,
        # or points License-File at a name the archives do not carry is as
        # wrong as one with the wrong project name -- and before these rows
        # existed, all three headers were simply forbidden.
        ("License-Expression", EXPECTED_LICENSE, "MIT"),
        ("Author-email", EXPECTED_AUTHOR_EMAIL, "somebody <else@example.invalid>"),
    ),
)
@pytest.mark.parametrize("problem", ("missing", "duplicate", "wrong"))
def test_rejects_missing_duplicate_or_wrong_singleton_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    header: str,
    expected: str,
    wrong: str,
    problem: str,
) -> None:
    if problem == "missing":
        values = []
    elif problem == "duplicate":
        values = [expected, expected]
    else:
        values = [wrong]
    wheel, sdist = _pair_with_metadata(
        tmp_path,
        target,
        _metadata(singletons={header: values}),
    )
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("problem", ("missing", "extra", "duplicate"))
def test_requires_the_exact_classifier_set_without_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    problem: str,
) -> None:
    classifiers = sorted(EXPECTED_CLASSIFIERS)
    if problem == "missing":
        classifiers.remove("Programming Language :: Python :: 3.14")
    elif problem == "extra":
        classifiers.append("Operating System :: OS Independent")
    else:
        classifiers.append(classifiers[0])
    wheel, sdist = _pair_with_metadata(
        tmp_path,
        target,
        _metadata(classifiers=classifiers),
    )
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("problem", ("missing", "extra", "duplicate"))
def test_requires_the_exact_normalized_runtime_dependency_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    problem: str,
) -> None:
    dependencies = list(DEPENDENCIES)
    if problem == "missing":
        dependencies = dependencies[1:]
    elif problem == "extra":
        dependencies.append("unexpected-package>=1")
    else:
        dependencies.append(dependencies[0])
    wheel, sdist = _pair_with_metadata(
        tmp_path,
        target,
        _metadata(dependencies=dependencies),
    )
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("problem", ("missing", "extra", "duplicate", "wrong"))
def test_requires_the_exact_project_url_set_without_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    problem: str,
) -> None:
    """The canonical URL is a release blocker, so it is checked, not tolerated.

    `Project-URL` was on the forbidden list until this project had owner
    metadata to publish. Removing it from that list without putting this in its
    place would have let a build point every link at somebody else's repository
    and still pass the gate.
    """
    project_urls = list(EXPECTED_PROJECT_URLS)
    if problem == "missing":
        project_urls.remove(f"Homepage, {CANONICAL_URL}")
    elif problem == "extra":
        project_urls.append("Funding, https://example.invalid/sponsor")
    elif problem == "duplicate":
        project_urls.append(project_urls[0])
    else:
        project_urls[0] = "Homepage, https://github.com/someone-else/srt-mobile-api"
    wheel, sdist = _pair_with_metadata(
        tmp_path,
        target,
        _metadata(project_urls=project_urls),
    )
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("problem", ("missing", "extra", "duplicate", "wrong"))
def test_rejects_a_wrong_license_file_header_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    problem: str,
) -> None:
    """`License-File` is checked as a set, because it stopped being singular.

    It rode the singleton parametrization while `LICENSE` was the only declared
    licence file. NOTICE joining it made "appears exactly once" the wrong
    assertion -- it would have demanded the notice be absent. The coverage the
    singleton row provided is reproduced here against the whole set, so that
    dropping NOTICE from the metadata, inventing a file the archives do not
    carry, or renaming LICENSE to COPYING all still fail the gate.
    """
    license_files = list(EXPECTED_LICENSE_FILES)
    if problem == "missing":
        license_files.remove("NOTICE")
    elif problem == "extra":
        license_files.append("COPYING")
    elif problem == "duplicate":
        license_files.append(license_files[0])
    else:
        license_files[0] = "COPYING"
    wheel, sdist = _pair_with_metadata(
        tmp_path,
        target,
        _metadata(license_files=license_files),
    )
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("problem", ("missing", "empty", "altered", "special"))
def test_requires_the_checkout_license_text_verbatim_in_both_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    problem: str,
) -> None:
    """`License-Expression: Apache-2.0` has to be backed by the actual text.

    A header is a claim. The wheel carries the text at
    `<dist-info>/licenses/LICENSE` and the sdist at the root, and both must
    equal the checkout's own bytes -- otherwise a truncated, empty or edited
    license ships under a correct-looking SPDX header.
    """
    altered = LICENSE_TEXT.replace(b"Apache License", b"Someone Else License", 1)
    assert altered != LICENSE_TEXT
    payload = {"missing": None, "empty": b"", "altered": altered}.get(problem, b"")
    if target == "wheel":
        if problem == "special":
            info = _zip_info(f"{DIST_INFO}/licenses/{LICENSE_FILE}", stat.S_IFLNK)
            wheel = _write_wheel(tmp_path, license_text=b"target", license_info=info)
        else:
            wheel = _write_wheel(tmp_path, license_text=payload)
        sdist = _write_sdist(tmp_path)
    else:
        wheel = _write_wheel(tmp_path)
        if problem == "special":
            sdist = _write_sdist(
                tmp_path,
                overrides={LICENSE_FILE: (tarfile.SYMTYPE, b"", "target")},
            )
        elif problem == "missing":
            sdist = _write_sdist(tmp_path, missing=(LICENSE_FILE,))
        else:
            sdist = _write_sdist(tmp_path, license_text=payload)
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
@pytest.mark.parametrize("header", FORBIDDEN_METADATA_HEADERS)
def test_rejects_forbidden_owner_license_and_url_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    header: str,
) -> None:
    wheel, sdist = _pair_with_metadata(
        tmp_path,
        target,
        _metadata(extra_headers=((header, "forbidden value"),)),
    )
    _assert_rejected(capsys, [wheel, sdist])


def test_requires_exact_dist_info_metadata_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _write_wheel(tmp_path, dist_info="wrong_project-9.9.9.dist-info")
    sdist = _write_sdist(tmp_path)
    _assert_rejected(capsys, [wheel, sdist])


def test_requires_exact_sdist_pkg_info_regular_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _write_wheel(tmp_path)
    missing = _write_sdist(tmp_path, include_metadata=False)
    _assert_rejected(capsys, [wheel, missing])

    missing.unlink()
    special = _write_sdist(
        tmp_path,
        overrides={"PKG-INFO": (tarfile.SYMTYPE, b"", "target")},
    )
    _assert_rejected(capsys, [wheel, special])


@pytest.mark.parametrize("target", ("wheel", "sdist"))
def test_malformed_archive_errors_are_one_fixed_secret_safe_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
) -> None:
    if target == "wheel":
        wheel = tmp_path / "secret-member-name.whl"
        wheel.write_bytes(b"not a zip file")
        sdist = _write_sdist(tmp_path)
    else:
        wheel = _write_wheel(tmp_path)
        sdist = tmp_path / "secret-member-name.tar.gz"
        sdist.write_bytes(b"not a gzip tar file")
    _assert_rejected(capsys, [wheel, sdist])


def test_encrypted_zip_members_cannot_escape_fixed_cli_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _write_wheel(tmp_path)
    _mark_zip_encrypted(wheel)
    sdist = _write_sdist(tmp_path)
    _assert_rejected(capsys, [wheel, sdist])


def test_unsupported_zip_compression_is_rejected_by_fixed_cli_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _write_wheel(tmp_path, compression=zipfile.ZIP_BZIP2)
    sdist = _write_sdist(tmp_path)
    _assert_rejected(capsys, [wheel, sdist])


@pytest.mark.parametrize(
    "forged",
    (
        ("w" * 110) + "\nforged.whl",
        "a\rb\x00c\x1bd.whl",
        ("\n" * 200) + ".whl",
    ),
)
def test_bounded_name_strips_controls_and_caps_length(forged: str) -> None:
    """The sanitiser itself, on names no filesystem would hold.

    This used to be reachable only by creating a file whose basename carried
    the control character, which Windows refuses outright -- so the one
    assertion that mattered ran on two platforms out of three. ``_bounded_name``
    takes a ``Path``, not an open file, so the forged name never has to exist.
    """
    display = VERIFIER._bounded_name(Path(forged))

    assert len(display) <= 96
    assert all(character.isprintable() for character in display)
    assert "\n" not in display


def test_success_output_bounds_the_basename_it_prints(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """And the bound survives the trip through ``main``.

    The name here is long but filesystem-legal everywhere, because this case is
    about the printed line -- one line, no stderr, name capped -- and not about
    the character classes, which the parametrisation above covers directly.
    """
    wheel = _write_wheel(tmp_path, filename=("w" * 110) + "forged.whl")
    sdist = _write_sdist(tmp_path)
    assert VERIFIER.main([str(wheel), str(sdist)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert len(captured.out.splitlines()) == 1
    wheel_display = captured.out.split("wheel=", maxsplit=1)[1].split(
        " sdist=", maxsplit=1
    )[0]
    assert len(wheel_display) <= 96
    assert all(character.isprintable() for character in wheel_display)


def test_ci_and_manual_release_gates_are_structurally_offline_and_fail_fast() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / "docs/RELEASE.md").read_text(encoding="utf-8")
    release_lower = release.casefold()
    offline_command = 'pytest -q -m "not live"'

    for version in ("'3.11'", "'3.12'", "'3.13'", "'3.14'"):
        assert version in workflow
    assert offline_command in workflow
    assert offline_command in release
    assert "run: pytest -q\n" not in workflow
    assert "set -euo pipefail" in release
    assert "cleanup()" in release
    assert "trap cleanup EXIT" in release
    assert release.index("set -euo pipefail") < release.index("artifact_dir=")
    assert "\npython -m " not in release
    assert "\npython scripts/" not in release
    assert release.index("trap cleanup EXIT") < release.index("python3 -m build")
    for forbidden in (
        "twine upload",
        "publish",
        "actions/upload",
        "attest",
        "id-token: write",
        "contents: write",
        "korail_mobile_api_live",
        "srt_mobile_api_live",
    ):
        assert forbidden not in workflow.casefold()
        assert forbidden not in release_lower
    assert not re.search(r"(?m)^\s*release\s*:", workflow)
    assert not re.search(r"(?m)^\s*tags\s*:", workflow)


def _child_pytest(
    *arguments: str,
    environment: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """자식 프로세스로 ``pytest`` 를 돌리고 stdout 을 UTF-8 문자열로 받는다.

    ``PYTHONIOENCODING`` 을 세우는 것이 이 함수의 존재 이유다. 파이프에 묶인 자식
    파이썬은 stdout 인코딩을 로케일에서 가져오므로 한국어 Windows 에서는 cp949 로
    쓴다. 이 스위트에는 함수 이름에 한글이 든 테스트가 있어서
    (``test_three_person_minimum_belongs_to_exactly_다자녀_and_3세대``)
    ``--collect-only`` 출력이 그대로 cp949 바이트가 되고, 그것을 부모가 UTF-8 로
    읽으면 ``subprocess`` 의 읽기 스레드가 ``UnicodeDecodeError`` 로 죽어
    ``result.stdout`` 이 문자열이 아니라 ``None`` 이 된다. 자식 쪽 인코딩을
    못박는 것이 부모 쪽에서 ``errors="replace"`` 로 덮는 것보다 낫다 — 뒤엣것은
    깨진 글자를 통과시켜 놓고 고쳐진 척한다.

    ``timeout`` 은 호출자가 정한다. Windows 에서 pytest 의 콜드 스타트가 눈에
    띄게 느려서, 이 값은 "이 하위 프로세스가 멈추지 않았다"만 보장하며 성능을
    재지 않는다.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", *arguments],
        cwd=ROOT,
        env={**environment, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def test_ambient_live_opt_in_is_deselected_by_the_release_command() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / "docs/RELEASE.md").read_text(encoding="utf-8")
    offline_command = 'pytest -q -m "not live"'
    assert offline_command in workflow and offline_command in release

    environment = os.environ.copy()
    environment[LIVE_ENV] = "1"
    result = _child_pytest(
        "-q",
        "-m",
        "not live",
        "tests/test_live_service.py",
        environment=environment,
        timeout=60,
    )
    assert result.returncode == 5
    assert "1 deselected" in result.stdout

#: ``pytest --collect-only -q`` tail, in both spellings it can take: with
#: something deselected it reports ``1665/1666 tests collected (1 deselected)``,
#: and with nothing deselected just ``1666 tests collected``.
_COLLECTED_RE = re.compile(
    r"(?m)^(?:(?P<selected>\d+)/(?P<total>\d+)|(?P<only>\d+)) tests? collected"
    r"(?: \((?P<deselected>\d+) deselected\))?"
)


def _collected_offline_test_count() -> tuple[int, int]:
    """How many tests ``-m "not live"`` actually selects, and how many it drops.

    Collection rather than a run: it is the same selection the README sentence
    describes, it costs a fraction of a second, and a suite that RUNS itself to
    check its own count would double every future test's cost.

    The environment is scrubbed of the live opt-in on purpose. The neighbouring
    test sets it deliberately, and a count that quietly depended on an ambient
    variable would be no better than the hardcoded string this replaced.
    """
    environment = os.environ.copy()
    environment.pop(LIVE_ENV, None)
    result = _child_pytest(
        "-q",
        "-m",
        "not live",
        "--collect-only",
        environment=environment,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    match = _COLLECTED_RE.search(result.stdout)
    assert match is not None, result.stdout[-2000:]
    selected = int(match.group("selected") or match.group("only"))
    return selected, int(match.group("deselected") or 0)


# The README used to be BOTH the front door and the audit log: 1,835 lines whose
# first "##" heading sat at line 488. On 2026-07-26 the audit log moved into
# docs/VERIFICATION.md so the README could serve a reader who wants to USE the
# library. Every pin below moved with the claim it protects rather than being
# dropped -- a fact that stops being checked is a fact that starts drifting.
#
#   STAYED in the README, because a user needs them at the front door:
#     "installable read-only" / not "analysis workspace"  (what this repo IS)
#     "26 routes"                                          (the read boundary)
#     the offline gate count / "1 deselected"              (the offline gate)
#     "iter_train_search_pages"                            (a public method)
#     "docs/RELEASE.md"                                    (the release gate)
#
#   MOVED to docs/VERIFICATION.md, because each is an EVIDENCE record:
#     the live pagination continuation, the seat-layout sufficiency verdict,
#     the four seat-grid truths, and (below) the whole cancel/payment/refund
#     provenance family.
def test_repository_truth_and_full_mutation_policy() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_lower = readme.casefold()
    progress = (ROOT / "docs/IMPLEMENTATION_PROGRESS.md").read_text(encoding="utf-8")
    progress_lower = progress.casefold()
    progress_flat = " ".join(progress_lower.split())
    verification = (ROOT / VERIFICATION_DOCUMENT).read_text(encoding="utf-8")
    verification_lower = verification.casefold()
    verification_flat = " ".join(verification_lower.split())
    # The README is Korean, so the two phrases pinned here are Korean. They are
    # the same two claims the English pins carried -- WHAT this repository is
    # ("설치 가능한 기본 읽기 전용 패키지"), and what it must never call itself
    # again -- and both spellings of the negative stay, because the English one
    # costs nothing and an English sentence reappearing would be as wrong as a
    # Korean one.
    assert "설치 가능한 기본 읽기 전용 패키지" in readme
    assert "analysis workspace" not in readme_lower
    assert "분석 워크스페이스" not in readme
    # The read-only boundary, asked of the code rather than typed twice. This
    # used to be `assert "26 routes" in readme`: a literal on both sides, so the
    # allowlist could grow while the README kept saying 26 and this line kept
    # passing. Now the number comes from the allowlist itself, and the sentence
    # around it is pinned too so a bare "26개" elsewhere cannot satisfy it.
    assert f"읽기 전용 경로 {len(READ_ONLY_ROUTES)}개" in readme
    # The CURRENT offline count. This used to read
    #
    #     assert "1607 passed" in readme
    #
    # under a comment claiming it was "a real gate ... it must be updated
    # whenever the suite grows". It was not a gate at all: it compared the
    # README against a hardcoded string, so both could say 1607 while the suite
    # actually ran 1662, which is exactly what had happened. A number kept by
    # hand in two places drifts in both.
    #
    # So ask the suite instead. _collected_offline_test_count() is the same
    # `-m "not live"` selection the README sentence describes, and the README
    # must state THAT number -- which no longer needs updating "whenever the
    # suite grows", because a stale README now fails here on its own.
    #
    # (docs/VERIFICATION.md also cites the historical 0.2.0 figure, and
    # docs/IMPLEMENTATION_PROGRESS.md keeps a log of past gates; both are
    # labelled historical and neither is asserted here, because a frozen number
    # can never fail.)
    collected, deselected = _collected_offline_test_count()
    assert f"{collected} passed" in readme
    assert f"{deselected} deselected" in readme
    assert "iter_train_search_pages" in readme
    assert "live continuation was verified" in verification_lower
    assert "personal and group each returned two pages" in verification_lower
    assert "inventory_source_candidate" in verification
    # Both documents must state the CURRENT truth about the seat-grid route.
    # Two of these entries used to be "not allowlisted" and "no closed response
    # parser"; the 2026-07-26 live read made both false, and the fix for a
    # truth pin that has gone stale is to re-pin the new truth, not to drop it.
    # The padding is pinned here because it is the one fact the endpoint turned
    # on, and a document that omits it would send the next reader back to
    # believing the alert shell's timing story.
    #
    # "Both documents" used to mean README + IMPLEMENTATION_PROGRESS. It now
    # means VERIFICATION + IMPLEMENTATION_PROGRESS: the point was always that
    # two INDEPENDENT documents carry the fact, and the README is no longer one
    # of the documents that carries evidence.
    for evidence_truth in (
        "seat_page_schema_v2_evidence.json",
        "/arc/selectListArc02011_n.do",
        "zero-padded to five",
        "parse_seat_grid_response",
    ):
        assert evidence_truth.casefold() in verification_flat
        assert evidence_truth.casefold() in progress_flat
    assert "docs/RELEASE.md" in readme
    # Moving the record only preserves it if it stays FINDABLE. The README must
    # keep pointing at its new home, or the evidence becomes a file nobody opens.
    assert VERIFICATION_DOCUMENT in readme

    specification = (
        ROOT / "docs/analysis/srt-app-api-library-spec-2026-07-09.md"
    ).read_text(encoding="utf-8")
    section_twelve = specification.split("## 12.", maxsplit=1)[1].split(
        "## 13.", maxsplit=1
    )[0]
    for retained_content in (
        "src/srt_mobile_api/",
        "tests/",
        "docs/IMPLEMENTATION_PROGRESS.md",
        "docs/internal/superpowers/specs/",
        "README.md",
        "scripts/srt_app_api_smoke.py",
    ):
        # Section 12 must list it AND it must actually still be in the tree,
        # so the retained-file table cannot drift away from the repository.
        assert retained_content in section_twelve
        assert (ROOT / retained_content).exists()

    # docs/superpowers/plans/ is the opposite case: it was removed after the
    # plans were executed. Section 12 must keep saying so, and the directory
    # must stay gone.
    assert not (ROOT / "docs/superpowers/plans").exists()
    assert "| `docs/superpowers/plans/`" not in section_twelve
    assert "execution plans formerly under `docs/superpowers/plans/` were" in section_twelve
    assert "removed after implementation" in section_twelve

    policy = specification.casefold()
    forbidden_recommendations = (
        "reservationclient",
        "paymententryclient",
        "allow_production_reservation",
        "explicit production-reservation opt-in",
        "dry run validators",
        "must be opt-in",
        "unless the caller explicitly opts in",
    )
    for phrase in forbidden_recommendations:
        assert phrase not in policy
    for requirement in (
        "no flag",
        "no dry-run marker",
        "no confirmation token",
        "separate safety design",
        "new evidence",
        "independent review",
        "explicit user authorization",
    ):
        assert requirement in policy


# Two separate facts about the cancel wire shape have to stay documented
# together, and each is easy to lose by writing only the other:
#
#   * ORIGIN (history, still true). The shape came from srtgo's live runs, and
#     the route is 0-hit across all 21,673 files of the v2.0.41 offline bundle.
#     One live success does not make it statically corroborated, and a reader
#     who is told only "it works" cannot tell how much evidence stands behind
#     the fields the run never exercised.
#   * VERIFICATION (2026-07-25). One operator-run reserve->cancel round trip
#     released a real hold against the live server: SUCC, msgCd IRG000000, and
#     no trace of the reservation left in the ticket list.
#
# Until that run this test pinned "srtgo-attested AND unconfirmed". The
# unconfirmed half is now obsolete, but simply deleting the pin would let the
# origin disappear with it, so the pin is inverted rather than dropped: the
# documents must now carry the verification AND keep the origin as history.
CANCEL_ROUTE_TOKEN = "ard02045"
# Substance, not sentences: every element may be reworded, but all of them have
# to stay attached to the route rather than merely coexist in the same file.
CANCEL_LIVE_VERIFICATION_DATE = "2026-07-25"
# The Korean spellings were ADDED rather than substituted when CHANGELOG.md was
# translated. Two of the three documents this pin covers are still English, and
# a phrase list that swapped languages would have stopped checking them. Widening
# an `any(...)` keeps every document that already passed passing.
CANCEL_LIVE_VERIFICATION_PHRASES = (
    "live server",
    "live-verified",
    "live verified",
    "verified live",
    "live round trip",
    "live reserve->cancel round trip",
    "라이브 서버",
    "라이브 검증",
    "실서버 검증",
)
# The server's own confirmation code for a successful cancel, and the reserve
# code from the same run. Codes rather than prose: they are the observation, and
# a document that states them is a document that records a real response.
CANCEL_SUCCESS_CODE = "irg000000"
RESERVE_SUCCESS_CODE = "irr000018"
CANCEL_ZERO_EVIDENCE_PHRASES = ("0-hit", "0 hits", "zero hits", "zero-hit")
# One run, one journey, one adult. Without this the codes above read as a
# general "cancel is verified", which is exactly the over-claim to prevent.
CANCEL_VERIFICATION_SCOPE_PHRASES = (
    "single journey",
    "single-journey",
    "one adult",
    "one-adult",
    # Korean, added alongside the English rather than replacing it — see the
    # note on CANCEL_LIVE_VERIFICATION_PHRASES.
    "성인 1명",
    "편도 1건",
)
CANCEL_PROVENANCE_WINDOW = 900
# README.md was the first of these three until 2026-07-26. The provenance record
# is a dense paragraph of route tokens, confirmation codes, scope limits and
# 0-hit counts -- exactly the material that made the README unreadable -- so it
# moved to docs/VERIFICATION.md and the pin followed it there. It did not become
# weaker by moving: it is the same window, the same seven elements, over three
# documents that each have to state the whole thing independently.
CANCEL_PROVENANCE_DOCUMENTS = (
    VERIFICATION_DOCUMENT,
    "docs/IMPLEMENTATION_PROGRESS.md",
    "CHANGELOG.md",
)


def test_cancel_documentation_records_the_live_verification_and_its_srtgo_origin() -> None:
    for document in CANCEL_PROVENANCE_DOCUMENTS:
        flat = " ".join((ROOT / document).read_text(encoding="utf-8").casefold().split())
        assert CANCEL_ROUTE_TOKEN in flat, document
        # The other half of the same round trip: a document describing the
        # verification without reserve's code describes only half of it.
        assert RESERVE_SUCCESS_CODE in flat, document
        # A window around each mention of the cancel route, so the record has to
        # stay ATTACHED to it: "srtgo", "2.0.41" and the date are all named
        # elsewhere in these documents for unrelated reasons.
        windows = [
            flat[max(0, offset - CANCEL_PROVENANCE_WINDOW) : offset + CANCEL_PROVENANCE_WINDOW]
            for offset in range(len(flat))
            if flat.startswith(CANCEL_ROUTE_TOKEN, offset)
        ]
        assert any(
            # The verification, with the response the server actually gave.
            CANCEL_LIVE_VERIFICATION_DATE in window
            and any(phrase in window for phrase in CANCEL_LIVE_VERIFICATION_PHRASES)
            and CANCEL_SUCCESS_CODE in window
            # and its limits, so one round trip cannot read as a general proof.
            and any(phrase in window for phrase in CANCEL_VERIFICATION_SCOPE_PHRASES)
            # and the origin, unchanged by the run and still worth knowing.
            and "srtgo" in window
            and "2.0.41" in window
            and any(phrase in window for phrase in CANCEL_ZERO_EVIDENCE_PHRASES)
            for window in windows
        ), document


# The same two-facts-together rule, applied to payment and refund. It is the
# identical pattern to the cancel pin above and exists for the identical reason:
# on 2026-07-26 a live round trip refuted the "cannot be transmitted / never
# observed" claim these documents carried, and deleting the pin would have let
# the ORIGIN vanish along with the retired claim. So the pin is inverted rather
# than dropped -- the documents must now carry the verification AND keep saying
# where the shapes came from, because that is still the whole of the static
# evidence and it did not improve.
#
# These two surfaces need one thing cancel's pin did not: the SCOPE phrase has
# to survive as well, since "payment works" is a far more expensive over-claim
# than "cancel works".
PAYMENT_ROUTE_TOKEN = "ata09036"
REFUND_ROUTE_TOKEN = "atc02063"
PAYMENT_REFUND_VERIFICATION_DATE = "2026-07-26"
PAYMENT_SUCCESS_CODE = "irt000000"
REFUND_SUCCESS_CODE = "irt200277"
# The free probe that preceded the real round trip. Recorded because it is what
# established the routes EXIST without spending anything, and a document that
# keeps only the success story loses the cheap half of the method.
PAYMENT_PROBE_CODE = "wrt100170"
REFUND_PROBE_CODE = "wrt300005"
PAYMENT_REFUND_PROVENANCE_WINDOW = 1200


@pytest.mark.parametrize(
    ("route_token", "success_code"),
    [
        (PAYMENT_ROUTE_TOKEN, PAYMENT_SUCCESS_CODE),
        (REFUND_ROUTE_TOKEN, REFUND_SUCCESS_CODE),
    ],
)
def test_payment_and_refund_documentation_records_the_live_verification_and_its_origin(
    route_token: str, success_code: str
) -> None:
    for document in CANCEL_PROVENANCE_DOCUMENTS:
        flat = " ".join((ROOT / document).read_text(encoding="utf-8").casefold().split())
        assert route_token in flat, document
        windows = [
            flat[
                max(0, offset - PAYMENT_REFUND_PROVENANCE_WINDOW) : offset
                + PAYMENT_REFUND_PROVENANCE_WINDOW
            ]
            for offset in range(len(flat))
            if flat.startswith(route_token, offset)
        ]
        assert any(
            # The verification, with the code the server actually gave.
            PAYMENT_REFUND_VERIFICATION_DATE in window
            and any(
                phrase in window for phrase in CANCEL_LIVE_VERIFICATION_PHRASES
            )
            and success_code in window
            # and its limits, so one round trip cannot read as a general proof.
            and any(
                phrase in window for phrase in CANCEL_VERIFICATION_SCOPE_PHRASES
            )
            # and the origin, unchanged by the run and still the only static
            # evidence there is.
            and "srtgo" in window
            and "2.0.41" in window
            and any(phrase in window for phrase in CANCEL_ZERO_EVIDENCE_PHRASES)
            for window in windows
        ), document


def test_payment_and_refund_documentation_records_the_free_probe_that_came_first() -> None:
    # The probe is method, not trivia: it is how the routes were shown to exist
    # before any money moved, and it is the part a future reader would otherwise
    # have to reinvent. Both codes must appear somewhere in each document.
    for document in CANCEL_PROVENANCE_DOCUMENTS:
        flat = " ".join((ROOT / document).read_text(encoding="utf-8").casefold().split())
        assert PAYMENT_PROBE_CODE in flat, document
        assert REFUND_PROBE_CODE in flat, document


def test_no_current_state_document_still_claims_payment_or_refund_cannot_transmit() -> None:
    # The retired claim, pinned as retired. Every one of these sentences was in
    # the tree on 2026-07-25 and every one is now false; a doc edit that
    # reintroduces the wording would be reintroducing a false statement about
    # what this library does with a real card.
    #
    # CHANGELOG.md is deliberately NOT scanned. It is a historical record, and
    # its convention in this repository is to supersede an entry in place rather
    # than rewrite it — so it still quotes "still cannot be transmitted" as the
    # heading of the entry the 2026-07-26 verification retired, which is correct
    # and must stay. The documents below all describe the CURRENT state, where
    # the same words would simply be wrong.
    #
    # The Korean spellings are here because README.md is now Korean. Without
    # them this test would still PASS on that file and would be checking
    # nothing: an English-only phrase list cannot see a Korean sentence, and a
    # pin that cannot fail is the same thing as a deleted pin. The English
    # entries stay -- the other three documents are still English, and an
    # English sentence reappearing anywhere would be exactly as false.
    #
    # A NOTE FOR WHOEVER TRANSLATES THE OTHER THREE DOCUMENTS. 할인쿠폰 등록
    # genuinely cannot transmit, so a sentence saying so is TRUE -- but if that
    # sentence also names 결제 or 환불 ("쿠폰 등록은 결제가 아니므로 전송할 수
    # 없다") this test reads it as the retired claim and fails. Keep 쿠폰
    # statements in a sentence of their own. The English text dodged this only
    # because the subject test was English-only, which was the bug being fixed
    # here rather than a property worth keeping.
    #
    # The Korean entries are STEMS, not whole endings. README.md moved from
    # 반말 to 존댓말 on 2026-07-28, which would have turned "전송할 수 없다" into
    # a phrase the file can no longer contain -- a pin that cannot fire is a
    # deleted pin, and the fix for that is to widen the pin rather than drop it.
    # Cutting each entry before the verb ending matches both registers
    # ("...없다", "...없습니다", "...없으며") with one string, so the next
    # register change cannot silently disarm this test either.
    retired = (
        "cannot be transmitted",
        "cannot transmit",
        "still cannot be sent",
        "never sent by anyone here",
        "no client method",
        "remain unimplemented",
        "stay unimplemented",
        "전송할 수 없",
        "전송될 수 없",
        "보낼 수 없",
        "아무도 보낸 적이 없",
        "클라이언트 메서드가 없",
        "구현되지 않은 채로 남",
        "미구현으로 남",
    )
    # Checked per SENTENCE rather than per character window. A window is the
    # wrong granularity here: "seat holding and selection have no client method
    # at all" is a TRUE sentence that sits two clauses away from the payment
    # method list, and a proximity rule cannot tell it apart from a false one.
    #
    # docs/VERIFICATION.md was ADDED to this list on 2026-07-26, when the
    # README's evidence sections moved into it. It is a current-state document
    # by the same test CHANGELOG.md fails: it describes what the library does
    # now and is amended in place, so the retired wording would simply be wrong
    # in it. Scanning it is a strengthening -- the sentences that carried the
    # highest risk of reintroducing the claim are the ones that moved.
    documents = (
        "README.md",
        VERIFICATION_DOCUMENT,
        "docs/IMPLEMENTATION_PROGRESS.md",
        "SECURITY.md",
    )
    for document in documents:
        flat = " ".join((ROOT / document).read_text(encoding="utf-8").casefold().split())
        for sentence in re.split(r"(?<=[.!?])\s+", flat):
            if not any(phrase in sentence for phrase in retired):
                continue
            assert not any(
                subject in sentence
                # 결제 / 환불: the same two subjects, spelled the way a Korean
                # document spells them. Both halves of the rule had to be
                # translated together -- an English subject test would never
                # fire on a Korean sentence even once the phrase list saw it.
                for subject in ("payment", "refund", "결제", "환불")
            ), f"{document}: retired claim still stated: {sentence!r}"
