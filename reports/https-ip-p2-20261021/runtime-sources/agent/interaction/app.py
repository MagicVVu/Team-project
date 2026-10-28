"""Thin P5 input profile; routes, authentication and tools remain P3-owned."""
from p3.app import create_app as planning_app
from .manager import Manager
from .schemas import AgentResult, ClarificationRequest, Message, POLICY_VERSION
from .engines import DeepSeekEngine,RuleEngine,PROMPT_VERSION


class Profile:
    manager_type = Manager
    message_type = Message
    clarification_type = ClarificationRequest
    result_type = AgentResult
    title = "Household reviewed-text AI (V1-P5)"
    version = "0.5.0"
    health = {"release_version":"V1-P5", "input_policy_version":POLICY_VERSION,
        "extraction_prompt_version":PROMPT_VERSION,
        "clarification_protocols":["p1","p2-risk-selection-1","p3-item-selection-1","p5-continuation-1","p5-text-review-1"],
        "deduplication_owner":"business_backend", "audio_upload_supported":False,
        "public_gateway_contract":"v0.6", "input_provenance_owner":"caller",
        "device_asr_verified":False, "production_chain_verified":False}

    @staticmethod
    def make_engine(name):
        return DeepSeekEngine() if name=="deepseek" else RuleEngine()


def create_app(**kwargs):
    return planning_app(profile=Profile(), **kwargs)
