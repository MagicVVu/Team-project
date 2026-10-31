"""Package already-completed results. Contains no paid execution."""
import hashlib,json,os,pathlib,re,shutil,zipfile
from lxml import etree
ROOT=pathlib.Path(__file__).resolve().parents[1];REPO=ROOT.parents[2]
HANDOFF=REPO/'tests/交接文件夹/2026-10-31_P8.6基线测试'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 HANDOFF.mkdir(parents=True,exist_ok=True)
 copies=[]
 for name in ['Garin_P8.6基线测试工作记录.docx','P8.6 DeepSeek基线总览.xlsx','失败交接清单.md','测试方法与分功能结果.md','测试结果与极端值.md']:
  src=ROOT/'reports'/name;dest=HANDOFF/name;shutil.copy2(src,dest);assert digest(src)==digest(dest);copies.append({'name':name,'sha256':digest(dest)})
 dump(HANDOFF/'交接文件校验.json',copies)
 (HANDOFF/'README.md').write_text('''# P8.6 DeepSeek基线测试交接

Garin-cyber，2026年10月31日。固定源码733d339，本地只读合成环境，真实DeepSeek，Jev关闭。

## 先读结果

- [Word工作记录](Garin_P8.6基线测试工作记录.docx)：4页，结果、问题、极端值和接续工作。
- [Excel总览](P8.6%20DeepSeek基线总览.xlsx)：总览、每题均值、极端值、逐题记录、API明细、方法说明。可筛选FAIL和题目编号。
- [失败交接清单](失败交接清单.md)：65次失败逐项预期、实际、证据行号，根因待负责人复核。
- [测试方法和分功能结果](测试方法与分功能结果.md)、[极端值详细解释](测试结果与极端值.md)。

正式执行719题次：654 PASS、65 FAIL，严格自动通过率90.96%。另1题次发出HTTP前被预算拦截，保留BLOCKED；原计划720题次。240个输入，239个完成三遍，最后一个仅两遍，均值按实际遍数计算。人工标注及自然度复核未签字。

| 指标 | 数值 |
|---|---:|
| 正式实际API请求 | 766次 |
| 每题平均API | 1.065次 |
| 每题平均耗时 | 1.279秒 |
| 每题P95耗时 | 2.394秒 |
| 每题最大耗时 | 4.177秒 |
| 单次API平均耗时 | 1.041秒 |
| 每题平均用量费用 | 0.00103989元 |
| 单次API平均用量费用 | 0.00097609元 |
| 正式用量估算费用 | 0.74768412元 |
| 含小批量保守记账 | 4.957662元，限额5元 |

用量估算不是平台实扣账单。保守记账采用更高价格预留，已停止全部真实调用，没有清零旧账本。每题均值包含零调用；单次API均值仅包含真实出站。

## 请AI负责人先处理

1. 多件未选择仍生成草稿、引用过期仍继续使用：核对对象选择与引用有效性。
2. 唯一对象的整件消耗和丢弃18次失败：核对模型amount_mode、字段落地及逐件规则。
3. 部分重复计划已返回事实但状态stopped；错误码或降级状态不同需确认契约。保留原FAIL，不改预期来凑成绩。
4. 规划资料接口本轮故意不可用，用于缺数据降级；不能用该组宣布完整统计预测已通过，也不能反推生产服务必然未实现。

失败分类是排查线索，不等于已确定单一组件责任。没有已确认的样本标注错误；人工复核继续pending。

## 证据和边界

完整记录在 [本轮测试目录](../../8.6基线测试/P8.6_DeepSeek基线_20261031_733d339/README.md)。runs保留脱敏请求、原始响应、用量、输入与输出；reports保留逐题和逐请求JSONL。所有证据仅虚拟家庭与合成库存，未连接业务服务或真实数据库，没有改队友源码。

本轮为当前AI方案基线，不是纯模型裸问答，不登记App、后端事务或真实数据库联合验收通过。旧批次数量模型与当前逐件库存不同，不能直接用旧通过率差证明升级效果。

后续Jev比较使用同样冻结数据、评分和状态；若本集已用于调优，另备未见评估集。新的付费复测另立批次和预算，不能覆盖本轮证据。
''',encoding='utf-8')
 index=REPO/'tests/交接文件夹/README.md';text=index.read_text(encoding='utf-8');link='[2026年10月31日 P8.6 DeepSeek基线](2026-10-31_P8.6基线测试/README.md)'
 if link not in text:
  text=text.replace('最新交接：[2026年10月16日 V1分阶段测试 第一批](2026-10-16_V1分阶段测试_第一批/README.md)。','最新交接：'+link+'。\n\n历史首批：[2026年10月16日 V1分阶段测试 第一批](2026-10-16_V1分阶段测试_第一批/README.md)。')
  text+='\n- '+link+'：719题次实测，65次失败保留，含逐题费用、耗时、调用次数与极端值。\n';index.write_text(text,encoding='utf-8')
 readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
 if '## 最终状态' not in text:
  text=text.replace('## 阅读顺序','## 最终状态\n\n正式实际执行719题次，654 PASS、65 FAIL；另1条预算BLOCKED，未发出HTTP。240个输入中239个完成三遍，最后一个仅两遍。正式766次HTTP，含小批量共773次；本轮保守记账4.957662元，5元保护已停止调用。不要再次运行smoke或formal命令。\n\n人工复核待完成。Word工作记录和完整失败清单见reports；交接副本见tests/交接文件夹/2026-10-31_P8.6基线测试。\n\n## 阅读顺序')
  readme.write_text(text,encoding='utf-8')
 # Verify complete final saved Office files and public text without traversing junctions.
 bad=[];count=0;files=[];ignored={'.snapshot','.qa','.runtime','node_modules','__pycache__','.pytest_cache','.git'}
 keypat=re.compile(rb'(?:sk-[A-Za-z0-9_-]{24,}|Bearer\s+[A-Za-z0-9_-]{30,})')
 for base in [ROOT,HANDOFF]:
  for directory,dirs,names in os.walk(base,followlinks=False):
   dirs[:]=[n for n in dirs if n not in ignored and not pathlib.Path(directory,n).is_symlink()]
   for name in names:
    f=pathlib.Path(directory,name)
    if name in {'final-files.json','package-validation.json'}:continue
    raw=f.read_bytes();count+=1
    if f.suffix in {'.docx','.xlsx'}:
     with zipfile.ZipFile(f) as z:
      assert z.testzip() is None
      for n in z.namelist():
       if n.endswith('.xml') and keypat.search(z.read(n)):bad.append(str(f.relative_to(REPO)))
    elif keypat.search(raw):bad.append(str(f.relative_to(REPO)))
    files.append({'path':str(f.relative_to(REPO)).replace('\\','/'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 assert not bad,'Credential-like strings found; do not publish'
 dump(ROOT/'evidence/final-files.json',files)
 with zipfile.ZipFile(ROOT/'reports/P8.6 DeepSeek基线总览.xlsx') as z:
  chart_count=sum('/charts/' in n and n.endswith('.xml') for n in z.namelist())
  assert chart_count==1
 with zipfile.ZipFile(ROOT/'reports/Garin_P8.6基线测试工作记录.docx') as z:
  style=etree.fromstring(z.read('word/styles.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'};assert not style.findall('.//w:pBdr',ns)
 manifest=json.loads((ROOT/'datasets/manifest.json').read_text(encoding='utf-8'))
 assert all(digest(ROOT/'datasets'/f'{name}.jsonl')==v['sha256'] for name,v in manifest['sets'].items())
 dump(ROOT/'evidence/package-validation.json',{'public_files_checked':count,'credential_pattern_matches':0,'handoff_copies_hash_match':True,'frozen_dataset_hashes_match':True,'workbook_chart_count':chart_count,'word_rendered_pages':4,'word_all_pages_visually_checked':True,'workbook_all_sheets_visually_checked':True,'word_renderer_fallback':'Packaged renderer lacks bundled LibreOffice; retained failure log, used installed Word hidden read-only PDF export and bundled Poppler.','source_files_untouched':'see final-integrity-and-budget.json'})
 print(json.dumps({'handoff':str(HANDOFF),'copied':len(copies),'public_files_checked':count,'credential_matches':0},ensure_ascii=False))
if __name__=='__main__':main()
