"""Validate actual isolated snapshots against unchanged published V1 JSON Schema."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'.cache/p4-schema-deps'))
sys.path.insert(0, str(ROOT/'agent'))
from jsonschema import Draft202012Validator, FormatChecker
from v1.schemas import PlanningSnapshot

schema_path=ROOT/'docs/versions/V1-P6/planning-context.schema.json'
schema=json.loads(schema_path.read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
validator=Draft202012Validator(schema,format_checker=FormatChecker())
checked=[]
for path in sorted((ROOT/'reports').glob('backend-p4-*-examples.json')):
    doc=json.loads(path.read_text(encoding='utf-8'))
    for key,value in doc.items():
        snapshots=[]
        if isinstance(value,dict) and 'data' in value and 'protocol_version' in value['data']:
            snapshots.append(value['data'])
        if key.startswith('concurrent_'): snapshots.extend([value['old'],value['new']])
        for index,snapshot in enumerate(snapshots):
            validator.validate(snapshot)
            parsed=PlanningSnapshot.model_validate(snapshot)
            assert parsed.protocol_version=='v1-planning-context-1'
            checked.append({'file':path.name,'case':key,'index':index,'schema_valid':True,'agent_valid':True})
http=ROOT/'reports/backend-p4-http-evidence.json'
if http.exists():
    value=json.loads(http.read_text(encoding='utf-8'))['snapshot']['data']
    validator.validate(value)
    PlanningSnapshot.model_validate(value)
    checked.append({'file':http.name,'schema_valid':True,'agent_valid':True})
assert checked
result={'published_schema':str(schema_path.relative_to(ROOT)),'validator':'jsonschema 4.26.0 Draft202012Validator + FormatChecker',
        'snapshots_validated':len(checked),'failures':0,'cases':checked}
(ROOT/'reports/backend-p4-schema-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
