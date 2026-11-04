"""No API calls. Preserve all records and verify source, privacy, counts and limits."""
import collections,json,os
from pathlib import Path
from decimal import Decimal
from prepare import ROUND,REPO,sha,write
source=json.loads((ROUND/'evidence/source.json').read_text(encoding='utf-8'))
changed=[r['path'] for r in source['protected'] if not (REPO/r['path']).exists() or sha(REPO/r['path'])!=r['sha256']]
snapshot_changed=[r['path'] for r in source['snapshot'] if sha(ROUND/'.snapshot'/r['path'])!=r['sha256']]
d=json.loads((ROUND/'reports/analysis.json').read_text(encoding='utf-8'))
wire=[w for q in [*d['questions'],*d.get('superseded_budget_blocked_attempts',[])] for w in q['wire_ids']]
book=d['complete'].get('budget_after') or {}
updated_authorization=(ROUND/'evidence/authorization-update-20261104.json').exists()
secret_hits=[];secret_names=[]
secrets={k:os.environ.get(k) for k in ['DEEPSEEK_API_KEY','TYPESAFE_API_KEY']}
for base,dirs,files in os.walk(ROUND):
    dirs[:]=[n for n in dirs if n not in {'.snapshot','.runtime','.qa','node_modules','__pycache__','.pytest_cache'}]
    for name in files:
        path=Path(base)/name
        # Archive formats are separately checked after authoring by unpacking text entries.
        data=path.read_bytes()
        for key,value in secrets.items():
            if value and value.encode() in data:secret_hits.append(str(path.relative_to(ROUND)));secret_names.append(key)
        if path.suffix in {'.xlsx','.docx'}:
            import zipfile
            with zipfile.ZipFile(path) as archive:
                for entry in archive.namelist():
                    content=archive.read(entry)
                    if any(value and value.encode() in content for value in secrets.values()):secret_hits.append(str(path.relative_to(ROUND)))
checks={'teammate_and_old_tracked_files_unchanged':not changed,'snapshot_unchanged':not snapshot_changed,'initial_premises_match':not d['initial_premise_mismatches'],'wire_ids_unique':len(wire)==len(set(wire)),'wire_count_reconciles':len(wire)==d['formal_apis'],'per_question_http_counts_reconcile':all(q['actual_http_calls']==len(q['wire_ids'])==q['deepseek_http_calls']+q['jev_http_calls'] for q in d['questions']),'off_has_zero_jev_http':all(not q['jev_http_calls'] for q in d['questions'] if q['mode']=='off'),'no_inventory_writes':all(q['inventory_unchanged'] for q in d['questions']),'current_user_fee_authorization_respected':updated_authorization and book.get('cost_stop_enabled') is False or Decimal(str(book.get('charged_or_reserved_cny','99')))<=Decimal(10),'native_jev_not_over_1_usd':Decimal(str((d['complete'].get('jev_after') or {}).get('charged_or_reserved_usd','99')))<=1,'all_planned_executions_completed':d['formal_questions']==1152 and d['unexecuted']==0 and d['unpaired_executions']==0,'only_budget_blocked_attempts_superseded':all(q['status']=='BLOCKED' for q in d.get('superseded_budget_blocked_attempts',[])),'secret_scan_performed':all(secrets.values()),'no_configured_api_keys_in_public_evidence':not secret_hits,'formal_has_stopped':d['complete'].get('stop_reason')!='RUNNING'}
result={'checks':checks,'all_pass':all(checks.values()),'changed_protected_files':changed,'changed_snapshot_files':snapshot_changed,'secret_hit_files':sorted(set(secret_hits)),'public_scan_never_prints_keys':True,'formal_executions':d['formal_questions'],'formal_http':d['formal_apis'],'unexecuted':d['unexecuted'],'unpaired_executions':d['unpaired_executions']}
write(ROUND/'evidence/final-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
raise SystemExit(0 if result['all_pass'] else 1)
