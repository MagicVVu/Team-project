"""Evidence-based leads for teammates, never changes raw expected answers."""
import collections,json
from pathlib import Path
from prepare import ROUND,write
from summarize import load

KNOWN={
    'p84-22-1':{'category':'模型理解问题','finding':'多操作被理解为new_task。模型同时输出write_count=2，但最终走清除引用分支，没有按原预期追问操作优先级。','next':'AI负责人核对speech_act与多操作冲突的处理；保留原失败。'},
    'p84-24-2':{'category':'样本标注或版本契约待确认','finding':'模型正确输出correction和目标冰箱；当前库存已在冰箱，确定性代码未生成移动草稿，原预期要求edit。','next':'团队确定改回当前位置应取消、无操作还是保留待确认草稿；原FAIL不自动转PASS。'},
    'p84-29-6':{'category':'模型理解问题及保护规则待核对','finding':'模型将数量查询输出为question但reads为空，最终解释分支没有触发原预期的过期引用检查。','next':'核对缺少读取动作的查询降级策略，保留原FAIL。'},
    'p85-08-1-t5':{'category':'模型多轮理解问题','finding':'用户已经改为现在登记消耗两盒，模型仍输出negation，未生成草稿。','next':'检查否定之后明确重新请求的语义承接。'},
    'p85-08-1-t6':{'category':'前轮失败的后续影响','finding':'前轮没有生成草稿，因此状态追问缺少任务引用，返回TASK_REFERENCE_REQUIRED。','depends_on':'p85-08-1-t5','next':'与前轮一起修复和复测，不当成两个互不相关的模型缺陷。'},
}
def main():
    output=[]
    for directory in sorted((ROUND/'runs').glob('formal-*')):
        for row in load(directory/'cases.jsonl'):
            if row['status']=='PASS': continue
            note=KNOWN.get(row['id'],{'category':row.get('issue_category'),'finding':'见逐条失败断言和原始模型响应；自动分类尚未获负责人确认。','next':'先检查模型原始计划，再检查确定性规则与样本前提。'})
            output.append({'run':directory.name,'batch':row['batch'],'id':row['id'],'raw_status':row['status'],**note,
                'human_review_status':'pending','root_cause_confirmed_by_team':False,
                'evidence':str((directory/'cases.jsonl').relative_to(ROUND)),
                'raw_requests':str((directory/'requests.jsonl').relative_to(ROUND))})
    grouped=collections.defaultdict(list)
    for row in output:grouped[row['id']].append(row)
    write(ROUND/'reports/triage.json',{'notes':'AI-assisted analysis only; original statuses and expectations retained; supplemental audit failures also in issues.json',
        'nonpass_occurrences':len(output),'unique_nonpass_case_ids':len(grouped),'records':output,
        'by_case':{k:{'occurrences':len(v),'batches':[x['batch'] for x in v],'raw_statuses':[x['raw_status'] for x in v]} for k,v in grouped.items()}})
    lines=['# 问题定位与团队待确认事项','', '以下是依据原始证据给出的定位线索，未替团队确认根因，也未改变原FAIL或标注。','']
    for ident,note in KNOWN.items():
        if ident not in grouped:continue
        lines += [f'## {ident}', '',f"分类：{note['category']}。",'',note['finding'],'',f"下一步：{note['next']}",'']
    lines += ['## 本轮新样本与夹具的条件问题','',
        '5条风险绿色预期没有考虑当前规则的人工审核前提，列REVIEW。15条统计、预测和补货用例在对话到规划的选择映射上返回ITEM_NOT_FOUND，保留失败。',
        '零模型对照见evidence/planning-contract-diagnosis.json：更换为当前V1库存核对资料后，以商品名查询能得到正确统计和预测；使用b1作为商品键仍不可用。补货还需审核规则，原covered预期需团队复核。',
        '这些问题不能作为DeepSeek原始理解错误计数。新增用例的自动评分仍是待人工复核的合成基线。',
        '', '旧评分额外遗漏的问题见issues.json中FAIL_SUPPLEMENTAL_AUDIT，不能因原PASS而删除。']
    (ROUND/'reports/问题定位.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'nonpass_occurrences':len(output),'unique_ids':len(grouped)}))
if __name__=='__main__':main()
