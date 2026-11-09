# VocalScope 0.5.1 — source publication preparation

**Status: source published to the authorized public repository after licensing,
security, packaging and regression checks passed. No tag or GitHub Release created.**

## A. Repository audit

The initial directory was not a Git repository: no branches, tags, remotes,
tracked files or reachable Git history existed. GitHub authentication succeeded
outside restricted networking and identified Luqman234. An initial lookup returned
not found; a later create attempt found an existing public initialization commit.
Its only files were a Python .gitignore and the same full GNU GPLv3 LICENSE. The maintainer explicitly confirmed
original-code licensing authority, public attribution Luqman234, and permission
to create that public destination after mandatory checks pass. Configured private
Git email was neither copied into documentation nor committed.

## B. Licensing

LICENSE contains the complete, unmodified GNU GPL version 3 text fetched from
https://www.gnu.org/licenses/gpl-3.0.txt. Original Python files now identify
GPL-3.0-only and Copyright (C) 2026 Luqman234. No third-party file was relicensed.
Pyproject uses the supported PEP 639 expression `GPL-3.0-only` and explicit
license-files with setuptools >=77. No deprecated, conflicting classifier is
added. Version remains 0.5.1. README describes rights, no warranty and asset
boundaries. GPL's example appendix does not override the explicit version-only
SPDX selection.

## C. Third-party audit and mandatory blocker

See THIRD_PARTY_NOTICES.md and LICENSES/mirdata-BSD-3-Clause.txt. External Python,
GTK, GStreamer, PipeWire and FluidSynth dependencies are not vendored. Local
SoundFonts, datasets, model weights and rendered/song audio are excluded.
TimGM6mb's GPL-2 samples are separate and are not relicensed or uploaded.

**Reassessment corrected the earlier blocker.** The specific bundled file
`src/vocalscope/resources/vocadito_index_1.0.json` is byte-for-byte equal to the
artifact downloaded from https://zenodo.org/records/14024397. MD5:
`ff83648dc2311c0c11fe8f304bbb62d4`; SHA256:
`5b296ad41ebad63d649a397e2720569b2aa271fcd38de0f887dd5147eaeff278`.
The record's **Rights → License** explicitly states BSD-3-Clause, with creators
David Rubinstein and Rachel Bittner. The full displayed notice matches the
bundled `LICENSES/mirdata-BSD-3-Clause.txt`, including its original 2016 copyright,
all three conditions, and disclaimer. It is included in both wheel and sdist.
The earlier audit checked the wrong API field and missed these explicit rights;
that conclusion was mistaken, not an absence of redistribution permission.
The original blocked report remains in private operational evidence.

The index stays BSD-3-Clause, with unchanged bytes and checksum validation.
VocalScope original source is GPL-3.0-only. Three-clause BSD is compatible with
GPLv3; notice retention and non-endorsement requirements remain applicable.
GNU guidance: https://www.gnu.org/licenses/license-list.html#ModifiedBSD.
Mirdata’s index-upload instructions also require its published index license:
https://github.com/mir-dataset-loaders/mirdata/blob/master/docs/source/contributing.rst.
No dataset audio, annotations, models or SoundFonts are bundled.

## D. Security and privacy

Gitleaks was unavailable. Alternative checks reviewed all 148 candidate files,
paths, sizes and targeted patterns for GitHub/AWS credentials, private keys,
password/token assignments, credential URLs, private home paths and email
addresses. No findings remained. This is not an exhaustive secret-scanner
certification. There was no initial local Git history. The subsequently fetched public
initialization and all new reachable history were scanned as recorded below. Before any future commit/push,
repeat scanning on the exact staged tree and every newly reachable commit.
No known credentials, recordings, dataset archives or SoundFonts are approved
for publication. Operational logs, inventory and original evidence remain local.

## E. Repository organization

Reviewed source, tests, scripts, synthetic fixture, community files, CI,
packaging and redacted historical Markdown summaries form the candidate.
Raw reports, data, results, captures, virtualenvs, caches, credentials, build
outputs and private publication notes are ignored. MANIFEST uses an explicit
public report allowlist, preventing stale egg-info file lists from bundling raw
historical reports. This was checked against actual archives. No source data
was deleted. Historical summaries explain that their raw-evidence links require
local assets; their measured values were not recast as fresh validation.

## F. Packaging

A fresh wheel and source archive built successfully in a temporary staging
location. `scripts/check_public_package.py` verified GPL-3.0-only metadata,
license inclusion, no private-home paths and no audio/model/SoundFont/raw-log
assets in either archive. Source distribution includes tests and documentation.
All packaged source is the tested code. Installed-wheel imports and nine CLI
help/version checks passed outside the checkout without a display or local media.
No package upload, PyPI release, historical dist replacement or version bump
occurred. Package structural checks do not clear the separate index license gate.

## G. Fresh validation

| Run | Passed | Failed | Errors | Skipped | Time |
|---|---:|---:|---:|---:|---:|
| Headless, optional local neural and real SoundFont enabled | 216 | 0 | 0 | 12 | 95.09 s |
| Native Wayland/PipeWire category | 12 | 0 | 0 | 0 | 75.08 s |

228 distinct tests passed across complementary runs. Headless skips passed in
the native run. Two expected mir_eval warnings and 127 upstream GI deprecation
warnings occurred. Initial optional-flag invocations omitted the explicit tests
path needed to load conftest options and exited before collection; corrected
commands above supplied `tests`. No test tolerance was relaxed.

Fresh installed wheel smoke tests completed:

- YIN analysis of a 33.212-second local Vocadito vocal.
- YIN transcription and independent pretty_midi read-back of 83 valid notes.
- Existing 65-note edited project rendered through actual FluidSynth and local
  TimGM6mb: 48 kHz stereo, 1,666,188 frames, 34.71225 seconds.
- Soundfile read-back and actual shared-clock GStreamer fakesink playback.
- No GTK or Torch import for those headless workflow operations.

These are functional checks, not new transcription-accuracy claims. Physical
listening, acoustic latency and hardware-unplug acceptance remain unverified.

## H. Git operations

Initial local audit found no repository or shared local history. The audited
142-file source tree was committed as
`cb5382a5e2a1f4cade6fa316ffb473ebeed2fd59` with the approved public name and a
GitHub noreply email. The existing public remote initialization commit
`71fb0bca38c5b86fd6bd084c9a5180b4330c74b4` was fetched, reviewed and preserved.
Its ignore rules were retained alongside the stricter VocalScope exclusions;
the LICENSE already matched the verified GNU text.

Merge commit `1221e138b5ed7110ffb0fdf18b5c8bdf386e1810` published the source via
an ordinary fast-forward push to main. No force push, history rewrite, release
or tag occurred. All 144 reachable blobs across those three commits were reviewed
with targeted credential/privacy patterns and path/size checks; no findings.
The source tree contains no media, samples, weights or dataset annotations.
This report is subsequently updated in a documentation-only commit; its own SHA
is available from GitHub history rather than a self-referential embedded hash.

## I. GitHub

Public repository: https://github.com/Luqman234/VocalScope.
Default branch: main. The source publication SHA above was independently checked
through GitHub's commit API. Source modules, tests, GPL/BSD notices and README
are present. Accurate project topics and description are configured. Actual
license detection, private security reporting and CI status are recorded in the
post-push verification section below. No release or tag is authorized.

## J. Preservation

All 1,314 historical report/data/result/distribution files inventoried before
preparation remain byte-identical. Original README was backed up locally before
public restructuring. No recordings, raw benchmark results or previous reports
were overwritten. Source changes are license headers plus documentation and
packaging preparation; no DSP/transcription/playback algorithm changed.

## K. Remaining limitations

Secret scanning used explicit patterns and full candidate review, not Gitleaks.
CI is only called passed after its actual GitHub run finishes successfully.
Physical listening, hardware unplug and acoustic latency remain outside this
publication check. Raw historical artifacts remain local; public summaries
retain the methodology and measured limitations. No accuracy claims were added.

## L. Future engineering

Stage 3.1 note-release/repetition/transition improvements and Stage 4C expressive
piano interpretation remain separate future work. Neither was implemented here.

## Post-push verification

GitHub independently returned public visibility, default branch main and source
merge SHA `1221e138b5ed7110ffb0fdf18b5c8bdf386e1810`. The recursive remote tree
contains 142 reviewed source/documentation files, none over 1 MiB, and no
recordings, SoundFonts, weights, dataset archives or raw logs. The rendered
README contains VocalScope and GPL-3.0-only. GitHub detects the full GPLv3 text
as `GPL-3.0`; the project explicitly selects **GPL-3.0-only** through SPDX notices
and packaging metadata. The index independently retains BSD-3-Clause.
Private vulnerability reporting is enabled. The tags endpoint returned zero.

The first actual CI run is
https://github.com/Luqman234/VocalScope/actions/runs/42671570179.
Its initial attempt failed before any job started. The public run page states
**Internal server error**, correlation ID
`88937457-98ed-4936-abb5-af29aa15b36b`. The jobs API returned zero jobs; this is
not a software test result. Repository Actions are enabled with all actions
allowed. One retry was requested; CI is **not claimed passed**. Consult GitHub
for the current retry/follow-up status.
Native hardware acceptance remains separate from CI and is not claimed here.
