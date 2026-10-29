"""uvicorn conversation.p85.app:create_app --factory (explicit opt-in)."""
import os
from fastapi import Depends
from p0.schemas import Scope
from p0.domain import DomainError
from p0.engines import EngineError
from p2.knowledge import RuleCatalog
from p3.app import create_app as base_app
from v1.knowledge import HumanRuleCatalog
from ..app import Profile as PreviousProfile
from ..planning import RemoteReader
from . import flow
from .schemas import (P85Request, P85Understood, P85ResolveRequest, P85Resolved,
                      P85RespondRequest, P85Responded)


class Profile(PreviousProfile):
    title = "Household V1-P8.5 memory and semantic dialogue AI"
    version = "0.8.5"
    health = {**PreviousProfile.health, "maintenance_release": "V1-P8.5",
              "conversation_dialogue_protocol": "p85-dialogue-1",
              "dialogue_deadline_seconds": 60,
              "conversation_episode_protocol": "conversation-episodes-1",
              "memory_archive_max_episodes": 100, "memory_retrieved_episodes": 8,
              "memory_persistence_owner": "business_backend", "frontend_integration_verified": False}

    @staticmethod
    def install_routes(app, manager, scope):
        PreviousProfile.install_routes(app, manager, scope)

        @app.post("/agent/dialogue/p85/understand", response_model=P85Understood)
        async def understand(body: P85Request, identity: Scope = Depends(scope)):
            try:
                return await flow.understand(manager, body, identity)
            except (EngineError, TimeoutError) as error:
                raise DomainError(getattr(error, "code", "P85_UNDERSTANDING_TIMEOUT"),
                                  "本轮理解未完成，请保留原文，按原请求查询状态或手动核对。", 503) from error

        @app.post("/agent/dialogue/p85/resolve", response_model=P85Resolved)
        async def resolve(body: P85ResolveRequest, identity: Scope = Depends(scope)):
            return await flow.resolve(manager, body, identity)

        @app.post("/agent/dialogue/p85/respond", response_model=P85Responded)
        async def respond(body: P85RespondRequest, identity: Scope = Depends(scope)):
            return await flow.respond(manager, body)


def create_app(**kwargs):
    if kwargs.get("reader") is None:
        if not all(os.getenv(k) for k in ("BACKEND_BASE_URL", "BACKEND_TOOL_TOKEN")):
            raise RuntimeError("P8.5 requires backend read configuration")
        kwargs["reader"] = RemoteReader(os.environ["BACKEND_BASE_URL"], os.environ["BACKEND_TOOL_TOKEN"])
    kwargs["catalog"] = HumanRuleCatalog.from_catalog(kwargs.get("catalog") or RuleCatalog.load(os.getenv("P2_RULES_PATH")))
    profile = Profile()
    profile.health = {**profile.health, "active_human_rule_count": len(kwargs["catalog"].list_rules())}
    return base_app(profile=profile, **kwargs)
