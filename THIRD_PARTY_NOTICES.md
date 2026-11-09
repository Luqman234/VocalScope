# Third-party licensing and distribution boundaries

VocalScope's original code is GPL-3.0-only, copyright 2026 Luqman234 (ownership
and licensing authority confirmed by the maintainer). Existing third-party work
is not relicensed. Dependencies are installed externally, not vendored into
VocalScope's wheel/source archive. Their own binary distributions carry separate
notices, bundled libraries and licensing obligations.

## Bundled metadata and fixtures

`src/vocalscope/resources/vocadito_index_1.0.json` is the unchanged official
mirdata 1.0.0 checksum index (MD5 ff83648dc2311c0c11fe8f304bbb62d4), not audio,
lyrics, singer metadata or F0/note annotations. Zenodo record 14024397 explicitly
licenses this specific artifact under BSD-3-Clause in Rights → License. The
record lists David Rubinstein and Rachel Bittner as creators. Its complete
original copyright notice, conditions and disclaimer are reproduced verbatim
in `LICENSES/mirdata-BSD-3-Clause.txt` and included in both distributions.
The index retains its original bytes and BSD-3-Clause licensing; no GPL
copyright header is applied to it.

Artifact and rights: https://zenodo.org/records/14024397
Source generator and loader: https://github.com/mir-dataset-loaders/mirdata/tree/1.0.0
Upstream notice: https://github.com/mir-dataset-loaders/mirdata/blob/master/LICENSE
BSD-3-Clause is GPLv3-compatible; its notice and non-endorsement conditions
remain applicable. See https://www.gnu.org/licenses/license-list.html#ModifiedBSD.

`tests/fixtures/stage1-pyin.json` contains project-generated synthetic pitch
regression measurements. Test waveforms are generated mathematically at runtime.
No human recordings, song renditions, images or fonts are bundled.

## External dependencies

Licenses below describe inspected installed distributions/upstream projects,
not a blanket relicensing of all transitive binary contents:

| Component | License / qualification |
|---|---|
| librosa | ISC |
| NumPy | BSD-3-Clause; installed wheel additionally lists 0BSD, MIT, Zlib, CC0-1.0 |
| SciPy | BSD-3-Clause; bundled numerical libraries retain their own notices |
| PyGObject, GTK4, libadwaita | LGPL-2.1-or-later |
| Matplotlib | Matplotlib license based on PSF terms; bundled assets retain notices |
| GStreamer core/base/good | LGPL-2.1-or-later; optional plugins require separate review |
| PipeWire / native integration | MIT; installed system components are not bundled |
| FluidSynth | LGPL-2.1-or-later |
| pyfluidsynth, torchcrepe, pretty_midi, mir_eval | MIT |
| Torch / torchaudio | PyTorch BSD-style and composite binary notices; current Torch metadata lists Apache-2.0, LLVM exception, BSD, BSL, ISC, MIT and Zlib components |
| soundfile | BSD-3-Clause; external libsndfile is LGPL-2.1-or-later |

Evidence comes from installed Python distribution metadata/license files, system
package copyright information and linked upstream notices. No incompatible bundled component was identified in the reviewed file set. This is not a certification
of arbitrary extra plugins, user-installed samples or every future dependency.

## Separately supplied assets

Vocadito v3: Bittner, Pasalo, Bosch, Meseguer-Brocal and Rubinstein (2021),
https://zenodo.org/records/5578807, CC BY 4.0. Obtain explicitly with the dataset
command; recordings and annotations are not redistributed here.

TimGM6mb 1.3, used for local tests, contains separately GPL-2 licensed samples
attributed to Tim Brechbill and David Bolton. It is excluded from Git and
packages; GPLv3 on VocalScope does not relicense these samples. FluidSynth's
software license is distinct. Users must supply and assess their own SoundFont.
CREPE model weights are external optional assets and are not copied into this
repository. Audio generated from songs, commercial isolated vocals and personal
recordings stays local. No permission to redistribute such media is implied.
