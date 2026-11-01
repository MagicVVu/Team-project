"""Pure bilingual evidence helpers. No model, dates from a trusted clock only."""
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

SMALL=dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),range(20)))
TENS=dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(),range(20,100,10)))
WORDS="|".join([*SMALL,*TENS,"hundred","thousand"])
EN_NUMBER=rf"\b(?:(?:{WORDS})(?:(?:[ -]+and)?[ -]+(?:{WORDS}))*)\b"
UNITS={"bottle":"瓶","bottles":"瓶","box":"盒","boxes":"盒","carton":"盒","cartons":"盒",
    "pack":"包","packs":"包","bag":"袋","bags":"袋","roll":"卷","rolls":"卷","sheet":"片","sheets":"片",
    "item":"件","items":"件","piece":"件","pieces":"件","portion":"份","portions":"份",
    "milliliter":"ml","milliliters":"ml","millilitre":"ml","millilitres":"ml",
    "liter":"L","liters":"L","litre":"L","litres":"L","gram":"g","grams":"g",
    "kilogram":"kg","kilograms":"kg","ton":"吨","tons":"吨","tonne":"吨","tonnes":"吨"}
EN_UNIT=r"(?i:\b(?:"+"|".join(sorted(UNITS,key=len,reverse=True))+r")\b)"
EN_ACTIONS={
    "ADD":r"\b(?:add|bought|received|stock(?:ed)?\s+up)\b",
    "CONSUME":r"\b(?:consume[ds]?|consumption|drank|drunk|ate|eaten|used(?:\s+up)?|finished|use\s+up|finish)\b",
    "MOVE":r"\b(?:move[ds]?|relocate[ds]?|put)\b",
    "OPEN":r"\b(?:open(?:ed)?|unseal(?:ed)?)\b",
    "DISCARD":r"\b(?:discard(?:ed)?|throw(?:n)?\s+away|threw\s+away|dispose\s+of|dump(?:ed)?)\b",
    "PLAN_ADD":r"\b(?:shopping\s+list|purchase\s+plan|buy\s+list)\b"}
ORDINALS={"first":1,"second":2,"third":3,"fourth":4,"fifth":5,"sixth":6,"seventh":7,"eighth":8,"ninth":9,"tenth":10}
MONTHS={name.lower():i for i,name in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"),1)}
MONTHS.update({name[:3]:value for name,value in list(MONTHS.items())})
ALL=r"(?i:\b(?:all|remaining|rest|entire|whole|finished|used up|drank it|ate it)\b)"
HALF=r"(?i:\b(?:half|fifty percent)\b|50\s*[%％])"
INJECTION=r"(?i:\b(?:ignore|disregard|override)\b.{0,40}\b(?:instructions?|rules?|system|permissions?)\b|\b(?:skip|bypass)\b.{0,20}\b(?:confirmation|auth(?:orization)?)\b|\bexecute\b.{0,20}\bwithout\s+confirm)"


def english_number(value):
    value=value.strip().lower()
    if value in {"a","an"}:return Decimal(1)
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?",value):return Decimal(value.replace(",",""))
    if re.fullmatch(r"-?\d+(?:\.\d+)?",value):return Decimal(value)
    words=value.replace("-"," ").split()
    if not words or any(w not in {*SMALL,*TENS,"and","hundred","thousand"} for w in words):return None
    def under_hundred(tokens):
        if len(tokens)==1:return SMALL.get(tokens[0],TENS.get(tokens[0]))
        if len(tokens)==2 and tokens[0] in TENS and 1<=SMALL.get(tokens[1],0)<=9:
            return TENS[tokens[0]]+SMALL[tokens[1]]
        return None
    def under_thousand(tokens):
        if len(tokens)>=2 and 1<=SMALL.get(tokens[0],0)<=9 and tokens[1]=='hundred':
            tail=tokens[2:]
            if not tail:return SMALL[tokens[0]]*100
            if tail[0]=='and':tail=tail[1:]
            remainder=under_hundred(tail)
            return SMALL[tokens[0]]*100+remainder if remainder is not None and remainder>0 else None
        return under_hundred(tokens)
    if 'thousand' not in words:
        value=under_thousand(words)
    elif words.count('thousand')==1:
        at=words.index('thousand');part=under_thousand(words[:at]);tail=words[at+1:]
        if not part:return None
        if not tail:return Decimal(part*1000)
        if tail[0]=='and':tail=tail[1:]
        remainder=under_thousand(tail)
        value=part*1000+remainder if remainder is not None and remainder>0 else None
    else:return None
    return Decimal(value) if value is not None else None


def numbers(text):
    clean=re.sub(r"\d{4}-\d{1,2}-\d{1,2}","",text)
    result=[]
    for match in re.finditer(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?|"+EN_NUMBER,clean,re.I):
        number=english_number(match[0])
        if number is not None:result.append(number)
    if re.search(r"(?i)\b(?:a|an)\s+"+EN_UNIT,clean):result.append(Decimal(1))
    return result


def parse_english_date(value,reference,zone):
    today=reference.astimezone(zone).date();value=value.strip().lower().rstrip('.')
    if value in {"today","yesterday","tomorrow"}:return today+timedelta(days={"today":0,"yesterday":-1,"tomorrow":1}[value])
    match=re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(\d{4})",value)
    if match and match[1] in MONTHS:return date(int(match[3]),MONTHS[match[1]],int(match[2]))
    match=re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})",value)
    if match and match[2] in MONTHS:return date(int(match[3]),MONTHS[match[2]],int(match[1]))
    raise ValueError("Use YYYY-MM-DD, today, yesterday or an explicit month-name date")


def ordinal(text):
    value=text.strip().lower().rstrip("?.!")
    value=re.sub(r'^where is\s+','',value)
    value=re.sub(r'\s+(?:located|stored)$','',value)
    match=re.fullmatch(r"(?:(?:please\s+)?(?:choose|select|pick)\s+)?(?:the\s+)?("+"|".join(ORDINALS)+r"|\d+(?:st|nd|rd|th)?)(?:\s+(?:one|item|piece|batch))?(?:\s*(?:'s\s+)?(?:location|quantity)|\s+(?:where is it|where is that|where is it stored))?",value)
    if not match:
        numeric=re.fullmatch(r"(?:number\s+|#)(\d+|"+"|".join(SMALL)+r")",value)
        if numeric:return int(english_number(numeric[1]))
    if not match:return None
    return int(re.sub(r"\D","",match[1])) if re.search(r"\d",match[1]) else ORDINALS[match[1]]


def polite_core(text):
    """Remove a known conversational wrapper only for literal matching.

    The request and every field quote still refer to the unchanged original.
    This never removes negations, conditions or conjunctions.
    """
    return re.sub(r"(?i)^(?:please[, :]\s*|for this task:\s*|could you help:\s*|i want to check this:\s*)", "", text.strip(), count=1)


def ordinal_evidence(text):
    values=[]
    for match in re.finditer(r"(?i)\b("+"|".join(ORDINALS)+r"|\d+(?:st|nd|rd|th))\b|\bnumber\s+(\d+|"+"|".join(SMALL)+r")\b|#(\d+)\b",text):
        token=next(g for g in match.groups() if g is not None).lower()
        value=ORDINALS.get(token)
        if value is None:
            value=english_number(re.sub(r"(?<=\d)(?:st|nd|rd|th)$","",token))
        if value is not None:values.append(int(value))
    return set(values)


def literal_plan(body):
    from conversation.p85.schemas import P85Plan
    ctx=body.context;text=polite_core(body.text);low=text.lower().rstrip("?.!")
    if low in {"new task","start a new task","start new task"}:return P85Plan(speech_act="new_task")
    if re.fullmatch(r"(?:has it (?:been )?(?:executed|done|completed)|(?:did it|did that) (?:work|finish)|what(?:'s| is) (?:the |its )?status|why (?:hasn't|has not) it (?:moved|been moved)|what (?:do i|else do i) need to do)",low):return P85Plan(speech_act="status")
    if low in {"why this suggestion","why do you recommend that","what is the basis","why did you suggest that"}:return P85Plan(speech_act="basis")
    if re.fullmatch(r"(?:please )?(?:don't|do not|stop|hold off|wait)(?: (?:execute|executing|change|changing|move|moving|anything|it|that|yet|this|for now|please))*(?:; i am only asking)?",low):return P85Plan(speech_act="negation")
    if re.fullmatch(r"(?:consume|discard) (?:half|fifty percent|50\s*%) of (?:it|this item|that item)",low):
        return P85Plan(speech_act='request',action='DISCARD' if low.startswith('discard') else 'CONSUME',write_count=1,amount_mode='half',selector={'use_reference':True})
    if re.fullmatch(r"(?:where (?:is|are) (?:it|this|that|this item|this batch)|(?:its|this item's) (?:location|position))",low):
        return P85Plan(speech_act="question",selector={"use_reference":True},reads=[{"kind":"location"}])
    if low in {"how much is left","how many are left","how much of it is left","its quantity"}:
        return P85Plan(speech_act="question",selector={"use_reference":True},reads=[{"kind":"quantity"}])
    if match:=re.fullmatch(r"(?i)i used some ([^;.!?]{1,80}); the amount is unknown[.!]?",text):
        return P85Plan(speech_act='request',action='CONSUME',write_count=1,amount_mode='unknown',selector={'name':match[1]})
    if match:=re.fullmatch(r"(?i)add (.+?) ([^;.!?]{1,80}); i need to check the unit[.!]?",text):
        quantity=english_number(match[1])
        if quantity is not None:
            return P85Plan(speech_act='request',action='ADD',write_count=1,fields={
                'name':{'value':match[2],'quote':match[2]},'quantity':{'value':str(quantity),'quote':match[1]}})
    n=ordinal(text)
    if n is not None and ctx.choices:
        return P85Plan(speech_act="supplement" if ctx.active and ctx.active.task.status=="needs_clarification" else "question",
            selector={"choice_index":n-1 if n>=1 else len(ctx.choices)},reads=[] if ctx.active and ctx.active.task.status=="needs_clarification" else [{"kind":"location"}])
    active=ctx.active.task if ctx.active else None
    command=active.result.draft if active and active.result else None
    if active and active.status=="needs_clarification":
        allowed=set(active.result.missing_fields or [])
        if len(ctx.choices)==1 and low in {"yes","yes that one","that one","correct"} and "batch_id" in allowed:
            return P85Plan(speech_act="supplement",selector={"choice_index":0})
        fields={}
        date_fields=allowed & {'opened_at','purchased_at','label_expiry'}
        if len(date_fields)==1:
            try:
                from p1.domain import parse_date
                parse_date(text,ctx.trusted_now,body.household_timezone)
                fields[next(iter(date_fields))]={"value":text,"quote":text}
            except (ValueError,TypeError):pass
        if 'unit' in allowed and re.fullmatch(EN_UNIT,text):fields['unit']={'value':text,'quote':text}
        if len(allowed)==1 and allowed & {'location','to_location'} and not any(re.search(p,text,re.I) for p in EN_ACTIONS.values()):
            fields[next(iter(allowed))]={'value':text,'quote':text}
        if "quantity" in allowed:
            matches=numbers(text)
            if len(matches)==1:
                fields["quantity"]={"value":str(matches[0]),"quote":text}
                if match:=re.search(EN_UNIT,text):fields["unit"]={"value":match[0],"quote":text}
        if fields:return P85Plan(speech_act="supplement",fields=fields)
    if command and active.status=="needs_confirmation":
        match=re.fullmatch(r"(?i)(?:make that|change (?:it|that) to|actually[,]?|no[,]? make (?:it|that))\s+(.+?)[.!]?",text)
        if match:
            quote=match[1];values=numbers(quote)
            if len(values)==1:
                fields={"quantity":{"value":str(values[0]),"quote":quote}}
                if unit:=re.search(EN_UNIT,quote):fields["unit"]={"value":unit[0],"quote":quote}
                return P85Plan(speech_act="correction",fields=fields)
        if command.action=="MOVE" and (match:=re.fullmatch(r"(?i)(?:actually[,]?\s*)?(?:move it to|change (?:it|the location) to|make that)\s+(.+?)[.!]?",text)):
            return P85Plan(speech_act="correction",fields={"to_location":{"value":match[1],"quote":match[1]}})
    return None
