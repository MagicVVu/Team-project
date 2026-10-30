"""Validate Oct 30 current-contract evidence without rewriting historical reports."""
import ast
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/versions/V1-P8.6'
REPORT=ROOT/'reports/p86-autonomous/adaptation-20261030'
CACHE=ROOT/'.cache/runtime-adaptation-20261030'
sys.path.insert(0,str(ROOT/'agent'))


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode('utf-8')


def references(value,document):
    if isinstance(value,dict):
        if '$ref' in value:
            assert value['$ref'].startswith('#/'),value['$ref']
            target=document
            for part in value['$ref'][2:].split('/'):target=target[part.replace('~1','/').replace('~0','~')]
        for child in value.values():references(child,document)
    elif isinstance(value,list):
        for child in value:references(child,document)


def main():
    from integration.source_manifest import manifest
    source=manifest()['files']
    assert source==load(DOCS/'runtime-source-manifest.json')['files']
    for relative in source:
        if relative.endswith('.py'):ast.parse((ROOT/'agent'/relative).read_text(encoding='utf-8-sig'))
    contracts=load(DOCS/'contracts/manifest.json')['files']
    for name,digest in contracts.items():
        path=DOCS/'contracts'/name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
        data=load(path)
        if name.endswith('.schema.json'):Draft202012Validator.check_schema(data)
        references(data,data)
    links=0
    pages=[*DOCS.glob('*.md'),ROOT/'docs/handoffs/前端AI助手接入任务清单-单窗口版.md',
        ROOT/'docs/handoffs/V1-P8.3-P8.5-前后端统一对接方案.md']
    for page in pages:
        for link in re.findall(r'\]\(([^)]+)\)',page.read_text(encoding='utf-8')):
            if link.startswith(('http:','https:','#')):continue
            target=(page.parent/link.split('#')[0]).resolve()
            assert target.exists() or target==(REPORT/'delivery-summary.json').resolve(),(page.name,link)
            links+=1
    tests={}
    for name in ('ai-tests.xml','backend-tests.xml'):
        suites=ET.parse(REPORT/name).getroot().findall('testsuite')
        result={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
        assert result['failures']==result['errors']==0,(name,result)
        result['passed']=result['tests']-result['skipped']
        result['skipped_cases']=[{'name':t.attrib.get('name'),'reason':t.find('skipped').attrib.get('message')}
            for s in suites for t in s.findall('testcase') if t.find('skipped') is not None]
        tests[name]=result
    # Compare with the newly aligned teammate baseline, including staged edits.
    protected=['frontend','backend/server/alembic','backend/server/app/models.py',
        'backend/server/app/execution_models.py','backend/server/app/inventory_schemas.py',
        'backend/server/app/services/draft_execution.py','backend/server/app/services/physical_inventory.py',
        'backend/server/app/routers/inventory.py','backend/server/app/services/planning_facts.py']
    assert not git('diff','HEAD','--name-only','--',*protected).strip(),'Teammate-owned core files changed'
    assert not git('diff','--name-only','--diff-filter=U').strip(),'Unresolved index conflicts'
    git('diff','HEAD','--check')
    before=load(CACHE/'before.json')
    assert git('rev-parse','HEAD').strip()==before['origin_dev']==git('rev-parse','origin/dev').strip()
    preserved=[]
    from p86_organize_files import relocate
    for relative in before['preserved_files']:
        current=relocate(ROOT/relative)
        assert current.is_file(),relative
        if relative.startswith(('docs/versions/V1-P8.5/','reports/','tools/p85_release')):
            assert current.read_bytes()==(CACHE/'before-worktree'/relative).read_bytes(),relative
            preserved.append(relative)
    for relative in git('diff','HEAD','--name-only','--diff-filter=ACM','-z').split('\0'):
        if relative.endswith('.py'):ast.parse((ROOT/relative).read_text(encoding='utf-8-sig'))
    for relative in ('agent/conversation/autonomous/physical.py','backend/server/tests/autonomous_fixtures.py',
                     'backend/server/tests/test_autonomous_adaptation.py','tools/runtime_adaptation_audit.py',
                     'tools/runtime_adaptation_model_check.py', 'tools/runtime_adaptation_verify.py'):
        ast.parse((ROOT/relative).read_text(encoding='utf-8-sig'))
    audit=load(REPORT/'server-audit.json')
    assert all(row.get('remote_missing') or row.get('origin/dev_matches') for row in audit['source_comparison'])
    postcheck=load(REPORT/'server-postcheck.json')
    assert postcheck['same_container_identity'] and all(v['health']=='healthy' for v in postcheck['containers'].values())
    first=load(REPORT/'current-model-summary.json')
    regression=load(REPORT/'current-model-after-repair-summary.json')
    assert first['cases']==regression['cases']==16 and first['passed']==14 and regression['passed']==16
    assert regression['human_review']=='pending' and regression['independent_blind_eval'] is False
    assert all(not v['production_inventory_accessed'] and not v['server_modified'] for v in (first,regression))
    value={'date':'2026-10-30','baseline':git('rev-parse','HEAD').strip(),'inventory_model':'single-object-1',
        'runtime_files':len(source),'contract_files':len(contracts),'document_links_checked':links,'tests':tests,
        'backend_scope':'current-contract selected regressions; historical quantity fixtures not fully migrated',
        'real_first':first,'real_regression':regression,'protected_historical_files_preserved':preserved,
        'unresolved_conflicts':0,'teammate_core_or_frontend_changed':False,'new_git_commit':False,'git_push':False,
        'deployed':False,'server_runtime_unchanged':True,'postgres_verified_this_round':False,'app_joint_acceptance':False}
    (REPORT/'delivery-summary.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in value.items() if k not in {'tests','protected_historical_files_preserved','real_first','real_regression'}},ensure_ascii=False))
    print(json.dumps({'tests':{k:{n:v[n] for n in ('passed','skipped','failures','errors')} for k,v in tests.items()},
        'historical_files_preserved':len(preserved)},ensure_ascii=False))


if __name__=='__main__':main()
