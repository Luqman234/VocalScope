# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Run with PYTHONPATH pointing to a fresh installed wheel outside the checkout."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    for name in ['target','wheel','output','vocal','project','soundfont','report']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    import vocalscope
    assert args.target.resolve() in Path(vocalscope.__file__).resolve().parents
    from vocalscope.cli import main as cli
    source=args.vocal.resolve();project=args.project.resolve();font=args.soundfont.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    assert cli(['analyze',str(source),'--estimator','yin','--output',str(args.output/'analysis')])==0
    assert cli(['render-piano',str(project),'--soundfont',str(font),'--normalize-peak','--sample-rate','48000','--formats','wav','--output',str(args.output/'piano')])==0
    assert cli(['playback-test','--vocal',str(source),'--piano',str(args.output/'piano/piano.wav'),'--sink','fakesink','--seconds','.2','--output',str(args.output/'playback.json')])==0
    from vocalscope.synthesis.project import read_project_snapshot
    import soundfile as sf
    audio=sf.info(args.output/'piano/piano.wav')
    report={'version':vocalscope.__version__,'module_path':vocalscope.__file__,'wheel_sha256':hashlib.sha256(args.wheel.read_bytes()).hexdigest(),'wheel_files':zipfile.ZipFile(args.wheel).namelist(),'notes':len(read_project_snapshot(project)['notes']),
     'piano':{'sample_rate':audio.samplerate,'channels':audio.channels,'frames':audio.frames},'playback':json.loads((args.output/'playback.json').read_text()),'gtk_imported':any(n.startswith('gi.repository.Gtk') for n in sys.modules),'torch_imported':any(n.startswith('torch') for n in sys.modules)}
    assert not report['gtk_imported'] and not report['torch_imported']
    args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
