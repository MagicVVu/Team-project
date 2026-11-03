"""Publish only owned local handoff files and verify the completed artifacts."""
import json,os,pathlib,re,shutil,zipfile,hashlib,xml.etree.ElementTree as E
from prepare import ROUND,REPO,HEAD,write,sha
from stage_config import STAGES
HANDOFF=REPO/'tests/交接文件夹/2026-10-31_AI各功能专项测试'
def main():
 summary=json.loads((ROUND/'reports/summary.json').read_text(encoding='utf-8'));assert summary['live_finished']
 (ROUND/'.gitignore').write_text('.snapshot/\n.runtime/\n.qa/\nnode_modules/\n__pycache__/\n.pytest_cache/\n*.pyc\nruns/**/pytest-temp/\nruns/**/temp/\nruns/**/*.sqlite\nruns/**/*.sqlite-*\n',encoding='utf-8')
 requirements=[]
 coverage=json.loads((ROUND/'reports/功能版本覆盖.json').read_text(encoding='utf-8'))
 for c in coverage:
  for i,feature in enumerate(c['features'],1):requirements.append({'requirement_id':f"REQ-{c['stage']}-{i:02}",'stage':c['stage'],'feature':feature,'document':c['document'],'native_case_index':f"stages/{c['stage']}/result.json#native_nodes",'current_entry_case_index':f"stages/{c['stage']}/result.json#live_ids",'mapping_grain':'功能组与关联套件；不宣称每个边界都由每条用例验证','status':'已执行功能组检查，细项证据需按用例查看','human_review_status':'pending'})
 write(ROUND/'reports/需求与用例追溯.json',requirements)
 (ROUND.parent/'README.md').write_text('''# AI各功能专项测试

本目录由Garin-cyber维护，按docs/versions中的功能归属测试，与8.6性能费用基线分开。

- [2026年10月31日 源码733d339](功能专项_20261031_733d339/README.md)：模块回归、本地AI接口与数据库核对、真实DeepSeek功能专项。

以后源码更新另建批次，保留历史失败和原始证据。Jev对比、App和正式数据库验收另行记录。
''',encoding='utf-8')
 (ROUND/'README.md').write_text('''# AI各功能专项测试 2026年10月31日

固定源码733d339ee5bbb73635413902cdd0d07d43a6075a。按阶段负责的功能测试当前代码，当前入口P8.6，Jev关闭。全部真实调用已结束，本轮不再重跑付费命令。

## 先看哪些文件

1. [Excel功能总览](reports/AI各功能专项测试总览.xlsx)：总览、功能覆盖、问题清单、每题均值、逐题执行、API明细、离线明细、方法说明。
2. [Word工作记录](reports/Garin_AI各功能专项测试工作记录.docx)：4页，可直接给队友。
3. [结果总说明](reports/结果总说明.md)、[真实模型失败清单](reports/真实模型失败清单.md)。
4. [分阶段结果](stages)：P0至P8.6共20个阶段分别建页，P9和V1.5另列未接入/未开发边界。
5. [需求与用例追溯](reports/需求与用例追溯.json)：阶段文档、功能组和用例索引。源文档读取清单及哈希见evidence/documents-read.json。

## 这轮的结论

- 有效执行512题次，399 PASS、113严格自动FAIL，77.93%；人工标注和自然度复核待完成。113次失败涉及77个用例编号，不等于113个独立程序缺陷。
- 128个单轮用例加32个四轮场景，共256轮/遍，独立运行两遍。64次四轮场景执行中20次四轮全PASS；相关轮次和重复观测不当作独立真人样本。
- 正式557次实际API；小批量另7次，共564次。均为真实DeepSeek请求，全部HTTP 200不代表业务断言通过。
- 每题平均1.292秒、1.088次API、0.00096197元；单次API平均1.030秒、0.00088425元。费用是用量估算，平台账单未核对。
- 正式用量估算0.49252790元，本轮含小批量和补测的保守记账3.383262元，未超另设10元；旧账本不清零。
- AI源码1140通过、1跳过；Garin功能29通过，本地接口和数据库核对6通过。各组可能交叉，不能相加成统一正确率。
- 后端全量原始166 PASS、12 FAIL、415 ERROR、45 SKIP。旧夹具、SQLite迁移、当前契约和文档差异分别保留，不能宣布全部后端通过。

## 首轮工具问题与补测

原始正式批次512条记录是376 PASS、136 FAIL，其中40条因测试夹具旧话题引用时间晚于片段而在模型调用前被拒绝。原记录全部保留。

仅修正夹具引用的时间与15分钟原有效期，冻结文字和预期不变；另开archive-recheck批次补测40题次，23 PASS、17 FAIL。主表采用472条有效初始执行加40条补测，不把原40条工具FAIL算成AI质量FAIL。详见reports/测试工具问题与补测.json和原始工具失败40条.jsonl。

另外保留了AI首次收集时缺测试包、Garin接口首次缺日期/草稿名称等工具前提错误。未修改队友源码或原测试预期。

## 证据与隔离

- runs/：真实请求响应、输入上下文、计划、用量、原始JUnit、临时SQLite与数据库核对JSON。原始日志不覆盖。
- reports/：逐题、逐请求JSONL和分类；stages/：各阶段索引。
- evidence/：源码、配置模板、依赖、文档和数据哈希、费率依据、预算与文件校验。
- .snapshot/：必要源码、部署模板及旧测试包的隔离副本；.runtime、.qa和node_modules不提交Git。

仅真实DeepSeek允许外连，离线进程阻断外部连接。本地接口使用进程内HTTP和临时SQLite，确认前核对真实临时数据库没有库存变化；不连接真实用户数据库、正式服务或MuMu，不部署。

业务时钟固定2026-10-15 10:00上海，计费和HTTP用实际时钟。按官方缓存、时段和返回Token估算费用。当前single-object-1逐件库存，旧半盒扣减只在旧模块回归验证，不套到当前入口。

## 复现

先按datasets/manifest.json和evidence/source.json检查哈希。scripts/offline.py在冻结副本中运行模块、本地接口和既有评测器。AI与后端使用两套独立依赖，参考runs下各环境清单。

scripts/Run.ps1只在子进程加载仓库外当前用户DPAPI密钥；formal和archive-recheck拒绝覆盖已启动批次。**本轮已封存，不再次运行smoke、formal或archive-recheck获取新成绩；新付费复测必须另建批次和预算。**

旧8.6的65次FAIL只关联本轮同类功能，未按原文和原前提重放，继续保留FAIL。App、PG并发、生产联调、规则专业审核和人工自然度未验收。
''',encoding='utf-8')
 HANDOFF.mkdir(parents=True,exist_ok=True);copies=[]
 for name in ['AI各功能专项测试总览.xlsx','Garin_AI各功能专项测试工作记录.docx','结果总说明.md','真实模型失败清单.md','测试结果与极端值.md','功能版本覆盖.json','离线问题清单.json','测试工具问题与补测.json','P4历史84项对照.json','P4旧包37次FAIL.json']:
  src=ROUND/'reports'/name;target=HANDOFF/name;shutil.copy2(src,target);assert sha(src)==sha(target);copies.append({'name':name,'sha256':sha(target)})
 write(HANDOFF/'交接文件校验.json',copies)
 (HANDOFF/'README.md').write_text('''# AI各功能专项测试交接

Garin-cyber，2026年10月31日。源码733d339，当前P8.6入口；功能模块与真实DeepSeek分别记录。没有修改队友源码，没有连接正式用户数据库。

先读[Word工作记录](Garin_AI各功能专项测试工作记录.docx)和[Excel功能总览](AI各功能专项测试总览.xlsx)。再看[真实模型失败清单](真实模型失败清单.md)、[结果总说明](结果总说明.md)与[极端值解释](测试结果与极端值.md)。

512题次有效执行，399通过、113严格自动失败，77.93%；失败含状态/错误码契约差异，不能全部叫程序缺陷。原40条工具夹具错误保留且单独补测，不混为AI问题。人工复核待确认。

主要需AI负责人继续处理：整件消耗仍追问数量、移动目标和草稿更正、实际位置查询被当成状态解释、商品统计读取和旧话题续接，以及模型结构输出和循环终止状态。

后端源码原始166通过、12失败、415准备错误、45跳过；准备错误主要为旧五件批次夹具与当前逐件模型冲突。另有SQLite迁移约束缺名、终态清理契约及unit可省略的文档不同步。新的本地接口与数据库核对6项通过，不能替代整个后端验收。

本轮正式用量估算0.49252790元，含小批量及补测的保守记账3.383262元，在本轮10元上限内，平台账单未核对。所有真实调用已结束。

完整脚本、20阶段结果页、P9/V1.5边界页及原始证据见[version测试本轮目录](../../version测试/功能专项_20261031_733d339/README.md)。各问题可按执行编号追到runs原始行；修复后另建复测批次，旧FAIL不删除。App、真实PG并发、生产链路和人工规则审核待验收。
''',encoding='utf-8')
 index=REPO/'tests/交接文件夹/README.md';text=index.read_text(encoding='utf-8');link='[2026年10月31日 AI各功能专项测试](2026-10-31_AI各功能专项测试/README.md)'
 if link not in text:
  text=re.sub(r'最新交接：[^\n]*', '最新交接：'+link+'。',text,count=1);text+='\n- '+link+'：按功能分别报告，包含本地接口与真实模型问题。\n';index.write_text(text,encoding='utf-8')
 import openpyxl
 book=ROUND/'reports/AI各功能专项测试总览.xlsx';cached=openpyxl.load_workbook(book,data_only=True);ws=cached['总览']
 assert ws['B8'].value==512 and ws['B9'].value==399 and ws['B10'].value==113 and ws['B12'].value==557
 assert abs(ws['B18'].value-.4925279)<1e-9 and abs(ws['B24'].value-3.383262)<1e-9
 errors=[]
 for sheet in cached:
  for row in sheet:
   for cell in row:
    if cell.data_type=='e':errors.append(f'{sheet.title}!{cell.coordinate}')
 assert not errors
 with zipfile.ZipFile(book) as z:assert z.testzip() is None;charts=sum('/charts/' in n and n.endswith('.xml') for n in z.namelist());assert charts==1
 manifest=json.loads((ROUND/'datasets/manifest.json').read_text(encoding='utf-8'));assert all(sha(ROUND/'datasets'/f'{n}.jsonl')==v['sha256'] for n,v in manifest['sets'].items())
 public=[];sensitive=[];ignored={'.snapshot','.runtime','.qa','node_modules','__pycache__','.pytest_cache','.git','pytest-temp','temp'};pattern=re.compile(rb'(?:sk-[A-Za-z0-9_-]{24,}|Bearer\s+[A-Za-z0-9_-]{30,})')
 for base in [ROUND,HANDOFF]:
  for directory,dirs,names in os.walk(base,followlinks=False):
   dirs[:]=[n for n in dirs if n not in ignored and not pathlib.Path(directory,n).is_symlink()]
   for n in names:
    if n in {'final-files.json','package-validation.json'} or '.sqlite' in n:continue
    p=pathlib.Path(directory,n);raw=p.read_bytes()
    if p.suffix in {'.xlsx','.docx'}:
     with zipfile.ZipFile(p) as z:
      if z.testzip() is not None:raise RuntimeError('Invalid Office archive')
      if any(pattern.search(z.read(q)) for q in z.namelist() if q.endswith('.xml')):sensitive.append(str(p.relative_to(REPO)))
    elif pattern.search(raw):sensitive.append(str(p.relative_to(REPO)))
    public.append({'path':p.relative_to(REPO).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 if sensitive:
  write(ROUND/'evidence/secret-scan-findings.json',{'paths':sensitive,'values_not_printed':True});raise RuntimeError('Credential-like content found; inspect privately before packaging')
 write(ROUND/'evidence/final-files.json',public)
 write(ROUND/'evidence/package-validation.json',{'saved_xlsx_cached_metrics_match':True,'xlsx_formula_errors':errors,'charts':charts,'word_pages':4,'all_word_pages_visually_reviewed':True,'all_workbook_sheets_visually_reviewed':True,'frozen_data_hashes_match':True,'handoff_hashes_match':True,'public_files_scanned':len(public),'credential_pattern_matches':0,'scope':'owned tests and handoff only','export_process_note':'Artifact export prints saved path then process exits1; actual saved archive, formula caches, chart and renders independently verified.','word_renderer_note':'Packaged LibreOffice absent; canonical failure log retained, hidden read-only Word PDF export plus bundled Poppler used.'})
 print(json.dumps({'handoff':str(HANDOFF),'public_files':len(public),'copied':len(copies),'xlsx_verified':True},ensure_ascii=False))
if __name__=='__main__':main()
