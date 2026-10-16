"""Execute each suite in a fresh worker, retaining failing exit codes."""
import argparse, datetime, json, pathlib, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser();p.add_argument('--ai-python',required=True);p.add_argument('--backend-python',required=True);p.add_argument('--set',choices=['all','ai','backend','supplemental'],default='all');a=p.parse_args()
    evidence=ROOT/'evidence';commands=[]
    def run(label,python,args):
        out=evidence/label;start=datetime.datetime.now(datetime.timezone.utc).isoformat()
        if out.exists() or (evidence/(label+'.log')).exists():raise FileExistsError('Existing evidence is immutable; capture a fresh round before rerunning: '+label)
        command=[python,str(ROOT/'worker.py'),*args,'--out',str(out)]
        with (evidence/(label+'.log')).open('w',encoding='utf-8') as log:done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,encoding='utf-8')
        row={'label':label,'command':command,'started_at':start,'exit_code':done.returncode,'evidence':label}
        commands.append(row);(evidence/f'commands-{a.set}.json').write_text(json.dumps(commands,ensure_ascii=False,indent=2),encoding='utf-8');print(label,'exit=',done.returncode,flush=True)
    if a.set in {'all','ai'}:
        run('ai-source',a.ai_python,['ai']);run('p4-history',a.ai_python,['legacy'])
        for phase in ('p1','p2','p3','p5'):
            for split in ('dev','test'):run(phase+'-'+split,a.ai_python,['native','--phase',phase,'--split',split])
    if a.set in {'all','backend'}:
        run('backend-local',a.backend_python,['backend']);run('backend-reference-flow',a.backend_python,['backend-special'])
    if a.set in {'all','supplemental'}:run('garin-special',a.ai_python,['supplemental'])
    return 1 if any(r['exit_code'] for r in commands) else 0
if __name__=='__main__':raise SystemExit(main())
