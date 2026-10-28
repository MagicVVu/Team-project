"""Small completion orchestrator; original lifecycle/risk/planning managers own their domain."""
import asyncio
import time
from datetime import datetime, timedelta, timezone

from p0.domain import DomainError, new_id
from p0.engines import EngineError
from p0.schemas import Scope
from p0.text import multiple_items
from p1.domain import guard
from p1.schemas import ConsumeCommand, ChangePreview, ProposedState, TraceStep
from p2.knowledge import RuleCatalog
from p2.risk import RiskTool
from p2.schemas import Batch
from p3.schemas import SelectionContext, Query, Answers as P3Answers
from interaction.manager import Manager as InputManager
from interaction.schemas import ClarificationRequest as P5Request, ContinuationContext, receipt
from interaction.policy import extraction_text, review_reason
from .knowledge import HumanRuleCatalog
from .policy import local_request, FACT_LABELS
from .schemas import (AgentResult, ClarificationRequest, LocalContext, SelectionEnvelope,
    Decision, Guidance, Section, Feedback, RuntimeInfo)
from .render import reply as render_reply
from .engines import PROMPT_VERSION
from .tools import Reader


class CountedEngine:
    def __init__(self, engine):
        self.engine, self.calls = engine, 0

    async def extract(self, text):
        self.calls += 1
        return await self.engine.extract(text)


class Manager:
    def __init__(self, engine, reader, catalog, *, now=None, timeout_seconds=10, max_stock_age_hours=168):
        if not 0 < timeout_seconds <= 10:
            raise ValueError("AI total deadline must be at most ten seconds")
        if not 1 <= max_stock_age_hours <= 8760:
            raise ValueError("Invalid inventory freshness policy")
        self.engine, self.reader = engine, reader
        self.catalog = catalog if isinstance(catalog,HumanRuleCatalog) else HumanRuleCatalog.from_catalog(catalog)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout_seconds, self.max_stock_age_hours = timeout_seconds, max_stock_age_hours

    def operation(self):
        return Operation(self)

    async def handle(self, message, scope):
        return await self.operation().execute("handle", message, scope)

    async def clarify(self, request, scope):
        return await self.operation().execute("clarify", request, scope)

    async def query(self, query, scope, intent):
        return await self.operation().execute("query", query, scope, intent)

    async def overview(self, query, scope):
        return await self.operation().execute("overview", query, scope)

    async def after_commit(self, query, scope):
        return await self.operation().execute("after_commit", query, scope)

    async def capabilities(self, scope):
        return await self.operation().execute("capabilities", None, scope)


class Operation:
    def __init__(self, owner):
        self.owner = owner
        self.engine = CountedEngine(owner.engine)
        self.reader = Reader(owner.reader, owner.now, owner.max_stock_age_hours)
        self.delegate = InputManager(self.engine, self.reader, owner.catalog,
            now=owner.now, timeout_seconds=owner.timeout_seconds)
        self.start = time.perf_counter()
        self.context = None
        self.input_receipt = None
        self.partial_result = None
        self.request_id = None

    async def execute(self, method, body, scope, intent=None):
        self.request_id = getattr(body,"request_id",None) or getattr(getattr(body,"context",None),"request_id",None)
        original = getattr(body,"text", "") or getattr(getattr(body,"context",None),"original_text","")
        try:
            async with asyncio.timeout(self.owner.timeout_seconds):
                if method == "query":
                    result = await self.delegate.query(body, scope, intent)
                else:
                    result = await getattr(self,method)(body, scope)
                result = self.public_result(result)
        except (DomainError, EngineError, TimeoutError) as error:
            code = getattr(error, "code", "AGENT_TIMEOUT")
            private = code == "HOUSEHOLD_FORBIDDEN"
            if code == "AGENT_TIMEOUT" and self.partial_result is not None:
                result = self.partial_result
                result.data_gaps.append(code)
                if result.feedback:
                    result.feedback.refresh_required = True
                    result.reply += " 当前资料刷新超时；已提交的业务结果不受影响，请查询原操作。"
                if not any(s.name=="planning" for s in result.sections):
                    result.sections.append(Section(name="planning",status="unavailable",reason_codes=[code]))
            else:
                result = AgentResult(status="error", reply=getattr(error,"message","处理暂不可用，请保留原文并手动核对。"),
                    original_text="" if private else original, trace_id=new_id("trace"), error_code=code,
                    clarification=None if private else self.context, manual_entry=True,
                    input_receipt=None if private else self.input_receipt)
        return self.decorate(result)

    def public_result(self, response):
        result = AgentResult.model_validate(response.model_dump())
        context = response.clarification
        if isinstance(context, ContinuationContext) and isinstance(context.delegate,SelectionContext):
            if context.delegate.allowed_fields == ["item_key"]:
                values = {f:getattr(context,f) for f in ("id","revision","scope","original_text","request_id",
                    "trace_id","household_timezone","created_at","expires_at")}
                has_batches = any(c.batches for c in context.delegate.candidates)
                result.clarification = SelectionEnvelope(**values, allowed_fields=["batch_id"] if has_batches else ["name"],
                    delegate=context, input_receipt=context.input_receipt)
                result.missing_fields = result.clarification.allowed_fields
                result.candidates = [b for c in context.delegate.candidates for b in c.batches]
                if not has_batches:
                    result.reply = "候选商品没有可选择的批次，请补充能唯一识别的名称；不能唯一识别时请在业务端核对。尚未写入。"
        return result

    def decorate(self, result):
        if result.error_code == "HOUSEHOLD_FORBIDDEN":
            # Never include previous-family diagnostics in an authorization error.
            result.data_gaps = []
        else:
            result.data_gaps = sorted(set(result.data_gaps+self.reader.gaps))
        for risk in result.risks:
            result.guidance.append(Guidance(batch_id=risk.batch_id, missing_fields=risk.missing_information,
                instructions=["请在物品资料中核对"+FACT_LABELS.get(f,f)+"，保存后重新查询。" for f in risk.missing_information]))
        for item_key,code in (v.rsplit(":",1) for v in self.reader.gaps):
            for value in result.forecast:
                if value.item_key == item_key:
                    value.status = "needs_review"
                    value.daily_recorded_consumption = value.remaining_days = value.reference_date = None
                    value.reason_codes = list(dict.fromkeys(value.reason_codes+[code]))
            for value in result.recommendations:
                if value.item_key == item_key:
                    value.status = "needs_review"
                    value.suggested_quantity = None
                    value.reason_codes = list(dict.fromkeys(value.reason_codes+[code]))
        gap_keys = {v.rsplit(":",1)[0] for v in self.reader.gaps}
        if result.draft and result.draft.action == "PLAN_ADD" and result.planning_basis and result.planning_basis.item_key in gap_keys:
            # Defence in depth, independent of the existing procurement gate.
            result.draft = result.preview = result.planning_basis = None
            result.status = "answered"
        if self.reader.gaps and result.forecast:
            if result.intent == "QUERY_FORECAST" and result.feedback is None:
                result.reply = "\n".join(f.name+"："+(f"参考剩余 {f.remaining_days} 天，参考日期 {f.reference_date}。"+f.conditions if f.status=="estimated" else "需要核对或数据不足，暂不提供未来耗尽日期。") for f in result.forecast)
            result.reply += "\n库存最近核对依据不足或已陈旧，暂不提供精确耗尽日期或自动补货草稿。"
        if result.draft and hasattr(result.draft,"quantity") and result.quantity_source is None:
            result.quantity_source = "planning_calculation" if result.planning_basis else "current_batch" if getattr(result.draft,"discard_mode",None)=="all" else "user_input"
        action = "CONFIRM" if result.draft else "CLARIFY" if result.status=="needs_clarification" else "READ" if result.status=="answered" else "WAIT"
        implementation = self.owner.engine
        while hasattr(implementation,"engine"):
            implementation = implementation.engine
        source = "llm" if self.engine.calls and hasattr(implementation,"budget") else "literal_rules" if self.engine.calls or result.intent else "input_guard"
        result.decisions = [
            Decision(node="intent_router",source=source,outcome=str(result.intent or result.status),
                reason_codes=[result.error_code] if result.error_code else []),
            Decision(node="event_classifier",source="deterministic",outcome=result.preview.event_type if result.preview and result.preview.event_type else "none"),
            Decision(node="clarification_gate",source="deterministic",outcome="CLARIFY" if result.status=="needs_clarification" else "PASS"),
            Decision(node="action_gate",source="deterministic",outcome=action)]
        result.request_id = None if result.error_code=="HOUSEHOLD_FORBIDDEN" else self.request_id
        result.runtime = RuntimeInfo(prompt_version=PROMPT_VERSION, ruleset_sha256=self.owner.catalog.sha256,
            model=getattr(implementation,"last_model",None) if self.engine.calls else None,model_calls=self.engine.calls)
        result.reply = render_reply(result)
        result.trace.append(TraceStep(step="v1_total",outcome=result.status,
            elapsed_ms=(time.perf_counter()-self.start)*1000))
        return result

    async def handle(self, message, scope):
        accepted = receipt(message,scope)
        self.input_receipt = accepted
        # Existing input guards always run before new literal routes.
        if (message.input and not message.input.user_confirmed) or guard(message.text) or review_reason(message.text):
            return await self.delegate.handle(message,scope)
        parsed = local_request(extraction_text(message.text))
        if parsed is None:
            return await self.delegate.handle(message,scope)
        kind,value = parsed
        if kind == "overview":
            result = await self.overview(Query(household_timezone=message.household_timezone),scope)
            result.original_text, result.input_receipt = message.text,accepted
            return result
        now = self.owner.now()
        self.context = LocalContext(id=new_id("clarify"),revision=1,scope=scope,
            original_text=message.text,request_id=message.request_id,trace_id=new_id("trace"),
            household_timezone=message.household_timezone,created_at=now,expires_at=now+timedelta(minutes=15),
            kind="finish" if kind=="finish" else "location",name=value if kind=="finish" else None,
            location=value if kind=="location" else None,unlocated=kind=="unlocated",allowed_fields=[],
            input_receipt=accepted)
        return await self.resolve_local(self.context,scope)

    def local_result(self, context, status, reply, **kwargs):
        return AgentResult(status=status,reply=reply,trace_id=context.trace_id,original_text=context.original_text,
            intent="CONSUME" if context.kind=="finish" else "QUERY_LOCATION_ITEMS",input_receipt=context.input_receipt,**kwargs)

    def need(self, context, fields, reply, **kwargs):
        context.allowed_fields = fields
        return self.local_result(context,"needs_clarification",reply,clarification=context,
            missing_fields=fields,candidates=context.candidates,manual_entry=True,**kwargs)

    async def resolve_local(self, context, scope):
        if context.kind == "location":
            rows = [Batch.model_validate(b.model_dump()) for b in await self.reader.search(scope,None)]
            if not context.unlocated and not context.location:
                return self.need(context,["location"],"请选择或填写要查询的真实位置。",location_options=sorted({b.location for b in rows if b.location}))
            matched = [b for b in rows if (b.location is None if context.unlocated else b.location==context.location)]
            if not matched and not context.unlocated:
                options = sorted({b.location for b in rows if b.location and context.location in b.location})
                if options:
                    return self.need(context,["location"],"没有精确匹配的位置，请选择已登记的具体位置。",location_options=options)
            reply = "；".join(f"{b.name}：{b.quantity} {b.unit}，状态 {b.status}（批次 {b.id}）" for b in matched)
            return self.local_result(context,"answered",reply or "该位置没有匹配的登记物品。",facts=matched,total_count=len(matched))
        if not context.name:
            return self.need(context,["name"],"请明确哪个物品已经全部用完；尚未写入。")
        if context.selected_batch_id:
            previous = next(b for b in context.candidates if b.id==context.selected_batch_id)
            batch = Batch.model_validate((await self.reader.get_batch(scope,previous.id)).model_dump())
            if batch != previous:
                context.candidates, context.selected_batch_id = [batch],None
                return self.need(context,["batch_id"],"库存已变化，请重新核对当前批次；不会自动把新增库存算作已用完。",error_code="VERSION_CONFLICT")
            rows = [batch]
        else:
            rows = [Batch.model_validate(b.model_dump()) for b in await self.reader.search(scope,context.name)]
            exact = [b for b in rows if b.name.casefold()==context.name.casefold()]
            rows = exact or [b for b in rows if context.name.casefold() in b.name.casefold()]
        context.candidates = rows
        if len(rows)!=1:
            return self.need(context,["batch_id"] if rows else ["name"],"请选择已经用完的目标批次；不会默认选择第一批。")
        batch = rows[0]
        if batch.status!="ACTIVE" or batch.quantity<=0:
            return self.local_result(context,"answered","该批次已结束或无库存，无需生成新变更。",facts=[batch],error_code="BATCH_TERMINAL")
        if "batch_id" in context.allowed_fields and not context.selected_batch_id:
            return self.need(context,["batch_id"],"请明确选择重新展示的当前批次。")
        command = ConsumeCommand(name=batch.name,batch_id=batch.id,expected_version=batch.version,
            quantity=batch.quantity,unit=batch.unit)
        from p1.schemas import Batch as BaseBatch
        before = BaseBatch.model_validate({k:getattr(batch,k) for k in BaseBatch.model_fields})
        preview = ChangePreview(batch_id=batch.id,before=before,event_type="Consumed",quantity_delta=-batch.quantity,
            after=ProposedState(quantity=0,unit=batch.unit,location=batch.location,opened_at=batch.opened_at,status="FINISHED"))
        return self.local_result(context,"needs_confirmation",
            "按登记剩余量生成整批消费草稿，请核对是否已全部用完。尚未写入；不会重复计算Finished为消费。",
            draft=command,preview=preview,quantity_source="current_batch")

    async def clarify(self, request, scope):
        context = request.context
        if context.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN","澄清任务不属于当前用户或家庭。",403)
        self.context, self.input_receipt = context,getattr(context,"input_receipt",None)
        if not isinstance(context,(LocalContext,SelectionEnvelope)):
            return await self.delegate.clarify(P5Request.model_validate(request.model_dump()),scope)
        if context.revision != request.revision:
            raise DomainError("CLARIFICATION_CONFLICT","修订号已变化，请查询最新任务。",409)
        if not context.created_at<=self.owner.now()<context.expires_at:
            raise DomainError("CLARIFICATION_EXPIRED","澄清已过期，请重新提交。",409)
        answers = request.answers.model_dump(exclude_none=True)
        if not answers or not set(answers)<=set(context.allowed_fields):
            raise DomainError("INVALID_CLARIFICATION","只接受当前缺失字段和真实候选批次。")
        if any(isinstance(v,str) and (guard(v) or review_reason(v)) for v in answers.values()):
            raise DomainError("INVALID_CLARIFICATION_INPUT","答案不能改变动作或包含不确定指令。")
        if isinstance(context,SelectionEnvelope):
            inner = context.delegate.delegate
            if "batch_id" in answers:
                pairs = [(c.item_key,b) for c in inner.candidates for b in c.batches if b.id==answers["batch_id"]]
                if len(pairs)!=1 or pairs[0][1].household_id!=scope.household_id:
                    raise DomainError("INVALID_CANDIDATE","请选择当前候选中的真实批次。")
                mapped = P3Answers(item_key=pairs[0][0])
                return await self.delegate.clarify(P5Request(context=context.delegate,revision=request.revision,answers=mapped),scope)
            # No anchor: re-resolve only a unique real name, never pick a duplicate.
            copied = context.delegate.model_copy(deep=True)
            copied.allowed_fields = copied.delegate.allowed_fields = ["name"]
            return await self.delegate.clarify(P5Request(context=copied,revision=request.revision,answers=P3Answers(**answers)),scope)
        context = context.model_copy(deep=True)
        self.context = context
        if "name" in answers:
            if multiple_items(answers["name"]):
                raise DomainError("INVALID_CLARIFICATION_INPUT","请只填写一个物品名称。")
            context.name = answers["name"]
        if "location" in answers: context.location,context.unlocated=answers["location"],False
        if "batch_id" in answers:
            if answers["batch_id"] not in {b.id for b in context.candidates}:
                raise DomainError("INVALID_CANDIDATE","请选择当前候选批次。")
            context.selected_batch_id = answers["batch_id"]
        context.revision += 1
        return await self.resolve_local(context,scope)

    async def overview(self, query, scope):
        if query.mode!="suggest":
            raise DomainError("INVALID_QUERY_MODE","关注摘要不生成批量草稿。")
        result = AgentResult(status="answered",intent="QUERY_OVERVIEW",reply="按已登记事实汇总关注事项，尚未写入。",
            original_text="",trace_id=new_id("trace"),evaluated_at=self.owner.now())
        try:
            rows = await self.reader.search(scope,query.name)
            risk_tool = RiskTool(self.owner.catalog)
            result.facts = rows
            risks=[]
            for row in rows:
                await asyncio.sleep(0)
                risks.append(risk_tool.evaluate(row,result.evaluated_at,query.household_timezone))
            ordered=sorted(risks,key=lambda r:({"red":0,"orange":1,"yellow":2,"unknown":3,"green":4}[r.level],r.name,r.batch_id))
            result.total_count=len(ordered)
            result.risks=ordered[:50]
            result.truncated=len(ordered)>50
            result.sections.append(Section(name="risk",status="available",evaluated_at=result.evaluated_at))
            self.partial_result = result
        except DomainError as error:
            if error.code=="HOUSEHOLD_FORBIDDEN": raise
            result.sections.append(Section(name="risk",status="unavailable",reason_codes=[error.code]))
        remaining = self.owner.timeout_seconds-(time.perf_counter()-self.start)
        try:
            async with asyncio.timeout(max(.001,remaining*.90)):
                planned=await self.delegate.query(query,scope,"SUGGEST_PURCHASE")
            if planned.error_code=="HOUSEHOLD_FORBIDDEN":
                raise DomainError("HOUSEHOLD_FORBIDDEN","规划事实不属于当前家庭。",403)
            if planned.status=="error":
                result.sections.append(Section(name="planning",status="unavailable",reason_codes=[planned.error_code or "PLANNING_UNAVAILABLE"]))
            else:
                # Sections explicitly retain independent read snapshots.
                result.forecast,result.recommendations=planned.forecast[:50],planned.recommendations[:50]
                result.truncated |= len(planned.forecast)>50 or len(planned.recommendations)>50
                result.sections.append(Section(name="planning",status="partial" if self.reader.gaps else "available",
                    snapshot_id=planned.snapshot_id,evaluated_at=planned.evaluated_at,reason_codes=list(self.reader.gaps)))
        except (DomainError,TimeoutError) as error:
            if getattr(error,"code",None)=="HOUSEHOLD_FORBIDDEN": raise
            result.sections.append(Section(name="planning",status="unavailable",reason_codes=[getattr(error,"code","AGENT_TIMEOUT")]))
        if all(s.status=="unavailable" for s in result.sections):
            result.status,result.error_code,result.manual_entry="error","OVERVIEW_UNAVAILABLE",True
        result.reply += f" 当前展示风险关注 {sum(r.attention for r in result.risks)} 项；各部分注明读取时间和可用状态。"
        return result

    async def after_commit(self, query, scope):
        proof=await self.reader.operation_receipt(scope,query.operation_id)
        if proof.status!="committed" or proof.committed_at>self.owner.now()+timedelta(seconds=1):
            raise DomainError("OPERATION_NOT_COMMITTED","业务操作尚未获得有效提交凭证，请查询原操作。",409)
        result=AgentResult(status="answered",reply="业务操作已提交；以下反馈读取当前事实，不会再次提交或写入。",
            original_text="",trace_id=new_id("trace"),evaluated_at=self.owner.now(),
            feedback=Feedback(operation_id=proof.operation_id,committed_trace_id=proof.trace_id,committed_at=proof.committed_at))
        self.partial_result = result
        try:
            remaining=self.owner.timeout_seconds-(time.perf_counter()-self.start)
            async with asyncio.timeout(max(.001,remaining*.90)):
                for batch_id,version in proof.batch_versions.items():
                    batch=await self.reader.get_batch(scope,batch_id)
                    result.facts.append(batch)
                    if batch.version<version: result.feedback.refresh_required=True
                    if batch.version>version: result.feedback.later_changes=True
                if not result.feedback.refresh_required:
                    result.risks=[RiskTool(self.owner.catalog).evaluate(b,result.evaluated_at,query.household_timezone) for b in result.facts]
                result.sections.append(Section(name="risk",status="partial" if result.feedback.refresh_required else "available",
                    evaluated_at=result.evaluated_at,reason_codes=["COMMITTED_VERSION_NOT_VISIBLE"] if result.feedback.refresh_required else []))
                remaining=self.owner.timeout_seconds-(time.perf_counter()-self.start)
                async with asyncio.timeout(max(.001,remaining*.90)):
                    planned=await self.delegate.query(Query(household_timezone=query.household_timezone),scope,"QUERY_FORECAST")
                if planned.error_code=="HOUSEHOLD_FORBIDDEN":
                    raise DomainError("HOUSEHOLD_FORBIDDEN","规划数据越权。",403)
                affected={b.id for b in result.facts}
                keys={i.item_key for snap in self.reader.snapshots.values() for i in snap.items if any(b.id in affected for b in i.batches)}
                snapshots=list(self.reader.snapshots.values())
                versions={b.id:b.version for snap in snapshots for item in snap.items for b in item.batches}
                if planned.status!="error" and (
                    any(versions.get(k,0)<v for k,v in proof.batch_versions.items()) or
                    any((proof.committed_at-snap.as_of).total_seconds()>1 for snap in snapshots)):
                    result.feedback.refresh_required=True
                    result.data_gaps.append("POST_COMMIT_SNAPSHOT_BEHIND")
                result.forecast=[f for f in planned.forecast if f.item_key in keys]
                result.sections.append(Section(name="planning",status="unavailable" if planned.status=="error" else "partial" if result.feedback.refresh_required or self.reader.gaps else "available",
                    snapshot_id=planned.snapshot_id,evaluated_at=planned.evaluated_at,
                    reason_codes=[planned.error_code] if planned.error_code else []))
                if result.feedback.refresh_required:
                    result.forecast=[]
        except (DomainError,TimeoutError) as error:
            if getattr(error,"code",None)=="HOUSEHOLD_FORBIDDEN": raise
            result.feedback.refresh_required=True
            result.data_gaps.append(getattr(error,"code","AGENT_TIMEOUT"))
            result.reply+=" 当前资料刷新未完成，请稍后查询；已提交的业务结果不受影响。"
        return result

    async def capabilities(self, unused, scope):
        # An explicit authenticated live check; health itself never reads business data.
        result=AgentResult(status="answered",reply="只读能力检查，未写入。Jev按用户要求暂缓。",
            original_text="",trace_id=new_id("trace"))
        for name,call in (("risk",lambda:self.reader.search(scope,None)),
                          ("planning",lambda:self.reader.planning_context(scope))):
            try:
                value=await call()
                reasons=[]
                if name=="risk":
                    if not self.owner.catalog.list_rules(): reasons.append("HUMAN_RULE_REVIEW_REQUIRED")
                    if any(getattr(b,"category","unknown")=="unknown" or getattr(b,"label_date_type","unknown")=="unknown" for b in value):
                        reasons.append("RISK_FACTS_INCOMPLETE")
                else:
                    reasons.extend(self.reader.gaps)
                    if not value.history_complete: reasons.append("HISTORY_INCOMPLETE")
                    if not value.pending_complete: reasons.append("PENDING_INCOMPLETE")
                result.sections.append(Section(name=name,status="partial" if reasons else "available",reason_codes=reasons))
            except DomainError as error:
                if error.code=="HOUSEHOLD_FORBIDDEN": raise
                result.sections.append(Section(name=name,status="unavailable",reason_codes=[error.code]))
        return result
