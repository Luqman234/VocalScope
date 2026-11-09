# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Check publication archives without depending on user data or a display."""
from pathlib import Path
import email
import hashlib
import sys
import tarfile
import zipfile

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'dist')
archives = list(root.glob('*.whl')) + list(root.glob('*.tar.gz'))
assert archives, 'No built archives'
for archive in archives:
    if archive.suffix == '.whl':
        with zipfile.ZipFile(archive) as z:
            entries = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
        meta = next(v for n, v in entries.items() if n.endswith('.dist-info/METADATA'))
        parsed = email.message_from_bytes(meta)
        assert parsed['License-Expression'] == 'GPL-3.0-only'
        assert parsed['Version'] == '0.5.1'
        assert any(n.endswith('/licenses/LICENSE') for n in entries)
    else:
        with tarfile.open(archive) as t:
            entries = {m.name.split('/', 1)[-1]: t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
        assert 'LICENSE' in entries
    for n, data in entries.items():
        assert not any(p in n.split('/') for p in ['data','results','.publication-local','.venv']), n
        assert not n.endswith(('.sf2','.sf3','.wav','.flac','.ogg','.mp3','.pt','.pth','.log')), n
        assert (b'/home/' + b'Luqman') not in data, n
        if n.startswith('reports/'):
            assert n == 'reports/OPEN_SOURCE_PUBLICATION.md', n
    license_text = next(v for n, v in entries.items() if n == 'LICENSE' or n.endswith('/licenses/LICENSE'))
    assert b'GNU GENERAL PUBLIC LICENSE' in license_text and b'Version 3, 29 June 2007' in license_text
    bsd = [v for n, v in entries.items() if n.endswith('mirdata-BSD-3-Clause.txt')]
    assert bsd == [Path('LICENSES/mirdata-BSD-3-Clause.txt').read_bytes()]
    index = [v for n, v in entries.items() if n.endswith('vocadito_index_1.0.json')]
    assert len(index) == 1 and hashlib.md5(index[0]).hexdigest() == 'ff83648dc2311c0c11fe8f304bbb62d4'
    print(archive.name, 'verified:', len(entries), 'files')
