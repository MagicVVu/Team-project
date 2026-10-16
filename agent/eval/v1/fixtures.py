from decimal import Decimal
from eval.p3.fixtures import NOW, SCOPE, snapshot, FixtureReader as BaseReader
from p2.knowledge import RuleCatalog
from v1.schemas import PlanningSnapshot

def fixture(name="燕麦饮", unit="盒", case="normal"):
    values=snapshot().model_dump(mode="json")
    values["protocol_version"]="v1-planning-context-1"
    item=values["items"][0]
    item["name"],item["unit"]=name,unit
    item["stock_verification"]={"checked_at":NOW.isoformat(),"source":"synthetic-test-count"}
    for batch in item["batches"]: batch.update(name=name,unit=unit,location="餐边柜")
    for event in item["events"]: event["unit"]=unit
    for pending in values["pending"]: pending["unit"]=unit
    if case=="multiple":
        item["batches"].append({**item["batches"][0],"id":"b2","version":9})
    if case=="terminal":
        item["batches"][0].update(quantity="0",status="FINISHED")
    if case=="opened":
        item["batches"][0].update(is_opened=True,opened_at="2026-10-10")
    if case=="missing_stock":
        item["stock_verification"]=None
    if case=="empty":
        values["items"],values["pending"]=[],[]
    if case=="no_history":
        item["events"],item["coverage"]=[],[]
    if case=="unlocated":
        item["batches"][0]["location"]=None
    return PlanningSnapshot.model_validate(values)

class FixtureReader(BaseReader):
    def __init__(self, name="燕麦饮",unit="盒",case="normal"):
        super().__init__(fixture(name,unit,case))

def synthetic_reviewed_catalog():
    # Only a test fixture. No real rule or report is marked human reviewed.
    data=RuleCatalog.load().data.model_copy(deep=True)
    for rule in data.rules:
        rule.review_kind="human_review"
        rule.reviewed_by="synthetic-test-only-reviewer"
    return RuleCatalog(data)
