# Internal development record

Everything under `docs/internal/` is development history, not user
documentation. It is kept — not deleted — because a substantial part of this
repository's value is the record of how each claim was checked, not just the
claim itself. Nothing here is required to install or use the package.

If you are looking for how to use `srt_mobile_api`, start at the repository
[`README.md`](../../README.md). If you are looking for the current evidence
behind a specific behaviour, start at [`docs/VERIFICATION.md`](../VERIFICATION.md)
or [`docs/IMPLEMENTATION_PROGRESS.md`](../IMPLEMENTATION_PROGRESS.md) — both
live outside this directory because they describe the package as it is now.

What is filed here, and why it stopped being current:

| Path | What it is |
| --- | --- |
| [`RELEASE_GAP_PLAN.md`](RELEASE_GAP_PLAN.md) | A dated planning document written while deciding how to close the gap to a mutation-capable client. Superseded by the mutation surface it planned, which now exists and is recorded in `CHANGELOG.md` and `docs/IMPLEMENTATION_PROGRESS.md`. States its own starting version (`0.2.0`) and status (`3 - Alpha`) as they stood on the day it was written; those are historical facts about that day, not claims about the package today. |
| [`analysis/impl-audit-2026-07-22.md`](analysis/impl-audit-2026-07-22.md) and its four `-reverify*` follow-ups | A dated implementation audit and its re-verification passes from 2026-07-22. Findings that survived are folded into the current implementation; this is the trail of how they were checked. |
| [`audit-2026-07-27/`](audit-2026-07-27/) | The three-phase, multi-agent 2026-07-27 audit (8 first-pass reviewers, 4 cross-check reviewers, 4 falsification-attempt verifiers) that produced the fixes recorded under `## 1.0.0` in `CHANGELOG.md`. Kept as the full record of what was checked and how, including the findings that were rejected on verification. |
| [`superpowers/specs/`](superpowers/specs/) | The approved design specifications written before each feature was implemented. Kept as the record of the reasoning behind a design, distinct from `docs/IMPLEMENTATION_PROGRESS.md`, which records what was actually built. |

None of these documents are updated to stay current — that is what makes them
a record rather than documentation. If a fact here conflicts with the current
package behaviour, the package is correct and the document is a dated snapshot
of what was true, or believed true, on the date in its own heading.
