"""Local-only P8.6 filing, evidence preservation and contract checks."""
import ast
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator
from runtime_adaptation_verify import references

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/versions/V1-P8.6'
REPORT=ROOT/'reports/p86-autonomous/organization-20261030'
sys.path.insert(0,str(ROOT/'agent'))


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def main():
    from integration.source_manifest import manifest
    relocation=load(REPORT/'relocation.json')
    raw=0
    for item in relocation['files']:
        target=ROOT/item['to']
        assert target.is_file(),item['to']
        if item['from'].startswith('reports/'):
            assert sha(target.read_bytes())==item['sha256_before'],item['to']
            raw+=1
    assert sha(git('ls-files','--stage','-z'))==relocation['git_index_sha256'],'Existing staged content changed'
    assert not (ROOT/'docs/ai-autonomous/contracts').exists(),'Duplicated canonical contracts'
    assert not (ROOT/'reports/ai-autonomous').exists() and not (ROOT/'reports/runtime-adaptation-20261030').exists()
    source=manifest()['files']
    assert load(DOCS/'runtime-source-manifest.json')['files']==source
    for relative in source:
        if relative.endswith('.py'):ast.parse((ROOT/'agent'/relative).read_text(encoding='utf-8-sig'))
    contracts=load(DOCS/'contracts/manifest.json')
    assert contracts['stage']=='V1-P8.6' and contracts['ai_version']=='0.8.6'
    assert contracts['protocol']=='inventory-autonomous-1' and contracts['deployment']=='local_only'
    for name,digest in contracts['files'].items():
        path=DOCS/'contracts'/name
        assert sha(path.read_bytes())==digest,name
        document=load(path)
        if name.endswith('.schema.json'):Draft202012Validator.check_schema(document)
        references(document,document)
    ai=load(DOCS/'contracts/ai-openapi.json')
    backend=load(DOCS/'contracts/backend-openapi.json')
    assert ai['info']['version']=='0.8.6' and 'V1-P8.6' in ai['info']['title']
    assert '/agent/dialogue/run' in ai['paths'] and backend['info']['version']=='0.9.0'
    pages=[*DOCS.glob('*.md'),*(ROOT/'docs/ai-autonomous').glob('*.md'),
        ROOT/'docs/versions/README.md',ROOT/'agent/README.md',ROOT/'reports/p86-autonomous/README.md',
        ROOT/'docs/handoffs/前端AI助手接入任务清单-单窗口版.md',
        ROOT/'docs/handoffs/V1-P8.3-P8.5-前后端统一对接方案.md']
    links=0
    for page in pages:
        for value in re.findall(r'\]\(([^)]+)\)',page.read_text(encoding='utf-8')):
            if value.startswith(('https:','http:','mailto:','#')):continue
            target=(page.parent/value.split('#')[0]).resolve()
            assert target.exists() or target==REPORT/'delivery-summary.json',(page.name,value)
            links+=1
    tests={}
    for name in ('ai-tests.xml','backend-tests.xml'):
        suites=ET.parse(REPORT/name).getroot().findall('testsuite')
        values={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
        assert values['failures']==values['errors']==0,(name,values)
        values['passed']=values['tests']-values['skipped'];tests[name]=values
    protected=['frontend','backend/server/alembic','backend/server/app/models.py',
        'backend/server/app/execution_models.py','backend/server/app/services/draft_execution.py',
        'backend/server/app/services/physical_inventory.py']
    assert not git('diff','HEAD','--name-only','--',*protected).strip()
    assert not git('diff','--name-only','--diff-filter=U').strip()
    git('diff','HEAD','--check')
    for path in [*(ROOT/'tools').glob('autonomous*.py'),*(ROOT/'tools').glob('runtime_adaptation*.py'),
            *(ROOT/'tools').glob('p86*.py')]:
        ast.parse(path.read_text(encoding='utf-8-sig'))
    # Older P8.5 release material stays byte-identical to the original backup.
    cache=ROOT/'.cache/runtime-adaptation-20261030'
    before=load(cache/'before.json')
    for relative in before['preserved_files']:
        if relative.startswith(('docs/versions/V1-P8.5/','reports/p85-memory/','tools/p85_release')):
            assert (ROOT/relative).read_bytes()==(cache/'before-worktree'/relative).read_bytes(),relative
    value={'stage':'V1-P8.6','ai_version':'0.8.6','protocol':'inventory-autonomous-1',
        'runtime_files':len(source),'contract_files':len(contracts['files']),'moved_files':len(relocation['files']),
        'raw_report_files_preserved':raw,'document_links_checked':links,'tests':tests,
        'backend_test_scope':'autonomous adapter, protocol recovery, current physical fixtures and relocated contract check',
        'git_index_changed':False,'teammate_frontend_or_core_modified':False,'new_model_calls':0,
        'server_accessed_this_organization':False,'deployed':False,'committed':False,'pushed':False,
        'app_joint_acceptance':False}
    (REPORT/'delivery-summary.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
