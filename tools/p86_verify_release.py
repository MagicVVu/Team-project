"""Validate locally retained P8.6 deployment evidence and document links."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/p86-autonomous/production-20261030'
DOCS=ROOT/'docs/versions/V1-P8.6'
sys.path.insert(0,str(ROOT/'agent'))


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    from integration.source_manifest import manifest
    from p86_release import BACKEND
    evidence={name:load(REPORT/(name+'.json')) for name in ('audit','prepare','switch','verify','model-check','network-check','capture')}
    original=evidence['audit'];live=evidence['verify']
    source={'agent':manifest()['files'],'backend':{p:sha((ROOT/'backend/server'/p).read_bytes()) for p in BACKEND}}
    signature=sha(json.dumps(source,sort_keys=True).encode())
    assert all(v['source_sha256']==signature for v in evidence.values())
    assert live['containers']['db']==original['containers']['db']
    assert live['database_schema']==['20261029_0012']
    assert live['private_configuration_unchanged'] and live['other_runtime_sources_preserved'] and live['rollback_images_available']
    assert not live['database_migrations_executed'] and not live['business_writes_performed']
    assert live['agent_health']['maintenance_release']=='V1-P8.6'
    assert live['agent_health']['dialogue_max_model_calls'] is None
    assert live['backend_capabilities']['conversation_dialogue_protocol']=='inventory-autonomous-1'
    assert set(evidence['prepare']['overlay_files']['backend'])==set(BACKEND)
    for group in evidence['prepare']['candidate_checks'].values():
        assert all(value is True for key,value in group.items() if key in ('imports','new_route','internal_auth','legacy_factory','deterministic_run','public_auth','capabilities','calls_above_two','legacy_limits','old_routes'))
    assert evidence['model-check']['real_deepseek'] and evidence['model-check']['model_calls']==1
    network=evidence['network-check']
    assert network['tls_certificate_verified'] and network['service_link']['backend_to_ai_authenticated']
    assert network['http_probes']=={'health_with_app_key':200,'without_app_key':403,'without_bearer':401}
    assert not network['tls_configuration_changed'] and network['system_ca_trust_verified'] is False
    contracts={kind:load(DOCS/'contracts'/('production-'+kind+'-openapi.json')) for kind in ('ai','backend')}
    ai,backend=contracts['ai'],contracts['backend']
    assert ai['info']['version']=='0.8.6' and backend['info']['version']=='0.9.0'
    assert all(p in ai['paths'] for p in ('/agent/dialogue/run','/agent/message','/agent/clarification','/agent/dialogue/p85/resolve'))
    assert all(p in backend['paths'] for p in ('/api/v1/agent/conversation-turns','/api/v1/agent/messages'))
    assert 'maximum' not in ai['components']['schemas']['RunResponse']['properties']['model_calls']
    assert 'maximum' not in backend['components']['schemas']['AutonomousCalls']['properties']['total']
    production={'stage':'V1-P8.6','source_sha256':signature,'source_commit':original['local_head'],
        'images':live['tags'],'ai_version':'0.8.6','business_version':'0.9.0','protocol':'inventory-autonomous-1',
        'files':{f'production-{kind}-openapi.json':sha((DOCS/'contracts'/f'production-{kind}-openapi.json').read_bytes()) for kind in contracts},
        'backend_export_method':'running container app.openapi(); public docs remain disabled',
        'app_joint_acceptance':False}
    (DOCS/'contracts/production-manifest.json').write_text(json.dumps(production,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    links=0
    for path in [*DOCS.glob('*.md'),ROOT/'agent/README.md',ROOT/'docs/versions/README.md',ROOT/'reports/p86-autonomous/README.md']:
        for link in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if link.startswith(('https:','http:','#','mailto:')):continue
            target=(path.parent/link.split('#')[0]).resolve()
            assert target.exists() or target==REPORT/'delivery-summary.json',(path.name,link)
            links+=1
    for name in ('p86_release.py','p86_release_remote.py','p86_verify_release.py'):
        ast.parse((ROOT/'tools'/name).read_text(encoding='utf-8'))
    protected=['frontend','backend/server/app','backend/server/alembic','agent/conversation','agent/p0','agent/p1']
    assert not subprocess.check_output(['git','diff','HEAD','--name-only','--',*protected],cwd=ROOT).strip()
    subprocess.check_call(['git','diff','--check'],cwd=ROOT)
    result={'release':'V1-P8.6','source_sha256':signature,'deployed':True,'ai_version':'0.8.6',
        'protocol':'inventory-autonomous-1','runtime_sources':{s:len(v) for s,v in source.items()},
        'all_services_healthy':all(v['health']=='healthy' for v in live['containers'].values()),
        'database_container_unchanged':True,'database_migrations_executed':False,
        'unrelated_runtime_sources_preserved':True,'private_configuration_preserved':True,
        'real_model_check':evidence['model-check'],'network_check':network,
        'document_links_checked':links,'production_contracts':2,'rollback_images_available':True,
        'app_joint_acceptance':False,'git_commit_or_push_performed':False}
    (REPORT/'delivery-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('real_model_check','network_check')},ensure_ascii=False))


if __name__=='__main__':main()
