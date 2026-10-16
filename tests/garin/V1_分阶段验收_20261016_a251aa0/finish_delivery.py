"""Finalize only this new Garin round and validate counted evidence."""
import pathlib,json,hashlib,datetime,sys
r=pathlib.Path(sys.argv[1]).resolve()
if r.name!='V1_分阶段验收_20261016_a251aa0' or r.parent.name!='garin':raise ValueError('Wrong round')
def read(p):return json.loads((r/p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
baseline=read('baseline.json');source=pathlib.Path(baseline['source']);audit=read('evidence/source-integrity.json')
for label,key,base in [('teammate_files','outside_round_tracked_hashes',source),('historical_garin','historical_garin_hashes',source),('snapshot_inputs','snapshot_sha256',r/'.snapshot')]:
    changes=[p for p,digest in baseline[key].items() if not (base/p).is_file() or sha(base/p)!=digest]
    assert not changes,(label,changes)
    audit[label]={'checked':len(baseline[key]),'changed':changes}
audit['final_checked_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(r/'evidence/source-integrity.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
counts=read('results/分阶段统计.json');android=read('results/Android结果.json')
assert counts['pytest'][1]['counts']=={'PASS':464};assert android['testDebugUnitTest']['pass']==17
assert counts['legacy_program_assertions_pass']==81;assert counts['special_evidence_records']==24
assert all(x['all_checks_pass'] for x in counts['native_datasets'])
assert sum(1 for x in (r/'results/旧用例失败清单.jsonl').read_text(encoding='utf8').splitlines() if x.strip())==37
doc=r/'Garin V1分阶段测试工作记录.docx';assert doc.stat().st_size>10000
qa={'document':doc.name,'page_count':4,'method':'Microsoft Word read-only PDF export then bundled Poppler rasterization; all 4 page PNGs inspected','packaged_renderer':'render_docx.py failed: bundled LibreOffice unavailable on Windows; diagnostic captured in work session','all_pages_reviewed':True,'human_signoff':False,'final_docx_sha256':sha(doc),'qa_intermediates_delivered':False}
(r/'evidence/word-layout-check.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf8')
excluded={'.snapshot','.runtime','.scratch','__pycache__'}
manifest={p.relative_to(r).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in r.rglob('*') if p.is_file() and not set(p.relative_to(r).parts)&excluded and 'temp' not in p.relative_to(r).parts and p.name!='evidence-manifest.json'}
(r/'evidence/evidence-manifest.json').write_text(json.dumps({'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':manifest,'note':'Ignores private runtime/cache/snapshot. No remote upload or Git commit performed.'},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'manifest_files':len(manifest),'public_bytes':sum(x['bytes'] for x in manifest.values()),'document_sha256':sha(doc),'source_unchanged':True},ensure_ascii=False,indent=2))
