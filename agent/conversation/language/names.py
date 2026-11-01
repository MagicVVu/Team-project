"""Read-only name matching; model search hints never establish identity."""
import json
from pathlib import Path
from p0.domain import DomainError,new_id
from p1.schemas import Parsed,Message
from ..schemas import AgentResult
from p1.manager import Manager
from p1.tools import check_scope
from . import choose

LEXICON=json.loads(Path(__file__).with_name('lexicon.json').read_text(encoding='utf-8'))


def variants(name,kind='names'):
    table=LEXICON[kind];key=name.strip().casefold()
    if key in table:return table[key]
    return [english for english,aliases in table.items() if key in [a.casefold() for a in aliases]]


async def resolve_name(reader,scope,name,hints=()):
    method=getattr(reader,'search_names',None)
    if method:
        rows,meta=await method(scope,name,list(hints))
        check_scope(scope,rows)
        if meta.get('query')!=name or meta.get('match_kind') not in {'original','dictionary','model_translation','none'}:
            raise DomainError('TOOL_UNAVAILABLE','Name matching evidence is invalid.',503)
        return rows,meta
    # In-process test readers use the same literal matching; no fake HTTP service.
    rows=await reader.search(scope,name)
    rows=[r for r in check_scope(scope,rows) if name.casefold() in r.name.casefold()]
    exact=[r for r in rows if r.name.casefold()==name.casefold()]
    if rows:return exact or rows,{'query':name,'match_kind':'original'}
    for kind,terms in (('dictionary',variants(name)),('model_translation',list(hints)[:3])):
        result={}
        for term in terms:
            if not isinstance(term,str) or not 1<=len(term)<=80:continue
            found=await reader.search(scope,term)
            for row in check_scope(scope,found):
                if term.casefold() in row.name.casefold():result[row.id]=row
        if result:return list(result.values()),{'query':name,'match_kind':kind,'lexicon_version':LEXICON['version']}
    return [],{'query':name,'match_kind':'none','lexicon_version':LEXICON['version']}


def clarification(owner,body,scope,rows,action,values,metadata):
    same={r.name for r in rows}
    parsed=Parsed.model_validate({**values,'intent':action or 'QUERY_INVENTORY','name':next(iter(same)) if len(same)==1 else metadata['query']})
    manager=Manager(None,owner.reader,now=owner.now)
    context=manager._context(Message(text=body.text,request_id=body.request_id,household_timezone=body.household_timezone),scope,new_id('trace'),parsed)
    context.candidates=rows;context.allowed_fields=['batch_id']
    return AgentResult(status='needs_clarification',original_text=body.text,reply=choose('请选择对应的真实物品，尚未执行。','Please select the registered item you mean. Nothing has been executed.'),
        trace_id=context.trace_id,intent=parsed.intent,candidates=rows,missing_fields=['batch_id'],clarification=context)


async def location(reader,scope,text):
    aliases=variants(text,'locations')
    rows=check_scope(scope,await reader.search(scope,None))
    known={r.location for r in rows if r.location}
    if text in known:return text,None
    literal=[value for value in known if value.casefold()==text.casefold()]
    if len(literal)==1:return literal[0],{'source':'verified_location_case','original_value':text,'value':literal[0]}
    if len(literal)>1:raise DomainError('LOCATION_MATCH_CONFIRMATION_REQUIRED','Specify the exact registered location.')
    matched=[value for value in known if value.casefold() in {a.casefold() for a in aliases}]
    if len(matched)>1:raise DomainError('LOCATION_MATCH_CONFIRMATION_REQUIRED','Specify the exact registered location.')
    if not matched:return text,None
    return matched[0],{'source':'verified_location_alias','original_value':text,'value':matched[0],'lexicon_version':LEXICON['version']}
