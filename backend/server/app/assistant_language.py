"""Request-scoped presentation language; never changes business facts."""
from contextvars import ContextVar
import json
from pathlib import Path

PROTOCOL='assistant-language-1'
LANGUAGES=['zh-CN','en']
current=ContextVar('assistant_locale',default='zh-CN')
LEXICON=json.loads((Path(__file__).parent/'data/assistant_lexicon.json').read_text(encoding='utf-8'))


def request_dump(body):
    value=body.model_dump(mode='json')
    # Preserve the exact pre-language digest for an omitted locale, including
    # all the other historical default/null fields.
    if 'locale' not in body.model_fields_set:value.pop('locale',None)
    return value


def text(chinese,english):return english if current.get()=='en' else chinese


class LanguageMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        value=next((v.decode('latin-1') for k,v in scope.get('headers',[]) if k==b'accept-language'),'')
        token=current.set('en' if value.lower().split(',')[0].split(';')[0].strip().startswith('en') else 'zh-CN')
        try:await self.app(scope,receive,send)
        finally:current.reset(token)


def variants(value,kind='names'):
    table=LEXICON[kind];key=value.strip().casefold()
    if key in table:return table[key]
    return [word for word,aliases in table.items() if key in {a.casefold() for a in aliases}]


def error_message(code):
    if any(v in code for v in ('CONFLICT','CHANGED')):return 'The task or inventory has changed. Refresh and review before continuing.'
    if 'EXPIRED' in code:return 'This task or reference has expired. Select the current item or recover the original task.'
    if code in {'APP_KEY_INVALID','APP_KEY_NOT_CONFIGURED'}:return 'Application access is unavailable. Update the app or contact the service maintainer.'
    if 'UNKNOWN' in code:return 'The outcome is not yet verified. Recover the original request; do not submit a new operation.'
    if 'UNIT' in code:return 'Use a supported unit and check the current item specification.'
    if 'DATE' in code:return 'Use a valid date and the household time zone.'
    if 'FORBIDDEN' in code:return 'You do not have permission to access this household or task.'
    if 'AUTH' in code:return 'Please sign in again before continuing.'
    return 'The request could not be completed. Review the current task and try again.'
