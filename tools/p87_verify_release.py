"""Verify retained P8.7 runtime evidence and document links; no network/mutations."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/ai-english/production-20261101'
DOC=ROOT/'docs/versions/V1-P8.7'
CONTRACTS=ROOT/'docs/versions/V1-P8.7/contracts'
sys.path.insert(0,str(ROOT/'tools'))
from p87_release import payload


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    import base64
    source=payload(include_known=False)
    hashes={s:{p:sha(base64.b64decode(v)) for p,v in values.items()} for s,values in source['files'].items()}
    signature=sha(json.dumps(hashes,sort_keys=True).encode())
    evidence={stage:read(REPORT/(stage+'.json')) for stage in ('audit','prepare','switch','verify','model-check','network-check','capture')}
    assert all(v['source_sha256']==signature for v in evidence.values())
    audit=evidence['audit'];live=evidence['verify'];switched=evidence['switch'];model=evidence['model-check'];network=evidence['network-check']
    assert not audit['unknown_runtime_changes'] and not audit['unknown_workspace_changes']
    assert live['containers']['db']==audit['containers']['db']
    assert all(v['health']=='healthy' for v in live['containers'].values())
    assert switched['compose_changes']==['agent.image','backend.image'] and switched['private_database_backup']
    assert live['private_configuration_unchanged'] and live['other_runtime_sources_preserved'] and live['rollback_images_available']
    assert not live['database_migrations_executed'] and not live['business_writes_performed']
    health=live['agent_health'];cap=live['backend_capabilities']
    assert health['maintenance_release']=='V1-P8.7' and health['engine']=='deepseek'
    assert health['jev_mode']==audit['jev_before']['mode'] and health['dialogue_max_model_calls'] is None
    assert health['assistant_languages']==cap['assistant_languages']==['zh-CN','en']
    assert cap['ai_adapter_release']=='V1-P8.7' and cap['maintenance_release']=='V1-P9'
    assert cap['conversation_dialogue_protocol']=='inventory-autonomous-1'
    assert all(not p.startswith('jev/') for p in evidence['prepare']['overlay_files']['agent'])
    assert len(evidence['prepare']['overlay_files']['backend'])==11
    assert model['real_deepseek'] and not model['inventory_reads'] and not model['business_writes']
    assert set(model['by_locale'])=={'zh-CN','en'} and all(v['model_calls']>=1 and v['stop_reason']=='completed' for v in model['by_locale'].values())
    assert model['deterministic_calls']==0
    assert network['tls_certificate_verified'] and network['service_link']['backend_to_ai_authenticated']
    assert network['http_probes']=={'health_with_app_key':200,'without_app_key':403,'without_bearer':401}
    apis={k:read(CONTRACTS/('production-'+k+'-openapi.json')) for k in ('ai','backend')}
    assert apis['ai']['info']['version']=='0.8.7' and apis['backend']['info']['version']=='0.9.0'
    assert apis['ai']['components']['schemas']['MemoryContext']['properties']['locale']['default']=='zh-CN'
    assert set(apis['backend']['components']['schemas']['Message']['properties']['locale']['enum'])=={'zh-CN','en'}
    contracts={'stage':'V1-P8.7','ai_version':'0.8.7','business_version':'0.9.0','source_sha256':signature,
        'source_commit':source['local_head'],'uncommitted_sources':True,'images':live['tags'],'language_protocol':'assistant-language-1',
        'protocol':'inventory-autonomous-1','files':{f'production-{k}-openapi.json':sha((CONTRACTS/f'production-{k}-openapi.json').read_bytes()) for k in apis},
        'backend_export_method':'running container app.openapi(); public docs remain disabled','app_joint_acceptance':False}
    (CONTRACTS/'production-manifest.json').write_text(json.dumps(contracts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    apk=ROOT/'frontend/app/build/outputs/apk/debug/app-debug.apk';assert apk.is_file()
    artifact={'path':apk.relative_to(ROOT).as_posix(),'bytes':apk.stat().st_size,'sha256':sha(apk.read_bytes()),
        'build_type':'debug','installed_on_device':False,'frontend_source_uploaded':False,'app_version_policy_unchanged':True}
    (REPORT/'android-artifact.json').write_text(json.dumps(artifact,indent=2)+'\n',encoding='utf-8')
    summary=REPORT/'delivery-summary.json';links=0
    for path in DOC.glob('*.md'):
        for link in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)',path.read_text(encoding='utf-8')):
            if '://' not in link:
                assert (path.parent/link).exists() or (path.parent/link).resolve()==summary.resolve(),(path.name,link)
                links+=1
    for name in ('p87_release.py','p87_release_remote.py','p87_verify_release.py'):ast.parse((ROOT/'tools'/name).read_text(encoding='utf-8'))
    tests={}
    for name in ('p87-release-tests','p87-backend-contract-tests'):
        suites=ET.parse(ROOT/'reports/ai-english'/f'{name}.xml').findall('.//testsuite')
        counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
        assert counts['errors']==counts['failures']==0;tests[name]=counts
    result={'release':'V1-P8.7','ai_version':'0.8.7','deployed':True,'source_sha256':signature,
        'images':live['tags'],'synced_runtime_files':live['source_files_verified'],'changed_files':{s:len(v) for s,v in evidence['prepare']['overlay_files'].items()},
        'all_services_healthy':True,'jev_preserved':True,'database_container_unchanged':True,'database_migrations_executed':False,
        'other_runtime_sources_preserved':True,'private_configuration_preserved':True,'real_bilingual_model_checks_passed':True,
        'tls_and_service_auth_passed':True,'rollback_images_available':True,'source_and_contracts_verified':True,
        'release_tests':tests,'android_artifact':artifact,'document_links_checked':links,'app_joint_acceptance':False,
        'git_commit_or_push_performed':False}
    summary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
