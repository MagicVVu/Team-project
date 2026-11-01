"""Render verified structured facts in English, without an extra LLM request."""
import re
from decimal import Decimal

UNIT_LABELS={"瓶":("bottle","bottles"),"盒":("box","boxes"),"包":("pack","packs"),"袋":("bag","bags"),
    "个":("item","items"),"件":("item","items"),"份":("portion","portions"),"卷":("roll","rolls"),
    "片":("sheet","sheets"),"台":("unit","units"),"吨":("tonne","tonnes")}
ACTION={"ADD":"add inventory","CONSUME":"consume","OPEN":"open","MOVE":"move","DISCARD":"discard","PLAN_ADD":"add to the shopping list"}
FIELDS={"batch_id":"item selection","name":"item name","quantity":"quantity","unit":"unit","location":"storage location",
    "to_location":"destination","opened_at":"opening date","purchased_at":"purchase date","label_expiry":"label expiry date"}
STATES={"needs_clarification":"More information is needed; nothing has been executed.",
    "needs_confirmation":"The draft is waiting for your confirmation; nothing has been executed.",
    "pending":"The draft is waiting for confirmation; nothing has been executed.",
    "processing":"The task is processing. Check the original request instead of submitting another one.",
    "cancelled":"The draft was cancelled. Cancelling it did not change inventory.",
    "expired":"The draft expired; no verified success receipt is available.",
    "superseded":"This draft was replaced. Review the latest task.",
    "conflict":"Inventory or draft versions have changed. Please review the latest information.",
    "unavailable":"The required business operation is currently unavailable.",
    "answered":"This query has been answered. Queries do not change inventory.",
    "error":"The task failed. Check the original request or handle it manually.",
    "unsupported":"This request is not supported; nothing has been executed.",
    "unknown":"The outcome has not been verified. Success cannot yet be confirmed."}
ERRORS={
    "REFERENCE_REQUIRED":"Select an item or specify its registered name.",
    "TASK_REFERENCE_REQUIRED":"Select the original task so its latest execution status can be checked.",
    "REFERENCE_EXPIRED":"I remember the object, but its reference expired. Please select the current item again.",
    "BATCH_NOT_FOUND":"No matching inventory item was found. Please check the name.",
    "INVALID_CANDIDATE":"Choose an item from the current candidate list.",
    "SINGLE_OBJECT_CONSUMPTION_REQUIRED":"Each inventory record is one physical item. Only whole-item consumption or discard is supported; a fraction cannot be deducted.",
    "SINGLE_OBJECT_AMOUNT_PROTECTED":"The quantity and unit of a whole-item consumption or discard draft cannot be edited. Select another item if needed.",
    "OBJECT_COUNT_INVALID":"The item count must be an integer from 1 to 10000. Weight or volume is stored as the specification of one portion.",
    "SPECIFICATION_READ_UNAVAILABLE":"The inventory read interface does not provide weight or capacity specifications. Item counts cannot be converted to grams or millilitres. Check the item details or provide its label.",
    "UNGROUNDED_FIELD":"A field does not match the original input or permitted current-task evidence. Please clarify it.",
    "UNGROUNDED_SELECTOR":"Specify the item or location in this message, or select a current candidate.",
    "UNGROUNDED_AMOUNT_MODE":"Specify an exact amount, the whole item, or a clearly stated fraction.",
    "MULTIPLE_WRITES":"You requested multiple changes. Which one should be handled first? No changes have been executed.",
    "INVALID_CONVERSATION_INPUT":"Inventory changes require a reviewed draft and your confirmation. Chat cannot bypass this requirement.",
    "NAME_MATCH_CONFIRMATION_REQUIRED":"Please confirm which registered item you mean before continuing.",
    "LOCATION_MATCH_CONFIRMATION_REQUIRED":"Several registered locations match. Please specify the exact destination.",
    "INVALID_DATE":"Use YYYY-MM-DD, today, yesterday, or an explicit month-name date. Ambiguous numeric dates require clarification.",
    "INVALID_UNIT":"Choose a supported item, packaging, weight or volume unit.",
    "INSUFFICIENT_STOCK":"The requested amount exceeds the verified inventory.",
    "ACTION_SEMANTIC_CONFLICT":"The proposed action conflicts with the original consumption/discard wording. Please correct the interpretation.",
    "HOUSEHOLD_FORBIDDEN":"This task or inventory does not belong to the current user and household.",
    "MEMORY_UNAVAILABLE":"Reliable history for this discussion is unavailable. Please identify the topic or original task.",
    "PARTIAL_BATCH_UNSUPPORTED":"Only a whole-item move or opening is supported; no partial change has been prepared.",
    "BATCH_TERMINAL":"This item is no longer active. No new change has been prepared.",
    "PROTECTED_DRAFT_MODE":"This is a whole-item draft. Its quantity cannot be changed separately.",
    "INVALID_DRAFT_EDIT":"Specify an editable quantity, date or destination. Changing the action or item starts a new task.",
    "TOOL_UNAVAILABLE":"The read service is unavailable. Verified information is retained; please check manually.",
}


def unit(value,count=None):
    pair=UNIT_LABELS.get(value)
    if not pair:return value
    return pair[0] if count is not None and Decimal(str(count))==1 else pair[1]


def error_text(code):
    if code in ERRORS:return ERRORS[code]
    if any(word in (code or "") for word in ("CONFLICT","CHANGED","NOT_EDITABLE","DECIDED")):return STATES['conflict']
    if "EXPIRED" in (code or ""):return ERRORS['REFERENCE_EXPIRED']
    if "DATE" in (code or ""):return ERRORS['INVALID_DATE']
    if "UNAVAILABLE" in (code or ""):return ERRORS['TOOL_UNAVAILABLE']
    return "This request could not be verified. Review the current information and try again."


def state_text(evidence):
    if evidence is None:return ERRORS['TASK_REFERENCE_REQUIRED']
    if evidence.receipt_verified and evidence.execution_status in {"committed","succeeded","executed"}:
        return "Execution succeeded according to the verified business receipt."
    status=evidence.execution_status or evidence.status
    return STATES.get(status,STATES['unknown'])


def calculation_lines(value):
    lines=[]
    for kind in ('risks','consumption_summary','forecast','recommendations','product_planning'):
        for item in value.get(kind) or []:
            name=item.get('name') or (item.get('product') or {}).get('name') or item.get('item_key') or 'Selected item'
            status=item.get('status') or item.get('level') or 'unknown'
            parts=[f"{kind.replace('_',' ').capitalize()} for {name}: {status}"]
            for field in ('current_stock','pending_quantity','target_stock','suggested_quantity','total_consumed','effective_quantity','observed_days','effective_events','consumption_dates','mean_daily_consumption','daily_recorded_consumption','remaining_days','reference_date','estimated_days_remaining','estimated_depletion_date','as_of','checked_at','updated_at','evaluated_at'):
                if item.get(field) is not None:parts.append(f"{field.replace('_',' ')}: {item[field]}")
            reasons=[r for r in item.get('reason_codes',[]) if re.fullmatch('[A-Z][A-Z0-9_]+',str(r))]
            if reasons:parts.append('Reasons: '+', '.join(reasons))
            if item.get('missing_information') or status in {'unavailable','insufficient_data','needs_review','unknown'}:
                parts.append('Required evidence is missing or still needs review; no reliable estimate is available.')
            lines.append('; '.join(parts)+'.')
    if value.get('data_gaps'):lines.append('Some required records are missing or have not been verified.')
    return lines


def localize_frame(frame,body):
    frame.locale=body.context.locale
    if frame.locale!='en':return frame
    plan=getattr(body,'plan',None);domain=frame.result or {};lines=[]
    reads={r.kind for r in plan.reads} if plan else {'quantity','location','dates'}
    for row in domain.get('facts',[]):
        name=row['name']
        if 'quantity' in reads:lines.append(f"{name}: registered count {row['quantity']} {unit(row['unit'],row['quantity'])}; status {row['status']}.")
        if 'location' in reads:lines.append(f"{name}: location {row.get('location') or 'not recorded'}.")
        if 'dates' in reads:lines.append(f"{name}: opened on {row.get('opened_at') or 'unknown'}; label expiry {row.get('label_expiry') or 'unknown'}.")
    domain_error=frame.error_code or domain.get('error_code')
    if domain.get('status')=='answered' and plan and plan.action and domain.get('facts') and not domain_error:
        row=domain['facts'][0]
        if plan.action=='OPEN' and row.get('opened_at'):
            lines.append(f"{row['name']} was already opened on {row['opened_at']}. No duplicate change is needed.")
        elif plan.action=='MOVE':
            lines.append(f"{row['name']} is already at {row.get('location') or 'the verified destination'}. No move is needed.")
    if domain_error:lines.append(error_text(domain_error))
    elif domain.get('status')=='needs_confirmation':
        command=domain['draft'];action=command['action'];name=command['name']
        if action in {'ADD','PLAN_ADD','CONSUME','DISCARD'}:
            lines.append(f"Draft to {ACTION[action]}: {command['quantity']} {unit(command['unit'],command['quantity'])} of {name}.")
        elif action=='MOVE':lines.append(f"Draft to move {name}: {domain.get('preview',{}).get('before',{}).get('location') or 'not recorded'} → {command['to_location']}.")
        else:lines.append(f"Draft to record {name} as opened on {command['opened_at']}.")
        lines.append('Waiting for your review and confirmation. Nothing has been written.')
    elif domain.get('status')=='needs_clarification' or frame.kind=='clarify':
        fields=domain.get('missing_fields') or list(frame.answers) or []
        lines.append('Please provide or review: '+', '.join(FIELDS.get(f,f) for f in fields)+'. Nothing has been executed.')
    elif frame.kind=='clear_reference':lines.append('A new task has started. Existing drafts were neither cancelled nor executed.')
    elif plan and plan.speech_act in {'status','basis'}:
        selected=body.context.tasks[plan.task_index] if plan.task_index is not None and plan.task_index<len(body.context.tasks) else next((t for t in body.context.tasks if body.context.active and t.task_id==body.context.active.task.task_id),None)
        if plan.speech_act=='status':lines.append(state_text(selected))
        else:lines.append('Saved calculation evidence is historical. Current stock, shopping records and reviewed rules must be checked before a new recommendation.')
    elif plan and plan.speech_act=='recall':
        history=[t.text for t in body.context.history[-3:]]
        if plan.memory_id and getattr(body,'archive',None):history=[e.text for e in body.archive.episodes if e.memory_id==plan.memory_id]
        lines.append('Earlier discussion: '+ ' / '.join(history)+'. This is history, not current inventory or an execution receipt.' if history else 'Reliable history for this topic is unavailable.')
    elif plan and plan.speech_act in {'social','discuss','negation','hypothesis'}:
        from ..p85.prose import household_prose
        proposed=plan.social_reply
        if plan.speech_act=='negation':lines.append('Understood. Nothing will be executed through chat. Any existing draft still needs your confirmation.')
        elif plan.speech_act=='hypothesis' and any(e.get('kind')=='hypothetical_calculation' for e in frame.evidence) and len(domain.get('facts',[]))==1:
            row=domain['facts'][0];half=Decimal(row['quantity'])/2
            lines.append(f"Hypothetically, half of {row['name']} would leave {half} {unit(row['unit'],half)}. This is a hypothetical calculation, not current inventory or an executable partial-item operation.")
        elif proposed and not re.search('[\u4e00-\u9fff]',proposed) and household_prose(proposed):lines.append(proposed)
        else:lines.append('We can take this one step at a time. Start with a small area, group similar items together, and tell me what you would like help with.')
    for evidence in frame.evidence:
        if evidence.get('kind')=='verified_calculation':lines+=calculation_lines(evidence.get('result') or {})
    lines+=calculation_lines(domain)
    if not lines:
        if frame.answers:lines=['Continuing the current task with the supplied information. Nothing has been executed.']
        elif domain.get('status')=='answered':lines=['No matching inventory records were found.']
        else:lines=['Please identify the item or task you would like to continue.']
    frame.facts={f'f{i}':value for i,value in enumerate(dict.fromkeys(lines))}
    frame.reply='\n'.join(frame.facts.values());frame.expression_required=False
    if frame.result:
        frame.result={**frame.result,'reply':frame.reply}
    return frame
