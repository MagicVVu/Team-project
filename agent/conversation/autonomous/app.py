"""V1-P8.6: uvicorn conversation.autonomous.app:create_app --factory."""
import os
from fastapi import Depends
from p0.schemas import Scope
from p2.knowledge import RuleCatalog
from p3.app import create_app as base_app
from v1.knowledge import HumanRuleCatalog
from ..p85.app import Profile as P85Profile
from ..planning import RemoteReader
from .schemas import RunRequest, RunResponse, PROTOCOL
from . import runner


class Profile(P85Profile):
    title = "Household V1-P8.6 autonomous inventory assistant"
    version = "0.8.6"
    health = {**P85Profile.health, "maintenance_release":"V1-P8.6",
        "conversation_dialogue_protocol":PROTOCOL,
        "dialogue_max_model_calls":None, "dialogue_deadline_seconds":60,
        "dialogue_work_seconds":58, "legacy_dialogue_max_model_calls":2,
        "autonomous_loop_protocol":PROTOCOL, "autonomous_fixed_call_limit":False,
        "inventory_model":"single-object-1","partial_object_operations":False}

    def __init__(self, jev_router=None):
        self.jev_router = jev_router

    def install_routes(self, app, manager, scope):
        manager.inventory_model="single-object-1"
        manager.jev_router = self.jev_router
        P85Profile.install_routes(app, manager, scope)
        @app.post("/agent/dialogue/run", response_model=RunResponse)
        async def run(body: RunRequest, identity: Scope = Depends(scope)):
            return await runner.run(manager, body, identity)


def create_app(*, jev_mode=None, jev_router=None, **kwargs):
    mode = jev_mode if jev_mode is not None else os.getenv("JEV_MODE", "off")
    if mode not in {"off", "assist"}:
        raise RuntimeError("JEV_MODE must be off or assist")
    if mode == "off":
        jev_router = None
    if mode == "assist" and jev_router is None:
        from jev.runtime import from_environment
        jev_router = from_environment(mode)
    if kwargs.get("reader") is None:
        if not all(os.getenv(k) for k in ("BACKEND_BASE_URL", "BACKEND_TOOL_TOKEN")):
            raise RuntimeError("Autonomous AI requires backend read configuration")
        kwargs["reader"] = RemoteReader(os.environ["BACKEND_BASE_URL"], os.environ["BACKEND_TOOL_TOKEN"])
    kwargs["catalog"] = HumanRuleCatalog.from_catalog(kwargs.get("catalog") or RuleCatalog.load(os.getenv("P2_RULES_PATH")))
    profile = Profile(jev_router)
    profile.health = {**profile.health, "active_human_rule_count":len(kwargs["catalog"].list_rules()),
                      "jev_mode": "assist" if jev_router is not None else "off",
                      "jev_status": "optional_enabled" if jev_router is not None else "disabled"}
    return base_app(profile=profile, **kwargs)
