from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .knowledge import RuleCatalog
from .schemas import Batch, Evidence, RiskResult

PRIORITY = {"green": 0, "unknown": 1, "yellow": 2, "orange": 3, "red": 4}


class RiskTool:
    """Deterministic evidence-based attention assessment, never a safety certificate."""
    def __init__(self, catalog: RuleCatalog):
        self.catalog = catalog

    def evaluate(self, batch: Batch, now: datetime, timezone_name="Asia/Shanghai", reminder_days=3):
        if now.tzinfo is None:
            raise ValueError("评估时间必须带时区")
        if not 0 <= reminder_days <= 365:
            raise ValueError("提醒天数必须在 0 到 365 内")
        today = now.astimezone(ZoneInfo(timezone_name)).date()
        evidence, missing, levels, used = [], [], [], {}
        all_rules = self.catalog.applicable(batch)

        def add(code, text, level=None, rule=None, **facts):
            evidence.append(Evidence(reason_code=code, explanation=text,
                facts={k: str(v) if v is not None else None for k, v in facts.items()},
                rule_id=rule.id if rule else None, rule_version=rule.version if rule else None,
                source=rule.source if rule else None))
            if level: levels.append(level)
            if rule: used[rule.id] = rule.version

        def needed(field):
            if field not in missing: missing.append(field)

        def finish(excluded=False):
            level = max(levels, key=PRIORITY.get) if levels else "green"
            if missing and PRIORITY[level] < PRIORITY["orange"]:
                level = "unknown"
            if excluded: level = "unknown"
            messages = {"red": "先停止使用并核对包装标签，按适用说明处理；药品问题咨询药师。",
                "orange": "先核对保存或开封要求及物品状态，暂不依据该记录判为可用。",
                "yellow": "已进入设置的提醒窗口，请核对标签并安排处理。",
                "unknown": "信息或适用规则不足，请补充所列事实后重新评估。",
                "green": "已知规则未触发关注条件；仍应遵循包装说明并核对实物状态。"}
            return RiskResult(batch_id=batch.id, name=batch.name, batch_version=batch.version,
                level=level, attention=not excluded and level != "green", excluded=excluded,
                reason_codes=[e.reason_code for e in evidence], evidence=evidence, missing_information=missing,
                recommended_action="该批次已结束，不纳入当前可用库存关注列表。" if excluded else messages[level],
                evaluated_at=now, household_timezone=timezone_name, ruleset_version=self.catalog.data.version,
                rule_versions=used, source_human_reviewed=bool(used) and all(
                    r.review_kind == "human_review" for r in all_rules if r.id in used))

        if batch.status != "ACTIVE" or batch.quantity <= 0:
            add("BATCH_TERMINAL", "该批次已结束或无库存，不作当前在库风险判断。", status=batch.status, quantity=batch.quantity)
            return finish(excluded=True)
        if not all_rules:
            needed("applicable_reviewed_rule")
            add("NO_APPLICABLE_RULE", "没有与登记类别和条件匹配的已核对规则。", category=batch.category)
            if batch.category == "unknown": needed("category")
            return finish()
        # Multiple simultaneously applicable definitions of a kind are not
        # silently resolved by version number, strictness or list order.
        groups = {kind: [r for r in all_rules if r.kind == kind] for kind in ("label_date", "storage", "near_expiry", "after_open")}
        conflicts = {kind for kind, rules in groups.items() if len(rules) > 1}
        for kind in sorted(conflicts):
            needed("rule_resolution")
            add("RULE_CONFLICT", "存在同时适用的规则，请审核后保留唯一版本。", kind=kind,
                rules=",".join(r.id + ":" + r.version for r in groups[kind]))

        if batch.opened_at and batch.opened_at > today:
            needed("opened_at")
            add("INVALID_OPENED_DATE", "开封日期在未来，需要核对。", opened_at=batch.opened_at, today=today)
        if batch.purchased_at and batch.label_expiry and batch.label_expiry < batch.purchased_at:
            needed("purchased_at_or_label_expiry")
            add("DATE_CONFLICT", "标签日期早于登记购入日期，需要核对事实。")
        if (batch.is_opened is False and batch.opened_at is not None):
            needed("is_opened")
            add("OPEN_STATE_CONFLICT", "未开封状态与已登记开封日期冲突。")

        label_rules = groups["label_date"]
        label_rule = label_rules[0] if len(label_rules) == 1 else None
        label_usable = False
        if not label_rule:
            needed("label_date_rule")
        else:
            allowed = {"use_by", "best_before"} if batch.category == "food" else {"expiry"}
            if batch.label_expiry is None: needed("label_expiry")
            if batch.label_date_type not in allowed: needed("label_date_type")
            if batch.label_context_valid is not True:
                needed("label_context_valid")
                add("LABEL_CONTEXT_UNCONFIRMED", "尚未确认原标签适用于当前处理状态；不得自动延长或重算有效期。",
                    rule=label_rule, label_context_valid=batch.label_context_valid)
            label_usable = batch.label_expiry is not None and batch.label_date_type in allowed and batch.label_context_valid is True
            if label_usable:
                days = (batch.label_expiry - today).days
                if days < 0:
                    if batch.label_date_type == "best_before":
                        add("BEST_BEFORE_PASSED", "已超过登记的品质日期，不能据此单独判定食品安全。", "yellow", label_rule,
                            label_expiry=batch.label_expiry, label_date_type=batch.label_date_type)
                    else:
                        add("LABEL_DATE_PASSED", "已超过当前适用的标签期限，请遵循包装说明。", "red", label_rule,
                            label_expiry=batch.label_expiry, label_date_type=batch.label_date_type)
                else:
                    add("LABEL_DATE_CURRENT", "登记标签日期尚未超过；这不构成安全保证。", rule=label_rule,
                        label_expiry=batch.label_expiry, days_remaining=days)
                if 0 <= days <= reminder_days and len(groups["near_expiry"]) == 1:
                    add("LABEL_DATE_NEAR", "进入用户设置的提前提醒窗口，该窗口不是安全阈值。", "yellow", groups["near_expiry"][0],
                        reminder_days=reminder_days, days_remaining=days)

        storage_rules = groups["storage"]
        if len(storage_rules) != 1:
            needed("storage_rule")
        else:
            rule = storage_rules[0]
            if batch.storage_condition is None: needed("storage_condition")
            if batch.label_storage_condition is None: needed("label_storage_condition")
            if batch.storage_condition is not None and batch.label_storage_condition is not None:
                if batch.storage_condition != batch.label_storage_condition:
                    add("STORAGE_MISMATCH", "登记保存条件与包装要求不一致，需要核对；位置名称不等于测量条件。", "orange", rule,
                        storage_condition=batch.storage_condition, label_storage_condition=batch.label_storage_condition)
                else:
                    add("STORAGE_RECORDED_MATCH", "登记条件与包装要求一致，未验证实际温度或完整保存历史。", rule=rule,
                        storage_condition=batch.storage_condition, label_storage_condition=batch.label_storage_condition)

        if batch.is_opened is None:
            needed("is_opened")
        elif batch.is_opened:
            if batch.opened_at is None:
                needed("opened_at")
            if len(groups["after_open"]) != 1:
                needed("after_open_rule")
                add("OPEN_RULE_REQUIRED", "已开封，需要与具体商品匹配的包装开封要求；不采用通用品类天数。")
            elif batch.opened_at is not None and batch.opened_at <= today:
                rule = groups["after_open"][0]
                deadline = batch.opened_at + timedelta(days=rule.max_days_after_open)
                if today >= deadline:
                    add("OPEN_WINDOW_REACHED", "已达到包装规则的开封窗口；按日期粒度保守提示核对。", "orange", rule,
                        opened_at=batch.opened_at, max_days_after_open=rule.max_days_after_open, review_date=deadline)
                else:
                    add("OPEN_WINDOW_CURRENT", "尚未达到该商品已核对的开封窗口；不覆盖标签期限或其他风险。", rule=rule,
                        opened_at=batch.opened_at, max_days_after_open=rule.max_days_after_open, review_date=deadline)
        if missing:
            add("INFORMATION_INCOMPLETE", "还缺少判断所需事实或规则。", missing=",".join(missing))
        elif not levels:
            add("NO_RULE_TRIGGER", "本次已知条件未触发关注规则，不表示物品已经检测安全。")
        return finish()
