"""Keep original smoke, distinguish observed product timeout from broken measurement."""
import json
from prepare import ROUND,write
for path in (ROUND/'runs').glob('smoke-*/complete.json'):
    summary=json.loads(path.read_text(encoding='utf-8'))
    requests=[json.loads(s) for s in (path.parent/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    rows=[json.loads(s) for s in (path.parent/'questions.jsonl').read_text(encoding='utf-8').splitlines()]
    assertions={'source_run_complete':summary['complete'],'real_jev_with_usage':any(r['provider']=='jev' and r['http_status']==200 and r['returned_model']=='jev-1.13.0' and r.get('usage') for r in requests),'real_deepseek_with_usage':any(r['provider']=='deepseek' and r['http_status']==200 and r.get('usage') for r in requests),'no_auth_balance_errors':not any(r['http_status'] in {401,402,403} for r in requests),'actual_counts_reconcile':sum(r['actual_http_calls'] for r in rows)==len(requests),'no_inventory_writes':all(r['inventory_unchanged'] for r in rows),'both_modes':{r['mode'] for r in rows}=={'off','assist'},'off_never_calls_jev':all(not r['jev_http_calls'] for r in rows if r['mode']=='off'),'no_local_http_failure':all(r['local_http_status']==200 for r in rows)}
    write(path.parent/'validated.json',{'ready':all(assertions.values()),'checks':assertions,'original_complete_json_unchanged':True,'reason':'The initial infrastructure gate wrongly required all HTTP calls to succeed. Observed Jev timeouts are product behavior with complete failed-request records and conservative reservations; retain them, do not retry or alter timeout.','not_a_quality_pass':True})
    print(json.dumps(assertions,ensure_ascii=False))
