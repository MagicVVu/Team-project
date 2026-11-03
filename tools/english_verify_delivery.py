"""Local delivery checks only. No deployment, provider calls or git mutations."""
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/ai-english'
DOC=ROOT/'docs/versions/V1-P8.7'
sys.path.insert(0,str(ROOT/'agent'))


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def tests(path):
    root=ET.parse(path)
    suites=root.findall('.//testsuite')
    result={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    result['passed']=result['tests']-result['failures']-result['errors']-result['skipped']
    return result


def main():
    from integration.source_manifest import manifest
    assert read(DOC/'runtime-source-manifest.json')==manifest()
    exported=read(DOC/'contracts/manifest.json')
    for name,digest in exported['files'].items():
        path=DOC/'contracts'/name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
        value=read(path)
        def refs(node):
            if isinstance(node,list):
                for v in node:refs(v)
            elif isinstance(node,dict):
                if '$ref' in node:
                    ref=node['$ref'];assert ref.startswith('#/'),ref
                    target=value
                    for key in ref[2:].split('/'):target=target[key.replace('~1','/').replace('~0','~')]
                for v in node.values():refs(v)
        refs(value)
    public=read(DOC/'contracts/public-message.schema.json')
    assert public['properties']['locale']['default']=='zh-CN' and 'locale' not in public['required']
    assert set(public['properties']['locale']['enum'])=={'zh-CN','en'}
    lexicon=ROOT/'agent/conversation/language/lexicon.json'
    assert lexicon.read_bytes()==(ROOT/'backend/server/app/data/assistant_lexicon.json').read_bytes()
    from p0.language import UNITS
    aliases=(ROOT/'frontend/app/src/main/java/com/example/teamapp/data/AssistantUnitAliases.kt').read_text(encoding='utf-8')
    assert dict(re.findall(r'"([^"]+)" to "([^"]+)"',aliases))==UNITS
    dataset=read(REPORT/'cases.json')
    assert len(dataset)==150 and len({r['id'] for r in dataset})==150
    assert sum(r['split']=='dev' for r in dataset)==90 and sum(r['split']=='holdout' for r in dataset)==60
    groups={s:{r['group'] for r in dataset if r['split']==s} for s in ('dev','holdout')}
    assert not groups['dev']&groups['holdout']
    assert all(r['source'] and r['human_review_status']=='pending' and r['zh-CN'] and r['en'] for r in dataset)
    ai=tests(REPORT/'ai-tests-final.xml');backend=tests(REPORT/'backend-tests-final.xml')
    for value in (ai,backend):assert value['failures']==value['errors']==0,value
    android=read(REPORT/'android-tests.json')
    assert android['android_compile'] and not android['failed'] and android['passed']>=77
    audit=read(REPORT/'real-corrected-regression-audit.json')
    raw=[json.loads(line) for line in (REPORT/'real-corrected-regression.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(raw)==len({(r['id'],r['locale']) for r in raw})==300
    targeted=read(REPORT/'real-selection-final-audit.json')
    targeted_rows=[json.loads(line) for line in (REPORT/'real-selection-final.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(targeted_rows)==10 and all(r['passed'] for r in targeted_rows)
    covered={(r['id'],r['locale']) for r in targeted_rows if r['passed']}
    for locale,metrics in audit['by_locale'].items():
        assert not metrics['unlocalized_system_reply_cases']
        assert all((v['id'],locale) in covered and v['id'].startswith('multiple_items-') for v in metrics['semantic_fact_violations']), 'Unresolved historical violation'
    assert all(not v['semantic_fact_violations'] and not v['unlocalized_system_reply_cases'] for v in targeted['by_locale'].values())
    changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True,encoding='utf-8').splitlines()
    protected=['backend/server/app/models.py','backend/server/app/execution_models.py','backend/server/app/services/draft_execution.py',
        'backend/server/app/services/inventory_cleanup.py','backend/server/app/services/physical_inventory.py']
    assert not set(protected)&set(changed)
    assert not any(p.startswith(('backend/server/alembic/','agent/jev/')) for p in changed)
    assert subprocess.check_output(['git','rev-parse','--short=7','HEAD'],cwd=ROOT,text=True).strip()=='8f44a6a'
    output=REPORT/'delivery-verification.json'
    for path in DOC.glob('*.md'):
        for link in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)',path.read_text(encoding='utf-8')):
            if '://' not in link:assert (path.parent/link).exists() or (path.parent/link).resolve()==output.resolve(),(path.name,link)
    publication=REPORT/'production-20261101/delivery-summary.json'
    published=read(publication) if publication.exists() else None
    result={'feature':'bilingual-assistant','release':'V1-P8.7','new_version_assigned':True,'baseline':'8f44a6a','verification_scope':'local_evidence',
        'contracts':len(exported['files']),'runtime_files':len(manifest()['files']),'bilingual_pairs':150,'dev':90,'holdout':60,
        'ai_tests':ai,'current_backend_tests':backend,'legacy_backend_tests':tests(REPORT/'backend-legacy-memory-execution.xml'),
        'android':android,'real_model_regression':audit,'final_selection_model_check':targeted,
        'historical_selection_violation_fixed_and_retested':True,'business_core_and_migrations_unchanged':True,
        'acceptance_targets_met_in_nonblind_regression':all(m['outcome_rate']>=.9 and m['clarification_recall']>=.95 and m['p95_ms']<=60000 for m in audit['by_locale'].values()),
        'manual_review':'pending','real_device_acceptance':'not_run',
        'server_deployment':'completed' if published and published.get('deployed') else 'not_run',
        'production_evidence':'production-20261101/delivery-summary.json' if published else None,'git_commit_or_push':'not_run'}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'real_model_regression','android','final_selection_model_check'}},ensure_ascii=True))


if __name__=='__main__':main()
