"""One 10 CNY allowance across both modes/providers; keep native cumulative limits."""
import json,os,sqlite3
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
from p0.budget import Budget as NativeDeepSeek
from p0.engines import EngineError
from jev.budget import Budget as NativeJev,RESERVATION,NANO
from jev.schemas import JevError
from prepare import ROUND,write
PRIVATE=Path(os.environ['LOCALAPPDATA'])/'GarinAIModelTest'
class Combined:
    limit=Decimal('10');fx=Decimal('8')
    def __init__(self):
        self.path=PRIVATE/'jev-ab-20261103-c2d5ea6.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,provider TEXT,reserved TEXT,actual TEXT,native_id TEXT,status TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS policy(k TEXT PRIMARY KEY,v TEXT)')
            expected={'limit_cny':'10','usd_budget_allowance':'8','source':'c2d5ea6','authorization':'user separate combined cap 10 CNY 2026-11-03'}
            for k,v in expected.items():db.execute('INSERT OR IGNORE INTO policy VALUES(?,?)',(k,v))
            if dict(db.execute('SELECT k,v FROM policy'))!=expected:raise RuntimeError('COMBINED_POLICY_MISMATCH')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def used(self,db):return sum((Decimal(r[0]) for r in db.execute('SELECT COALESCE(actual,reserved) FROM calls')),Decimal(0))
    def reserve(self,provider,amount):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.used(db)+amount>self.limit:raise EngineError('BUDGET_EXCEEDED')
            ident=uuid4().hex;db.execute('INSERT INTO calls VALUES(?,?,?,NULL,NULL,?)',(ident,provider,str(amount),'reserved'));return ident
    def update(self,ident,*,native_id=None,actual=None,status='measured'):
        with self.db() as db:db.execute('UPDATE calls SET actual=?,native_id=COALESCE(?,native_id),status=? WHERE id=?',(str(actual) if actual is not None else None,native_id,status,ident))
    def summary(self):
        with self.db() as db:
            return {'limit_cny':'10','charged_or_reserved_cny':str(self.used(db)),'reservations':db.execute('SELECT COUNT(*) FROM calls WHERE status != ?',('not_sent',)).fetchone()[0],'unknown_usage_calls':db.execute("SELECT COUNT(*) FROM calls WHERE actual IS NULL").fetchone()[0],'usd_budget_allowance':'8','not_platform_bill':True}
class DeepSeekBudget(NativeDeepSeek):
    def __init__(self,combined):
        path=PRIVATE/'baselines/3f007ba/budget.sqlite'
        if not path.exists():raise RuntimeError('ORIGINAL_DEEPSEEK_LEDGER_MISSING')
        super().__init__(path,ROUND/'.snapshot/agent/eval/pricing.json',Decimal('20'))
        self.combined=combined;self.ids={}
    def reserve(self,model,input_bound,output_bound):
        price=self.pricing(model);amount=(Decimal(str(price['input_cny_per_million']))*input_bound+Decimal(str(price['output_cny_per_million']))*output_bound)/1000000
        ident=self.combined.reserve('deepseek',amount)
        try:result=super().reserve(model,input_bound,output_bound)
        except BaseException:
            self.combined.update(ident,actual=Decimal(0),status='not_sent');raise
        self.ids[result[0]]=ident;self.combined.update(ident,native_id=result[0],status='reserved');return result
    def settle(self,call_id,usage,pricing):
        super().settle(call_id,usage,pricing)
        with self.connection() as db:actual=db.execute('SELECT actual FROM calls WHERE id=?',(call_id,)).fetchone()[0]
        if actual is not None:self.combined.update(self.ids[call_id],actual=Decimal(str(actual)))
class JevBudget(NativeJev):
    def __init__(self,combined):
        super().__init__(PRIVATE/'jev/budget.sqlite');self.combined=combined;self.ids={}
    def reserve(self):
        try:ident=self.combined.reserve('jev',Decimal(RESERVATION)/NANO*self.combined.fx)
        except EngineError:raise JevError('BUDGET_EXCEEDED') from None
        try:call_id,amount=super().reserve()
        except BaseException:
            self.combined.update(ident,actual=Decimal(0),status='not_sent');raise
        self.ids[call_id]=ident;self.combined.update(ident,native_id=call_id,status='reserved');return call_id,amount
    def settle(self,call_id,input_tokens):
        amount=super().settle(call_id,input_tokens)
        self.combined.update(self.ids[call_id],actual=amount*self.combined.fx);return amount
