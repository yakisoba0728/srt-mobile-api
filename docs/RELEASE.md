# Release Gate

This is the build and verification workflow this repository runs before every
release. It does not by itself authorize a production-service request — that
authorization is a separate, explicit decision recorded below — and it never
runs a live test: "verification" here means the offline suite plus a clean
package build, never a request to `app.srail.or.kr`.

## Preconditions

- Start from a clean tracked worktree.
- Use Python 3.11 or newer and install the test and build tools locally.
- Live tests are forbidden during this release gate. Do not load credentials,
  local live configuration, cookies, tokens, or production response data.

## Test, build, and verify

Run from the repository root:

```bash
set -euo pipefail

artifact_dir=""
venv_dir=""
outside_dir=""
checkout="$PWD"

cleanup() {
  cd "$checkout" 2>/dev/null || true
  if [[ -n "$artifact_dir" ]]; then rm -rf "$artifact_dir"; fi
  if [[ -n "$venv_dir" ]]; then rm -rf "$venv_dir"; fi
  if [[ -n "$outside_dir" ]]; then rm -rf "$outside_dir"; fi
  rm -rf "$checkout/build" "$checkout/dist"
  find "$checkout" -type d -name '*.egg-info' -prune -exec rm -rf {} +
}
trap cleanup EXIT

python3 -m pip install -e ".[test]"
python3 -m pip install build
PYTHONPATH="$PWD/src" pytest -q -m "not live"

artifact_dir="$(mktemp -d)"
venv_dir="$(mktemp -d)"
outside_dir="$(mktemp -d)"
python3 -m build --wheel --sdist --outdir "$artifact_dir" .
wheel_path="$(find "$artifact_dir" -maxdepth 1 -name '*.whl' -print -quit)"
sdist_path="$(find "$artifact_dir" -maxdepth 1 -name '*.tar.gz' -print -quit)"
python3 scripts/verify_distribution.py "$wheel_path" "$sdist_path"
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install "$wheel_path"

checkout="$PWD"
cd "$outside_dir"
unset PYTHONPATH
"$venv_dir/bin/python" - <<PY
from pathlib import Path
import srt_mobile_api
from srt_mobile_api import SrtClient

package_path = Path(srt_mobile_api.__file__).resolve()
assert "site-packages" in package_path.parts
assert Path("$checkout").resolve() not in package_path.parents
print(SrtClient.__name__, package_path)
PY
cd "$checkout"
cleanup
trap - EXIT
```

The verifier must receive exactly one wheel and one source distribution. The
fresh import must resolve from `site-packages`, outside the checkout.

## Cleanup

The `EXIT` trap removes temporary directories and local build metadata on both
success and failure. The explicit final cleanup disarms that trap only after all
checks pass.

Finish with `git status --short` and `git diff --check`.

## Version policy

From `1.0.0`, this project follows semantic versioning: patch for compatible
fixes, minor for backward-compatible additions to the public API, major for a
breaking change to it.

That promise is about **this library's Python API only** —
`srt_mobile_api.__all__`, the shape of the objects it returns, the exceptions
it raises. It is not, and cannot be, a promise about SRT (에스알) itself. The
mobile app's routes, field names, response shapes and business rules can
change without notice on their side, since SR offers no documented API and
owes this project no compatibility. A patch release here can be forced by a
change on their end that this project had no part in and did not choose.

## Public-release blockers

Every public release was blocked until four items existed and were reviewed: a
license, owner metadata, a canonical URL, and explicit authorization. All four
are satisfied as of 2026-07-27:

- **License.** `LICENSE` carries the verbatim Apache-2.0 text, and
  `pyproject.toml` states `license = "Apache-2.0"` / `license-files =
  ["LICENSE"]` in PEP 639 SPDX form.
- **Owner metadata.** `pyproject.toml`'s `authors` names the repository owner
  (`yakisoba0728`) and a contact address.
- **Canonical URL.** `pyproject.toml`'s `[project.urls]` states the GitHub
  Homepage, Repository, Issues and Changelog URLs under
  `github.com/yakisoba0728/srt-mobile-api`.
- **Explicit authorization.** The repository owner explicitly authorized a
  public release of this repository under Apache-2.0 on GitHub on 2026-07-27.

`scripts/verify_distribution.py` enforces the first three of these as part of
this gate: it checks the built wheel and sdist against the exact license,
author and URL values in `pyproject.toml`, so a distribution that drifts from
them fails the gate rather than shipping quietly.
