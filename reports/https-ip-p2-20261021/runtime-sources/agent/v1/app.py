"""Selectable V1 release profile. The database gateway and old profiles are unchanged."""
import os
from p3.app import create_app as planning_app
from p3.schemas import Query
from p2.knowledge import RuleCatalog
from interaction.schemas import Message
from .manager import Manager
from .schemas import AgentResult, ClarificationRequest, FeedbackRequest, POLICY_VERSION
from .engines import RuleEngine, DeepSeekEngine, PROMPT_VERSION
from .knowledge import HumanRuleCatalog
from .tools import RemoteReader

class Profile:
    manager_type=Manager
    message_type=Message
    clarification_type=ClarificationRequest
    result_type=AgentResult
    title="Household V1 completion AI"
    version="0.6.0"
    health={"release_version":"V1-P6","input_policy_version":POLICY_VERSION,
        "extraction_prompt_version":PROMPT_VERSION,"public_gateway_contract":"v0.8-compatible",
        "clarification_protocols":["v1-local-1","v1-batch-selection-1","p5-continuation-1","p5-text-review-1"],
        "planning_contract":"v1-planning-context-1","operation_contract":"v1-operation-receipt-1",
        "rule_review_policy":"human_review_only","stock_max_age_hours":168,"jev_status":"deferred_by_user",
        "device_asr_verified":False,"production_chain_verified":False,"audio_upload_supported":False}

    @staticmethod
    def make_engine(name):
        return DeepSeekEngine() if name=="deepseek" else RuleEngine()

    @staticmethod
    def install_routes(app,manager,scope):
        from fastapi import Depends
        from p0.schemas import Scope
        @app.post("/overview/query",response_model=AgentResult)
        async def overview(body:Query,identity:Scope=Depends(scope)):
            return await manager.overview(body,identity)
        @app.post("/feedback/after-commit",response_model=AgentResult)
        async def feedback(body:FeedbackRequest,identity:Scope=Depends(scope)):
            return await manager.after_commit(body,identity)
        @app.post("/capabilities/check",response_model=AgentResult)
        async def capabilities(identity:Scope=Depends(scope)):
            return await manager.capabilities(identity)

def create_app(**kwargs):
    if kwargs.get("reader") is None:
        if not all(os.getenv(k) for k in ("BACKEND_BASE_URL","BACKEND_TOOL_TOKEN")):
            raise RuntimeError("V1 requires backend read configuration")
        kwargs["reader"]=RemoteReader(os.environ["BACKEND_BASE_URL"],os.environ["BACKEND_TOOL_TOKEN"])
    catalog=kwargs.get("catalog") or RuleCatalog.load(os.getenv("P2_RULES_PATH"))
    kwargs["catalog"]=HumanRuleCatalog.from_catalog(catalog)
    profile=Profile()
    profile.health={**profile.health,"active_human_rule_count":len(kwargs["catalog"].list_rules())}
    return planning_app(profile=profile,**kwargs)
