"""Demonstrate a test assertion collision with random identifiers, without edits."""
import importlib.util,json,pathlib,sys
from unittest.mock import patch
from uuid import UUID
ROOT=pathlib.Path(__file__).resolve().parent
import worker
worker.setup('uuid-diagnostic')
source=ROOT/'.snapshot/agent/tests/test_interaction.py'
spec=importlib.util.spec_from_file_location('handoff_interaction_test',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from interaction import session
rows=[]
for name,value in [('no_99_identifier','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),('contains_99_identifier','99999999-9999-4999-8999-999999999999')]:
    with patch.object(session,'uuid4',return_value=UUID(value)):
        try:module.test_asr_edit_state_never_uploads_original_transcript();test_passed=True
        except AssertionError:test_passed=False
        active=session.begin_recognition(session.new_session(module.PUBLIC_SCOPE));text=session.recognition_result(active,active.recognition_id,'添加99盒牛奶');state,body=session.submission(session.confirm_text(session.edit(text,'添加2盒牛奶')))
        public=session.public_message(state);internal=body.model_dump(mode='json')
        rows.append({'identifier_variant':name,'original_test_passed':test_passed,'public_body':public,'final_text':public['text'],'raw_transcript_field_in_public':'raw_transcript' in public,'raw_transcript_field_in_ai_message':'raw_transcript' in internal,'user_edited':state.user_edited,'raw_transcript_uploaded':False})
assert rows[0]['original_test_passed'] and not rows[1]['original_test_passed']
assert all(r['final_text']=='添加2盒牛奶' and not r['raw_transcript_field_in_public'] and not r['raw_transcript_field_in_ai_message'] for r in rows)
(ROOT/'evidence/p5-uuid-diagnostic.json').write_text(json.dumps({'finding':'Whole-JSON substring assertion matches random request/input UUIDs, even though raw transcript is not uploaded. Test design issue; original test and business code unchanged.','controlled_runs':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False,indent=2))
