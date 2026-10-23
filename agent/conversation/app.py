import os
from p2.knowledge import RuleCatalog
from p3.app import create_app as base_app
from v1.app import Profile as BaseProfile
from v1.knowledge import HumanRuleCatalog
from v1.tools import RemoteReader
from .schemas import Message, ClarificationRequest, AgentResult, POLICY_VERSION
from .manager import Manager
from .engines import RuleEngine, DeepSeekEngine, PROMPT_VERSION


class Profile(BaseProfile):
    manager_type = Manager
    message_type = Message
    clarification_type = ClarificationRequest
    result_type = AgentResult
    title = "Household V1-P7 conversation AI"
    version = "0.7.0"
    health = {**BaseProfile.health, "release_version":"V1-P7",
        "input_policy_version":POLICY_VERSION, "extraction_prompt_version":PROMPT_VERSION,
        "clarification_protocols":[*BaseProfile.health["clarification_protocols"], "p7-reference-continuation-1"],
        "object_reference_protocol":"p7-object-reference-1", "reference_ttl_seconds":900,
        "chat_policy_version":"p8-chat-1", "reply_routing_model_calls":0,
        "frontend_integration_verified":False, "execution_capabilities_owner":"business_backend",
        "public_reference_forwarding":"requires_separate_trusted_adapter"}

    @staticmethod
    def make_engine(name):
        return DeepSeekEngine() if name == "deepseek" else RuleEngine()

    @staticmethod
    def install_routes(app, manager, scope):
        from .reply_adapter import install
        install(app, scope)
        from fastapi import Depends
        from p0.schemas import Scope
        from p3.schemas import Query
        from v1.schemas import FeedbackRequest
        @app.post("/overview/query", response_model=AgentResult)
        async def overview(body:Query, identity:Scope=Depends(scope)):
            return await manager.overview(body, identity)
        @app.post("/feedback/after-commit", response_model=AgentResult)
        async def feedback(body:FeedbackRequest, identity:Scope=Depends(scope)):
            return await manager.after_commit(body, identity)
        @app.post("/capabilities/check", response_model=AgentResult)
        async def capabilities(identity:Scope=Depends(scope)):
            return await manager.capabilities(identity)


def create_app(**kwargs):
    if kwargs.get("reader") is None:
        if not all(os.getenv(k) for k in ("BACKEND_BASE_URL", "BACKEND_TOOL_TOKEN")):
            raise RuntimeError("P7 requires backend read configuration")
        kwargs["reader"] = RemoteReader(os.environ["BACKEND_BASE_URL"], os.environ["BACKEND_TOOL_TOKEN"])
    kwargs["catalog"] = HumanRuleCatalog.from_catalog(kwargs.get("catalog") or RuleCatalog.load(os.getenv("P2_RULES_PATH")))
    profile = Profile()
    profile.health = {**profile.health, "active_human_rule_count":len(kwargs["catalog"].list_rules())}
    return base_app(profile=profile, **kwargs)
