"""Build the standalone Garin work record using the bundled document runtime."""
import json,pathlib
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
ROOT=pathlib.Path(__file__).resolve().parents[1]
def load(n):return json.loads((ROOT/'reports'/n).read_text(encoding='utf-8'))
s=load('summary.json');cats=load('功能版本覆盖.json');u=load('重复性与不确定性.json');ext=load('extremes.json')['records']
d=Document();sec=d.sections[0];sec.page_width=Cm(21);sec.page_height=Cm(29.7);sec.top_margin=Cm(1.8);sec.bottom_margin=Cm(1.8);sec.left_margin=Cm(2);sec.right_margin=Cm(2)
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2']:
 st=d.styles[name];st.font.name='Microsoft YaHei';st.font.color.rgb=RGBColor(0,0,0);st._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'微软雅黑')
st=d.styles['Normal'];st.font.size=Pt(10.5);st.paragraph_format.space_after=Pt(6);st.paragraph_format.line_spacing=1.15
d.styles['Title'].font.size=Pt(23);d.styles['Title'].paragraph_format.space_after=Pt(10)
d.styles['Heading 1'].font.size=Pt(16);d.styles['Heading 1'].paragraph_format.space_before=Pt(8);d.styles['Heading 1'].paragraph_format.space_after=Pt(8)
d.styles['Heading 2'].font.size=Pt(12);d.styles['Heading 2'].paragraph_format.space_before=Pt(8)
for border in list(d.styles.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
d.styles['Subtitle'].font.italic=False
d.core_properties.title='AI各功能专项测试工作记录';d.core_properties.author='Garin-cyber';d.core_properties.subject='真实模型基线与失败证据交接';d.core_properties.comments='人工复核未签字。'
def p(text,style=None):return d.add_paragraph(text,style)
def h(text):d.add_heading(text,1)
def table(headers,rows,widths):
 t=d.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
 for i,w in enumerate(widths):t.columns[i].width=Cm(w)
 for i,x in enumerate(headers):t.rows[0].cells[i].text=x
 for row in rows:
  for c,x in zip(t.add_row().cells,row):c.text=str(x)
 for j,row in enumerate(t.rows):
  for i,c in enumerate(row.cells):
   c.width=Cm(widths[i]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
   tcPr=c._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
   for side in ['top','left','bottom','right']:
    el=OxmlElement('w:'+side);el.set(qn('w:w'),'40' if len(headers)==5 and side in {'top','bottom'} else '75');el.set(qn('w:type'),'dxa');mar.append(el)
   tcPr.append(mar);b=OxmlElement('w:tcBorders')
   for side in ['top','left','bottom','right']:
    el=OxmlElement('w:'+side);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');b.append(el)
   tcPr.append(b);shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'183B56' if j==0 else 'F1F5F8' if j%2 else 'FFFFFF');tcPr.append(shade)
   for para in c.paragraphs:
    para.paragraph_format.space_after=Pt(1);para.paragraph_format.line_spacing=1.05
    if i>0:para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for r in para.runs:r.font.size=Pt(9.5);r.font.bold=j==0;r.font.color.rgb=RGBColor(255,255,255) if j==0 else RGBColor(0,0,0)
  trPr=row._tr.get_or_add_trPr();cant=OxmlElement('w:cantSplit');trPr.append(cant)
 repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
 d.add_paragraph().paragraph_format.space_after=Pt(1)
 return t

d.add_paragraph('AI各功能专项测试工作记录','Title')
p('Garin-cyber  |  2026年10月31日  |  团队功能测试交接','Subtitle')
p('本轮按docs/versions中各阶段负责的功能检查当前源码，分别验证功能模块与P8.6当前入口。模块回归通过不代表真实模型或App全链路通过。有效真实模型执行512题次，399通过、113未满足严格断言；仍有问题需要团队处理，不能宣布全部AI功能验收完成。')
h('本轮结果')
table(['指标','实际结果'],[
 ['固定源码','733d339  当前入口P8.6  Jev关闭'],['功能范围','20个阶段建立结果页  16组业务能力真实调用'],['用例规模','128条单轮加32个四轮场景  两遍共512题次'],['严格自动通过率','399除以512  77.93%  标签待人工复核'],['四轮任务全部通过','20除以64次场景执行  31.25%'],['正式实际API','557次  含小批量共564次'],['每题平均耗时','1.292秒  P95为2.371秒'],['单次API平均耗时','1.030秒'],['每题平均API','1.088次  含合法零调用'],['每题平均费用估算','0.00096197元'],['单次API平均费用估算','0.00088425元'],['正式用量估算','0.49252790元  未核对平台账单'],['本轮保守记账','3.383262元  新额度最多10元']], [7,10])
p('统计采用472条有效初始执行，加40条修正夹具后单独补测。原始正式批次512条记录及40条工具错误全部保留；输入文字和预期未改。具体时间修正和统计选择见第4页。')
p('原始AI源码回归1140通过、1跳过；Garin独立功能检查29通过，本地接口和数据库核对6通过。各组有交叉，不能把这些数量相加当成独立真人样本或统一正确率。')

d.add_page_break();h('按功能归属查看结果')
p('模块列来自本轮实际重跑的AI源码测试，可能被多个阶段引用。入口列为P8.6真实DeepSeek两遍成绩；配置维护和单位专项以离线检查为主，不强行增加模型调用。')
table(['阶段','主要功能','模块通过','入口通过','入口未通过'],[(c['stage'],c['title'],c['native_counts'].get('PASS',0),c['live_counts'].get('PASS','不单列'),c['live_counts'].get('FAIL','不单列')) for c in cats],[1.6,6.2,2.6,3.3,3.3])
p('P9 Jev未接入，本轮不调用；V1.5未开发能力只列待办。阶段编号用于说明功能归属，没有逐个安装历史App，也没有把开发记录中的旧成绩登记成本轮实测。')
p('当前每条库存代表一件实物，重量容量是规格。早期半盒扣减只在旧模块兼容测试中保留；当前入口正确拒绝半件，不视作漏实现。')

d.add_page_break();h('需要团队优先处理的问题')
p('113次严格自动失败涉及77个用例编号。下表是定位线索，根因仍待人工确认。')
table(['分类','题次'],[['程序或模型理解待定位',71],['模型结构输出不合法',16],['规划入口或理解待定位',14],['循环重复或无进展',5],['降级状态契约待复核',4],['具体错误码契约待复核',3]], [12,5])
d.add_heading('核心例子',2)
p('整件操作：“请登记这件牛奶整件消耗”仍可能要求数量或比例；“用完了”也出现继续追问。应核对原文、amount_mode和逐件投影，不能只看生成字段的单元测试。')
p('多轮任务：“把这件牛奶移到书房”有时仍追问目标位置；更正草稿可能返回INVALID_DRAFT_EDIT；询问实际位置并提到“尚未确认”时，有时只回答草稿待确认，没有读取所问的位置。')
p('规划与记忆：商品合计有时仅返回两条单件事实，未形成要求的商品汇总；回到旧话题、对象切换和事实刷新也存在失败。已有消费小计正确但因其他资料不足返回data_unavailable的4条，只是严格状态差异，不能称统计数值算错。')
d.add_heading('本地后端问题另列',2)
p('源码原始结果为166通过、12失败、415个准备错误、45跳过。415个准备错误主要来自旧夹具仍插入数量5的单行批次，业务断言并未执行。4个SQLite迁移失败是约束缺名，不能推断PostgreSQL失败。旧小数数量、终态行清理和文档契约差异分别记录。')
p('独立逐件专项6项通过，核对了任务草稿落库但库存不变、请求恢复不再调模型、确认重放不重复写入、家庭隔离、终态行删除后的事件回执，以及本地后端规划DTO到AI适配器的总量与未知事实。它们不能替代所有后端测试。')
p('文档仍要求unit必填，源码已允许省略并默认“件”，需同步。P4旧84次问题中81次满足原断言，另3条保留FAIL；旧包37次FAIL按入口分列，不当作37个新缺陷。')

d.add_page_break();h('证据口径与接续工作')
d.add_heading('测试夹具错误已经单独修正',2)
p('原始批次中40题次的旧话题引用时间晚于历史片段时间，程序在调用模型前拒绝了输入。这是Garin测试夹具问题。修正时仅把引用签发时间调整到对应片段时刻，仍保留15分钟原有效期，未改输入、库存事实或预期答案。单独补测40题次得到23通过、17失败；原始40条工具FAIL没有删除，也未混作AI质量问题。')
d.add_heading('性能和费用如何理解',2)
p('本轮52题次零API、363题次一次、97题次两次，真实样本没有出现三次以上。超过两次的循环能力由离线受控四步链路验证；不能声称本轮真实模型已经覆盖所有循环深度。总耗时包括本地处理和记录开销，排除App网络与业务数据库。')
mx=next(e for e in ext if e['metric']=='整题耗时' and e['kind']=='最大值')
p(f"最慢题为{mx['execution_id']}，{mx['seconds']:.3f}秒、{mx['api_calls']}次API。{mx['observed_explanation']}。极端值不删除，Top5和证据位置完整保留；客户端日志不能确定供应商排队或公网延迟各占多少。")
p('两遍均通过的输入179个，业务结果一致172个。按16个功能组整体重采样的描述性95%区间为71.29%至84.18%，不能当成真实用户总体正确率。实际HTTP均返回200，也不能据此认定业务回答正确。')
d.add_heading('交付与下一步',2)
p('完整文件在tests/version测试/功能专项_20261031_733d339，按stages查看各阶段。Excel提供功能覆盖、问题清单、逐题均值、实际API及离线明细；JSONL和JUnit保留全部输出及证据索引。给队友阅读的副本在tests/交接文件夹/2026-10-31_AI各功能专项测试。')
p('先由AI负责人处理整件操作、目标位置和草稿更正、商品统计与旧话题续接，再统一状态和错误码契约。后端负责人处理旧夹具与文档同步，并在独立PostgreSQL环境补验迁移、事务和并发。Garin以后按原问题编号记录新证据。')
p('未连接正式服务或真实用户数据库，未修改队友源码。旧8.6的65次失败仅关联同类功能覆盖，未按原文和原前提单独重放，因此原FAIL保留。Jev、App、人工规则审核及人工自然度验收仍待完成，未代签。')
p('价格来源：DeepSeek官方定价页，2026年10月31日复核。https://api-docs.deepseek.com/zh-cn/quick_start/pricing/。本轮保守记账含小批量和补测，平台实扣尚未核对。')
out=ROOT/'reports/Garin_AI各功能专项测试工作记录.docx';d.save(out);print(out)

