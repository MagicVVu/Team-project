"""Reproducible orchestration; all child tests use offline_exec.py."""
import datetime, json, pathlib, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
SUITE = ROOT / 'test_package' / 'Agent_Regression_v1'
EVIDENCE = ROOT / 'runs' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
EVIDENCE.mkdir(parents=True, exist_ok=False)
manifest=json.loads((ROOT/'source_manifest.json').read_text(encoding='utf-8'))
VERSION=manifest['commit'][:12]
shutil.copy2(ROOT/'source_manifest.json', EVIDENCE/'source_manifest.json')
PROJECT = ROOT / 'source_snapshot' / 'agent'
commands = []
def execute(label, args, cwd=ROOT):
    cmd = [sys.executable, str(ROOT / 'offline_exec.py'), *args]
    with (EVIDENCE / (label + '.log')).open('w', encoding='utf-8') as log:
        completed = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, encoding='utf-8')
    commands.append({'label': label, 'command': cmd, 'cwd': str(cwd), 'exit_code': completed.returncode})
    (EVIDENCE / 'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2), encoding='utf-8')
    print(label, 'exit=', completed.returncode, flush=True)
execute('source-tests',['pytest',str(PROJECT/'tests'),str(ROOT/'source_snapshot'/'backend'/'tests'),'-q','-p','no:cacheprovider','--basetemp='+str(EVIDENCE/'pytest-temp'),'--junitxml='+str(EVIDENCE/'source-tests.xml')])
for name, adapter in [('p0-regression','adapters.local_p0'), ('p1-regression','adapters.local_p1'), ('android-regression','adapters.android_gateway')]:
    execute(name, ['script', str(SUITE/'run.py'), '--project', str(PROJECT), '--adapter', adapter, '--version', VERSION+'-'+name+'-rules', '--out', str(EVIDENCE/name)], cwd=SUITE)
for split in ('dev','test'):
    execute('p1-native-'+split, ['module','eval.p1.run','--engine','rules','--split',split])
execute('scorer-tests', ['pytest',str(SUITE/'tests'), '-q','-p','no:cacheprovider','--basetemp='+str(EVIDENCE/'scorer-temp'),'--junitxml='+str(EVIDENCE/'scorer-tests.xml')])
execute('future-coverage', ['script',str(SUITE/'run.py'),'--project',str(PROJECT),'--version',VERSION+'-future-driver-coverage','--cases','cases/future_scenarios.jsonl','--out',str(EVIDENCE/'future-coverage')], cwd=SUITE)
# Keep review gates unchanged and outside the required denominator.
review = [json.loads(line) for name in ('baseline_150.jsonl','extended.jsonl') for line in (SUITE/'cases'/name).read_text(encoding='utf-8').splitlines() if json.loads(line)['gate']=='review']
(EVIDENCE/'review_cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in review),encoding='utf-8')
for name, adapter in [('p0','adapters.local_p0'), ('p1','adapters.local_p1'), ('android','adapters.android_gateway')]:
    label=name+'-review-observations'
    execute(label, ['script',str(SUITE/'run.py'),'--project',str(PROJECT),'--adapter',adapter,'--version',VERSION+'-'+label,'--cases',str(EVIDENCE/'review_cases.jsonl'),'--include-review','--out',str(EVIDENCE/label)],cwd=SUITE)
native=EVIDENCE/'p1-native-results'
native.mkdir()
for path in (PROJECT/'eval'/'p1'/'results').glob('*.json'):
    shutil.copy2(path,native/path.name)
# A wrapper finishing successfully must not turn red regressions into success.
invalid=any(row['exit_code'] not in {0,1} for row in commands)
required_red=any(json.loads((EVIDENCE/name/'summary.json').read_text(encoding='utf-8'))['required_pass'] is False for name in ('p0-regression','p1-regression','android-regression','future-coverage') if (EVIDENCE/name/'summary.json').exists())
unit_red=any(row['exit_code']!=0 for row in commands if row['label'] in {'source-tests','scorer-tests'})
native_red=False
native_reports=list(native.glob('*.json'))
for path in native_reports:
    report=json.loads(path.read_text(encoding='utf-8'))
    expected_count=90 if report['metadata']['split']=='dev' else 60
    native_red |= report['metadata']['attempted_count']!=expected_count or report['metrics']['all_checks_accuracy']!=1 or report['metrics']['inventory_mutations']!=0
native_red |= len(native_reports)!=2
print('Evidence:',EVIDENCE,flush=True)
raise SystemExit(2 if invalid else 1 if required_red or unit_red or native_red else 0)
