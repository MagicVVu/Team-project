"""Upload only release source, or execute a phase; never download private backups."""
import argparse
import base64
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/srv/magicvvu/releases/backend-p9-20261026'
parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=['upload','inspect','build','rehearse','deploy','verify','acceptance'])
args=parser.parse_args()
if args.phase=='upload':
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).strip()+b'\n'
        info=tarfile.TarInfo('source-revision.txt');info.size=len(revision);info.mode=0o600
        archive.addfile(info,io.BytesIO(revision))
        paths=list((ROOT/'backend/server/app').rglob('*.py'))+list((ROOT/'backend/server/alembic').rglob('*.py'))
        paths += [ROOT/'backend/server/alembic.ini']
        for path in paths:
            archive.add(path,arcname='source/'+path.relative_to(ROOT).as_posix(),recursive=False)
        archive.add(ROOT/'tools/p9_release_remote.py',arcname='release.py')
        if (ROOT/'tools/p9_production_acceptance.py').exists():
            archive.add(ROOT/'tools/p9_production_acceptance.py',arcname='acceptance.py')
    payload=base64.b64encode(stream.getvalue()).decode('ascii')
    code="import pathlib,os,tarfile,io,base64\np=pathlib.Path('"+REMOTE+"');p.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(p,0o700);os.umask(0o077)\nwith tarfile.open(fileobj=io.BytesIO(base64.b64decode('"+payload+"')),mode='r:gz') as t:t.extractall(p,filter='data')\nprint('Release source uploaded; no private configuration copied from client')"
    process=subprocess.run(['ssh','magicvvu','sudo -n python3 -'],input=code,text=True,capture_output=True,encoding='utf-8',timeout=60)
else:
    process=subprocess.run(['ssh','magicvvu','sudo -n python3 '+REMOTE+'/release.py '+args.phase],
                           text=True,capture_output=True,encoding='utf-8',timeout=600)
if process.returncode:
    print(process.stderr[-1800:])
    raise SystemExit(process.returncode)
if args.phase=='upload':
    print(process.stdout.strip())
else:
    result=json.loads(process.stdout)
    output=ROOT/'reports/backend-ai-p9'/('production-release-'+args.phase+'.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'phase':args.phase,'saved':str(output),'passed':result.get('passed',True)},ensure_ascii=False))
