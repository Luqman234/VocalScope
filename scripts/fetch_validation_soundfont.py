# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Explicit validation-asset fetch; never invoked by VocalScope or pytest.

TimGM6mb 1.3: GPL-2 sound samples, separate from FluidSynth's LGPL license.
Source/checksum: Debian signed .dsc, downloaded over HTTPS; no claim that the
uploader's OpenPGP signature has been independently verified here.
"""
from pathlib import Path
import hashlib,io,json,tarfile,urllib.request

ROOT=Path('data/soundfonts');ROOT.mkdir(parents=True,exist_ok=True)
URL='https://deb.debian.org/debian/pool/main/t/timgm6mb-soundfont/timgm6mb-soundfont_1.3.orig.tar.gz'
SHA='af8f3a00e416dfb262bcaa904a1c84df04a51b72bbc1313aed012bc754bdf99b'
COPYRIGHT='https://metadata.ftp-master.debian.org/changelogs/main/t/timgm6mb-soundfont/timgm6mb-soundfont_1.3-5_copyright'
license_text=urllib.request.urlopen(COPYRIGHT,timeout=30).read()
if b'Files: TimGM6mb.sf2' not in license_text or b'License: GPL-2' not in license_text:raise RuntimeError('Unexpected license; inspect before downloading samples.')
archive=urllib.request.urlopen(URL,timeout=60).read(6_000_000)
if len(archive)!=5_560_953 or hashlib.sha256(archive).hexdigest()!=SHA:raise RuntimeError('Source archive size/checksum mismatch.')
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
 members=[m for m in tar.getmembers() if Path(m.name).name=='TimGM6mb.sf2' and m.isfile()]
 if len(members)!=1 or members[0].size>10_000_000:raise RuntimeError('Unexpected SoundFont archive.')
 data=tar.extractfile(members[0]).read()
path=ROOT/'TimGM6mb.sf2'
if path.exists() and path.read_bytes()!=data:raise FileExistsError('Existing font differs; refusing to overwrite.')
path.write_bytes(data);(ROOT/'TimGM6mb.COPYRIGHT').write_bytes(license_text)
manifest={'name':'TimGM6mb','version':'1.3','source_url':URL,'archive_sha256':SHA,'copyright_url':COPYRIGHT,'license':'GPL-2','copyright':'2004 Tim Brechbill; 2010 David Bolton','soundfont_path':str(path),'soundfont_bytes':len(data),'soundfont_sha256':hashlib.sha256(data).hexdigest(),'redistributed_with_vocalscope':False}
Path('reports/stage4a/soundfont-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
