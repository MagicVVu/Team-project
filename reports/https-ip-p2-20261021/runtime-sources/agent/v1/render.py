"""Evidence-only Chinese summaries; numbers come from deterministic results."""
STATUS = {"complete":"记录完整", "insufficient_data":"记录不足", "needs_review":"需要核对",
    "no_recorded_consumption":"完整窗口内没有有效消耗", "current_zero":"当前登记库存为零",
    "covered":"库存与已确认待购已覆盖目标", "excluded":"不纳入自动采购"}
REASONS = {
    "STOCK_VERIFICATION_REQUIRED":"请先核对实际库存并登记核对时间",
    "STOCK_VERIFICATION_STALE":"库存核对记录已陈旧，请重新核对",
    "STOCK_VERIFICATION_FUTURE":"库存核对时间不可信，请纠正",
    "FEWER_THAN_14_COMPLETE_DAYS":"有效完整观察日不足14天",
    "TOO_FEW_CONSUMPTION_EVENTS_OR_DATES":"消耗事件或发生日期数量不足",
    "RECORDING_COMPLETENESS_UNKNOWN":"无法确认消费记录是否完整",
    "NO_COMPLETE_COVERAGE_DAYS":"没有可核验的完整记录日",
    "HISTORY_TRANSPORT_INCOMPLETE":"历史数据没有读取完整",
    "UNEXPLAINED_STOCKOUT_OR_ADJUSTMENT":"有未解释的断货或库存调整",
    "PENDING_INCOMPLETE":"待购清单没有读取完整",
    "USABLE_STOCK_REQUIRES_REVIEW":"可用库存或风险资料需要核对",
    "EXPLICIT_PURCHASE_PREFERENCES_REQUIRED":"请在业务设置中明确最低库存或采购周期",
    "MEDICINE_PROCUREMENT_OUT_OF_SCOPE":"药品不自动补货，请核对需求并咨询专业人员",
    "NO_RECORDED_CONSUMPTION":"窗口内没有已登记的有效消耗",
}
def reasons(codes):
    return "；".join(REASONS.get(code,"请核对相关事实或事件记录") for code in dict.fromkeys(codes))

def reply(result):
    if result.status not in {"answered","needs_confirmation"}:
        return result.reply
    if result.intent=="QUERY_CONSUMPTION" and result.consumption_summary:
        return "\n".join(f"{s.name}：{s.observed_days}个完整观察日，登记有效消耗{s.effective_quantity} {s.unit}；{STATUS.get(s.status,s.status)}。"+reasons(s.reason_codes) for s in result.consumption_summary)+"\n排除丢弃及已撤销消耗；没有记录不代表没有实际消耗。本次未写入。"
    if result.intent=="QUERY_FORECAST" and result.forecast and result.feedback is None:
        return "\n".join(f.name+"："+(f"参考剩余{f.remaining_days}天，参考日期{f.reference_date}。"+f.conditions if f.status=="estimated" else STATUS.get(f.status,"需要核对")+"，不提供未来耗尽日期。"+reasons(f.reason_codes)) for f in result.forecast)+"\n依据登记事实，本次未写入。"
    if result.intent=="SUGGEST_PURCHASE" and result.recommendations and result.draft is None:
        return "\n".join(r.name+"："+(f"建议新增待购{r.suggested_quantity} {r.unit}，依据"+("明确最低库存" if r.source=="minimum_stock" else "登记消耗与明确采购周期")+"。" if r.status=="suggested" else STATUS.get(r.status,"需要核对")+"。"+reasons(r.reason_codes)) for r in result.recommendations)+"\n本次未写入库存或采购清单。"
    return result.reply
