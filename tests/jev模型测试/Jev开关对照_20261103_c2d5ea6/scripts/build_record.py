"""Standalone Chinese work record, generated only after paid run has stopped."""
import json
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
ROOT=Path(__file__).resolve().parents[1]
dta=json.loads((ROOT/'reports/analysis.json').read_text(encoding='utf-8'))
assert dta['complete'].get('stop_reason')!='RUNNING'
doc=Document();section=doc.sections[0]
section.page_width=Inches(8.5);section.page_height=Inches(11)
section.top_margin=Inches(.65);section.bottom_margin=Inches(.65);section.left_margin=section.right_margin=Inches(.7)
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2']:
    style=doc.styles[name];style.font.name='Microsoft YaHei';style._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Microsoft YaHei');style.font.color.rgb=RGBColor.from_string('111827')
    style.font.size=Pt(10.5 if name=='Normal' else 21 if name=='Title' else 14 if name=='Heading 1' else 11)
doc.styles['Normal'].paragraph_format.space_after=Pt(6)
doc.styles['Normal'].paragraph_format.line_spacing=1.16
def p(text):doc.add_paragraph(text)
def h(text,newpage=False):
    paragraph=doc.add_heading(text,1)
    if newpage:paragraph.paragraph_format.page_break_before=True
def num(v,places=3):return '未执行' if v is None else f'{v:.{places}f}'
def pct(v):return '未执行' if v is None else str((Decimal(str(v))*100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))+'%'
def table(headers,rows):
    t=doc.add_table(rows=1,cols=len(headers));t.autofit=True
    for c,text in zip(t.rows[0].cells,headers):c.text=str(text)
    for values in rows:
        for c,text in zip(t.add_row().cells,values):c.text=str(text)
    for index,row in enumerate(t.rows):
        for c in row.cells:
            tc=c._tc.get_or_add_tcPr();fill=OxmlElement('w:shd');fill.set(qn('w:fill'),'233B53' if index==0 else 'F1F5F9' if index%2 else 'FFFFFF');tc.append(fill)
            for para in c.paragraphs:
                para.paragraph_format.space_after=Pt(3);para.paragraph_format.line_spacing=1.02
                for r in para.runs:r.font.size=Pt(9);r.font.bold=index==0;r.font.color.rgb=RGBColor.from_string('FFFFFF' if index==0 else '111827')
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t
main=dta['summaries']['主功能集'];off=main['off'];on=main['assist'];pair=dta['paired']['主功能集'];special=dta['summaries']['Jev专项']
diagnostics=json.loads((ROOT/'reports/diagnostics.json').read_text(encoding='utf-8'))
doc.add_paragraph('Jev开关对照测试工作记录','Title')
doc.add_paragraph('Garin cyber  2026年11月3日开始  AI功能测试交接','Subtitle')
p(f"我在同一版源码c2d5ea6上重新运行Jev关闭和开启两组，验证当前AI与DeepSeek组合的效果。主功能集关闭组自动断言匹配率为{pct(off['pass_rate'])}，开启组为{pct(on['pass_rate'])}；平均整题耗时分别为{num(off['question_seconds']['mean'])}秒和{num(on['question_seconds']['mean'])}秒。判断是否保留Jev，需要同时看改善、退步、额外调用和超时。")
p('本轮使用当前P8.7真实AI入口及真实模型API，业务数据是合成测试资料。没有连接正式业务服务、真实用户数据库或MuMu。自动断言尚待人工复核，我没有代替团队签字。')
if on['question_seconds']['mean']>off['question_seconds']['mean'] and abs(on['pass_rate']-off['pass_rate'])<.03:
    p('本轮没有证明开启Jev能带来综合收益。当前建议先保持默认关闭，由AI负责人优化接入策略后另开对照，优先确认快捷路由能否真正生效。此结论只针对当前接法和这套中文用例。')
h('主要指标')
table(['主功能集指标','Jev关闭','Jev开启'],[
['已执行有效题次',off['questions'],on['questions']],['PASS 与 FAIL',f"{off['pass']} / {off['fail']}",f"{on['pass']} / {on['fail']}"],['严格自动匹配率',pct(off['pass_rate']),pct(on['pass_rate'])],['平均整题秒',num(off['question_seconds']['mean']),num(on['question_seconds']['mean'])],['整题P95秒',num(off['question_seconds']['p95']),num(on['question_seconds']['p95'])],['平均单次HTTP秒',num(off['api_seconds']['mean']),num(on['api_seconds']['mean'])],['平均每题API次数',num(off['mean_calls']),num(on['mean_calls'])],['DeepSeek HTTP次数',off['deepseek_calls'],on['deepseek_calls']],['Jev HTTP次数',off['jev_calls'],on['jev_calls']],['平均每题保守预算元',num(off['mean_conservative_cny_per_question'],6),num(on['mean_conservative_cny_per_question'],6)],['平均每次API保守预算元',num(off['mean_conservative_cny_per_api'],6),num(on['mean_conservative_cny_per_api'],6)],['用量未知请求',off['unknown_calls'],on['unknown_calls']]])
p(f"主功能配对中，开启后由FAIL变PASS共{pair['improved']}题次，PASS变FAIL共{pair['regressed']}题次；两边都失败共{pair['both_fail']}题次。后者是共同问题，不能直接归因Jev。置信区间按完整场景分组计算，重复运行不当成新用户样本。")
p('通过率差异的描述性95%区间约为负2.10至正4.34个百分点，仍包含没有提升的可能。')
p(f"四轮任务全部通过：关闭{off['passed_four_turn_tasks']}/{off['complete_four_turn_tasks']}，开启{on['passed_four_turn_tasks']}/{on['complete_four_turn_tasks']}。仅一轮答对不能代替整段任务完成。")

h('按功能查看两组差异',True)
rows=[]
for g in dict.fromkeys(x['group'] for x in dta['groups']):
    a=next(x for x in dta['groups'] if x['group']==g and x['mode']=='off');b=next(x for x in dta['groups'] if x['group']==g and x['mode']=='assist')
    rows.append([g,pct(a['pass_rate']),pct(b['pass_rate']),num(a['question_seconds']['mean']),num(b['question_seconds']['mean'])])
table(['功能','关闭匹配率','开启匹配率','关闭平均秒','开启平均秒'],rows)
p('主功能集保留上轮128条单轮和32个四轮场景，合计256题次每遍。新增32条Jev专项，覆盖无引用简单查询、多件同名、对象不存在、否定计划、改口与多操作、引用场景和零调用路径。专项单列，不能混入主功能集使总体成绩看起来更好。')
first=dta['repeat_summaries']['1']['主功能集'];second=dta['repeat_summaries']['2']['主功能集']
p(f"分遍统计：第一遍关闭{first['off']['pass']}/{first['off']['questions']}、开启{first['assist']['pass']}/{first['assist']['questions']}；第二遍关闭{second['off']['pass']}/{second['off']['questions']}、开启{second['assist']['pass']}/{second['assist']['questions']}。两遍均完整执行。")
p(f"已完成两遍的{diagnostics['fully_repeated_case_count']}个问题中，{diagnostics['variable_case_count']}个在某种模式下出现遍间波动；稳定改善{len(diagnostics['stable_improvement_ids'])}个，稳定退步{len(diagnostics['stable_regression_ids'])}个。")
p(f"开启组Jev路径分布：{json.dumps(on['jev_status'],ensure_ascii=False)}。回退原因以Excel和原始trace为准。当前快捷查询仅适用于很窄的表达和前提；有任务、引用或多操作时经常回到原流程。")
p('本轮主功能和专项均没有快捷查询成功记录。专项JEV 01“牛奶还有多少”虽被识别为库存查询，但第一遍澄清节点置信度0.4、所选概率0.6，低于源码0.8和0.9门槛，仍回到DeepSeek。阈值未调整，这反映的是当前接入策略的效果。')
p('Jev一次HTTP可以返回多个判断节点，仍只算一次API。总调用同时统计两家，不能只看DeepSeek次数。')

h('失败与极端值',True)
p('所有首次输出、失败请求和极端耗时都保留。以下只是需要定位的例子，同一题多遍失败不等于多个独立程序缺陷。')
for label,value in [('疑似新增退步',-1),('疑似改善',1)]:
    doc.add_heading(label,2)
    examples=[x for x in dta['pairs'] if x['accuracy_delta']==value][:3]
    if not examples:p('本轮有效配对中未出现。')
    for e in examples:
        p(f"{e['id']} 第{e['repeat']}遍：{e['text']}。关闭{e['off']['status']}，开启{e['assist']['status']}；未满足断言为"+'、'.join((e['assist'] if value<0 else e['off'])['failed_checks'])+'。')
doc.add_heading('最慢问题',2)
for mode in ['off','assist']:
    x=next((e for e in dta['extremes'] if e['mode']==mode and e['metric']=='seconds'),None)
    if x:p(f"{mode}：{x['id']} 第{x['repeat']}遍，{x['value']:.3f}秒。{x['explanation']}。")
p('极端值解释依据实际trace、API分段和停止原因。日志只能证明发生了哪些调用和回退，无法准确拆出供应商排队与网络各占多少。费用极端值优先核对未知用量预留，不能把较大预留当成实际高额扣费。')
p('样本标注争议、状态或错误码契约差异单列REVIEW建议，不修改正确预期来通过。正式成绩仍按冻结断言列PASS或FAIL，待人工决定是否属于实际业务缺陷。')

h('费用与证据交接',True)
complete=dta['complete'];book=complete.get('budget_after') or {}
p(f"本轮最初预算10元，原累计20元保护在998题次时先触发。11月4日用户授权以完成实验为先；续跑保留原账本及阻断记录。最终本轮保守占用{float(book.get('charged_or_reserved_cny',0)):.6f}元，包含小批量检查，并非平台实扣。")
p(f"正式有效执行{dta['formal_questions']}题次、实际{dta['formal_apis']}次HTTP；其中{dta['unexecuted']}项未执行、{dta['unpaired_executions']}项未形成有效配对。原预算阻断的{len(dta.get('superseded_budget_blocked_attempts',[]))}题次另外保留首次输出与费用，不当成模型失败。续跑没有重试任何已完成PASS或FAIL。")
p(f"正式批次已知用量估算：关闭组DeepSeek {off['known_cny']:.8f}元；开启组DeepSeek {on['known_cny']:.8f}元与Jev {on['known_usd']:.8f}美元。这是主功能集已知部分，未知请求尚未计入估算，不是平台实扣。完整专项、检查支出和预算见Excel及账本。")
p('Jev美元费用保持原币列出。每1美元按8元只是保守预算折算参数，不宣称是当日结算汇率。未知用量保留最大请求预留，不记为零；平台账单尚未人工核对。模型价格已于2026年11月3日核对官方文档。')
doc.add_heading('测试与复现',2)
p('固定源码、依赖、提示词、用例和适配器哈希。通过真实create_app工厂设off或assist，核对health及实际trace。每个单轮或多轮场景重新建立相同状态，交错开关顺序，第二遍反转；并发1，不添加自动重试，也不调整生产超时、提示词和模型参数。')
p('离线原生测试1277通过、2跳过，适配器13项通过。模拟预检576题次不计模型成绩。Windows隔离及导入适配的首次失败与修正日志保留。')
p('历史引用夹具在付费前修正签发时间，仍保持15分钟有效期。小批量3次Jev超时未重跑消除，原结果保留；另附validated.json区分产品回退和测量工具故障。')
doc.add_heading('给团队的下一步',2)
p('AI负责人先按“关闭通过、开启失败”的编号复核Jev判断及保护路径，再看无引用简单查询是否真正快捷路由、2秒超时的比例和回退增量。共同失败沿原功能问题处理。若修改阈值、超时或提示词，应另开批次，复用冻结用例同时重跑两组。')
p('Excel与原始证据均保存在本轮目录，完整路径见README。交接副本在tests/交接文件夹；请求、输出、JUnit、文件哈希及运行脚本均保留。')
p('价格来源 https://docs.typesafe.ai/models 及 https://api-docs.deepseek.com/zh-cn/quick_start/pricing/。本轮未修改队友源码或正式服务开关，人工复核继续待确认。')
for element in [*doc._element.xpath('.//w:pBdr'),*doc.styles.element.xpath('.//w:pBdr')]:element.getparent().remove(element)
out=ROOT/'reports/Garin_Jev开关对照测试工作记录.docx';doc.save(out);print(out)
