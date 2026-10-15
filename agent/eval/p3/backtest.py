"""Offline chronological validation of captured snapshots, never production data writes.

python -m eval.p3.backtest --input reviewed-intervals.json --output report.json
Only pre-cutoff captured state is accepted. No reconstruction from today's
inventory, preferences, coverage or risk annotations is permitted.
"""
import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator
from p0.schemas import Model
from p3.forecast import evaluate
from p3.schemas import Event, PlanningSnapshot


class Interval(Model):
    id: str
    source: str = Field(pattern=r"^(real|synthetic)$")
    human_reviewed: bool
    item_key: str
    household_timezone: str
    captured_at: AwareDatetime
    snapshot: PlanningSnapshot
    outcome_known_at: AwareDatetime
    exhausted_on: date | None
    outcome_verified: bool
    followup_complete: bool
    followup_events: list[Event]

    @model_validator(mode="after")
    def cutoff(self):
        if self.captured_at != self.snapshot.as_of or self.outcome_known_at <= self.captured_at:
            raise ValueError("只接受当时捕获的快照及其之后核验的结果")
        if any(e.recorded_at > self.captured_at for i in self.snapshot.items for e in i.events):
            raise ValueError("历史快照含未来录入的事件")
        ZoneInfo(self.household_timezone)
        if sum(i.item_key == self.item_key for i in self.snapshot.items) != 1:
            raise ValueError("快照中必须有唯一目标商品")
        today = self.captured_at.astimezone(ZoneInfo(self.household_timezone)).date()
        if self.exhausted_on is not None and (self.exhausted_on < today or self.exhausted_on > self.outcome_known_at.astimezone(ZoneInfo(self.household_timezone)).date()):
            raise ValueError("核验耗尽日期不在随访范围内")
        return self


def backtest(intervals):
    rows = []
    for interval in intervals:
        item = next(i for i in interval.snapshot.items if i.item_key == interval.item_key)
        forecast = evaluate(item, interval.snapshot, interval.household_timezone)
        label = interval.exhausted_on
        interventions = [e.id for e in interval.followup_events if e.item_key == interval.item_key and e.committed
            and interval.captured_at < e.occurred_at <= interval.outcome_known_at
            and e.recorded_at <= interval.outcome_known_at
            and (label is None or e.occurred_at.astimezone(ZoneInfo(interval.household_timezone)).date() <= label)
            and e.kind in {"Added", "Purchased", "Discarded", "Adjusted", "Reversed", "Corrected"}]
        verified = (interval.source == "real" and interval.human_reviewed and interval.outcome_verified
                    and interval.followup_complete and not interventions and label is not None)
        error = abs((forecast.reference_date-label).days) if verified and forecast.reference_date else None
        rows.append({"id":interval.id, "forecast_status":forecast.status,
            "reference_date":str(forecast.reference_date) if forecast.reference_date else None,
            "intervention_event_ids":interventions, "eligible_real_interval":verified,
            "absolute_error_days":error})
    eligible = [r for r in rows if r["eligible_real_interval"]]
    errors = [r["absolute_error_days"] for r in eligible if r["absolute_error_days"] is not None]
    sufficient = len(errors) >= 30
    return {"policy_version":"p3-policy-1", "real_effect_verified":False,
        "metrics_available":sufficient, "acceptance_thresholds_frozen":False,
        "reviewed_real_intervals":len(eligible), "estimated_real_intervals":len(errors),
        "mae_days":sum(errors)/len(errors) if sufficient else None,
        "median_absolute_error_days":median(errors) if sufficient else None,
        "estimate_coverage":len(errors)/len(eligible) if sufficient else None,
        "refusal_rate":1-len(errors)/len(eligible) if sufficient else None,
        "baseline_comparison_verified":False, "rows":rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    intervals = [Interval.model_validate(row) for row in json.loads(args.input.read_text(encoding="utf-8"))]
    if len({i.id for i in intervals}) != len(intervals): parser.error("interval ids must be unique")
    args.output.write_text(json.dumps(backtest(intervals),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
