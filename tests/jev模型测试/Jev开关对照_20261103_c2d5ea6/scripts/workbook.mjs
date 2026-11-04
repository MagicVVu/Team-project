import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const d=JSON.parse(await fs.readFile(path.join(root,'reports/analysis.json'),'utf8'));
if(!d.complete || d.complete.stop_reason==='RUNNING')throw new Error('Formal run is still active; do not export final results');
const wb=Workbook.create(),names=['总览','调用与费用','功能比较','每题平均','逐题对照','问题与极端值','API明细','方法说明'];
const sheets=Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26)}return s};
function setup(s,title,note,last='N'){
 s.showGridLines=false;s.getRange(`A1:${last}4`).format.font={name:'Arial',size:11,color:'#1E293B'};
 s.getRange('A2').values=[[title]];s.getRange('A2').format.font={size:17,bold:true,color:'#111827'};
 s.getRange('A4').values=[[note]];s.getRange('A4').format.font={size:10,color:'#536171'};s.getRange('A4').format.rowHeight=22;
}
function table(s,headers,values,widths,id,start=7){
 const last=col(headers.length),end=start+values.length;
 s.getRange(`A${start}:${last}${start}`).values=[headers];
 if(values.length)s.getRange(`A${start+1}:${last}${end}`).values=values;
 s.getRange(`A${start}:${last}${Math.max(end,start+1)}`).format={font:{name:'Arial',size:11,color:'#1E293B'},rowHeight:27,verticalAlignment:'center'};
 s.getRange(`A${start}:${last}${start}`).format={fill:'#233B53',font:{bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:42,horizontalAlignment:'center'};
 widths.forEach((w,i)=>s.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);
 if(values.length){s.tables.add(`A${start}:${last}${end}`,true,id).showFilterButton=true;s.freezePanes.freezeRows(start);s.freezePanes.freezeColumns(2);}
 return end;
}
const pair=sheets['逐题对照'];setup(pair,'同一道题的关闭与开启结果','一行是一题一遍。耗时差为开启减关闭，负数表示开启更快。','T');
const pend=table(pair,['编号','遍数','功能','输入','关闭结果','开启结果','关闭秒','开启秒','耗时差秒','关闭DeepSeek','开启DeepSeek','开启Jev','关闭保守元','开启保守折算元','关闭已知估算元','开启已知估算元','关闭未知调用','开启未知调用','关闭证据','开启证据'],d.pairs.map(p=>[p.id,p.repeat,p.group_id,p.text,p.off.status,p.assist.status,p.off.seconds,p.assist.seconds,null,p.off.deepseek_http_calls,p.assist.deepseek_http_calls,p.assist.jev_http_calls,p.off.conservative_cny,p.assist.conservative_cny,p.off.estimated_cny_at_budget_fx,p.assist.estimated_cny_at_budget_fx,p.off.unknown_calls,p.assist.unknown_calls,p.off.evidence,p.assist.evidence]),[25,8,15,62,13,13,14,14,16,17,17,14,20,23,22,22,16,16,65,65],'PairedQuestions');
pair.getRange(`I8:I${pend}`).formulas=d.pairs.map((p,i)=>[`=H${i+8}-G${i+8}`]);pair.getRange(`G8:I${pend}`).setNumberFormat('0.000');pair.getRange(`M8:P${pend}`).setNumberFormat('0.000000');pair.getRange(`D8:D${pend}`).format.wrapText=true;pair.getRange(`A8:T${pend}`).format.rowHeight=42;
for(const c of ['E','F'])pair.getRange(`${c}8:${c}${pend}`).conditionalFormats.add('containsText',{text:'FAIL',format:{fill:'#FDE8E8',font:{color:'#9B1C1C'}}});
const means=sheets['每题平均'];setup(means,'每道问题的两遍均值','均值只使用已执行有效题次；空白费用表示有未知用量。美元按8元作预算折算，不能当平台账单。','P');
const mend=table(means,['编号','功能','输入','关闭遍数','开启遍数','关闭通过','开启通过','关闭平均秒','开启平均秒','平均耗时差秒','关闭平均API','开启平均API','关闭平均保守元','开启平均保守折算元','关闭未知调用','开启未知调用'],d.averages.map(q=>[q.id,q.group,q.text,q.off.questions,q.assist.questions,q.off.pass,q.assist.pass,null,null,null,q.off.mean_calls,q.assist.mean_calls,q.off.questions?q.off.conservative_cny/q.off.questions:null,q.assist.questions?q.assist.conservative_cny/q.assist.questions:null,q.off.unknown_calls,q.assist.unknown_calls]),[25,14,62,15,15,15,15,19,19,21,19,19,23,27,18,18],'QuestionMeans');
const pr=c=>`'逐题对照'!$${c}$8:$${c}$${pend}`;
for(const [dest,src] of [['H','G'],['I','H']])means.getRange(`${dest}8:${dest}${mend}`).formulas=d.averages.map((q,i)=>[`=IF(COUNTIF(${pr('A')},A${i+8})=0,"",AVERAGEIF(${pr('A')},A${i+8},${pr(src)}))`]);
means.getRange(`J8:J${mend}`).formulas=d.averages.map((q,i)=>[`=IF(OR(D${i+8}=0,E${i+8}=0),"",I${i+8}-H${i+8})`]);means.getRange(`H8:L${mend}`).setNumberFormat('0.000');means.getRange(`M8:N${mend}`).setNumberFormat('0.000000');means.getRange(`C8:C${mend}`).format.wrapText=true;means.getRange(`A8:P${mend}`).format.rowHeight=42;
const feature=sheets['功能比较'];setup(feature,'按功能查看Jev影响','主功能集与32条Jev诊断集分开。通过率为严格自动断言匹配率，人工复核尚未签字。','L');
const fend=table(feature,['功能','模式','执行题次','通过','未通过','通过率','平均整题秒','P95秒','平均API次数','DeepSeek次数','Jev次数','未知用量请求'],d.groups.map(g=>[g.group,g.mode,g.questions,g.pass,g.fail,null,g.question_seconds.mean,g.question_seconds.p95,g.mean_calls,g.deepseek_calls,g.jev_calls,g.unknown_calls]),[18,13,16,13,13,16,19,17,20,19,16,23],'FunctionComparison');
feature.getRange(`F8:F${fend}`).formulas=d.groups.map((g,i)=>[`=IF(C${i+8}=0,"",D${i+8}/C${i+8})`]);feature.getRange(`F8:F${fend}`).setNumberFormat('0.0%');feature.getRange(`G8:I${fend}`).setNumberFormat('0.000');
const api=sheets['API明细'];setup(api,'两家模型的实际HTTP请求','一行一次真实HTTP。F为原批次，C为续跑。原币费用与保守折算分列，超时用量未知不写零。','R');
const aend=table(api,['请求编号','问题编号','遍数','模式','提供方','HTTP状态','请求秒','输入Token','输出Token','缓存命中','缓存未命中','已知原币费用','原币种','保守折算元','未知用量','返回模型','网络错误','证据'],d.apis.map(a=>[(a.source_folder.includes('continuation')?'C-':'F-')+a.original_wire_id,a.question_id,a.repeat,a.mode,a.provider,a.http_status,a.seconds,a.prompt_tokens,a.output_tokens,a.cache_hit,a.cache_miss,a.cost_native,a.currency,a.budget_cny,a.cost_known?'否':'是',a.returned_model??'',a.transport_error??'',a.evidence]),[22,25,8,13,15,14,16,17,17,17,18,21,14,20,16,24,24,68],'ActualHttpRequests');api.getRange(`G8:G${aend}`).setNumberFormat('0.000');api.getRange(`L8:N${aend}`).setNumberFormat('0.00000000');
const issues=sheets['问题与极端值'];setup(issues,'失败与极端值定位','共同失败不直接归因Jev。极端值保留原始耗时与保守费用，不作删除。','I');
const snippet=text=>text.length>110?text.slice(0,100)+'…完整见证据':text;
const issueRows=[...d.questions.filter(q=>q.status!=='PASS').map(q=>[q.id,q.repeat,q.mode,q.group_id,q.issue_category,snippet(q.failed_checks.join('；')),snippet(q.output.reply??q.error_code??''),q.explanation,q.evidence]),...d.extremes.map(e=>[e.id,e.repeat,e.mode,'极端值',e.metric,String(e.value),'IQR上界 '+e.iqr_threshold,e.explanation,e.evidence])];
const iend=table(issues,['编号','遍数','模式','功能','分类','未满足断言或数值','实际回复或范围','原因线索','证据'],issueRows,[26,8,13,17,29,55,85,100,70],'IssuesAndExtremes');issues.getRange(`F8:I${iend}`).format.wrapText=true;issues.getRange(`A8:I${iend}`).format.rowHeight=70;
const summary=sheets['总览'];setup(summary,'Jev开关真实模型对照','源码c2d5ea6，当前P8.7入口。离线AI组合测试，不代表App或正式后端联合验收。');
const cost=sheets['调用与费用'];setup(cost,'按模型查看单次调用时间与费用','本页包含全部正式实际HTTP，费用均价只针对有用量的请求，未知部分另列；小批量支出在总预算中。','J');
table(cost,['模式','提供方','实际请求','平均HTTP秒','P95秒','已知用量请求','已知请求均价','原币','未知用量请求','保守折算元'],d.provider_summaries.map(x=>[x.mode,x.provider,x.requests,x.request_seconds.mean,x.request_seconds.p95,x.known_usage_requests,x.known_requests_mean_cost_native,x.currency,x.unknown_usage_requests,x.conservative_cny]),[15,17,17,20,17,23,24,13,23,23],'ProviderCosts');
cost.getRange('D8:E11').setNumberFormat('0.000');cost.getRange('G8:G11').setNumberFormat('0.00000000');cost.getRange('J8:J11').setNumberFormat('0.000000');
cost.getRange('A14').values=[['均价分母为已知用量请求数，不能当作包括超时的全部请求平均实扣。']];
cost.getRange('A16').values=[['Jev的USD与DeepSeek的CNY不能直接相加。美元按8元只用于本轮预算。']];
cost.freezePanes.unfreeze();
const primary=d.summaries['主功能集'],spec=d.summaries['Jev专项'];
const summaryRows=[['主功能执行题次',primary.off.questions,primary.assist.questions,'只比较已完成配对，同一输入与初始状态'],['主功能自动通过率',primary.off.pass_rate,primary.assist.pass_rate,'待人工复核'],['主功能平均整题秒',primary.off.question_seconds.mean,primary.assist.question_seconds.mean,'包括两家HTTP及本地处理'],['主功能P95秒',primary.off.question_seconds.p95,primary.assist.question_seconds.p95,'失败耗时保留'],['主功能平均API次数',primary.off.mean_calls,primary.assist.mean_calls,'总HTTP次数含Jev'],['主功能DeepSeek次数',primary.off.deepseek_calls,primary.assist.deepseek_calls,'Jev请求另列'],['主功能Jev次数',primary.off.jev_calls,primary.assist.jev_calls,'仅实际HTTP计数'],['主功能保守折算元',primary.off.conservative_cny,primary.assist.conservative_cny,'峰值未命中价及未知预留'],['主功能每题保守元',primary.off.mean_conservative_cny_per_question,primary.assist.mean_conservative_cny_per_question,'费用上界，不是实际扣费'],['主功能每API保守元',primary.off.mean_conservative_cny_per_api,primary.assist.mean_conservative_cny_per_api,'费用上界，不是实际扣费'],['主功能平均HTTP秒',primary.off.api_seconds.mean,primary.assist.api_seconds.mean,'按实际HTTP请求平均'],['主功能未知用量请求',primary.off.unknown_calls,primary.assist.unknown_calls,'未知费用不能登记为零'],['专项自动通过率',spec.off.pass_rate,spec.assist.pass_rate,'32条，独立统计'],['专项平均整题秒',spec.off.question_seconds.mean,spec.assist.question_seconds.mean,'不并入主功能率'],['专项平均API次数',spec.off.mean_calls,spec.assist.mean_calls,'包含Jev调用']];
table(summary,['指标','Jev关闭','Jev开启','口径'],summaryRows,[32,22,22,65],'MainSummary');summary.getRange('B9:C9').setNumberFormat('0.0%');summary.getRange('B20:C20').setNumberFormat('0.0%');summary.getRange('B10:C12').setNumberFormat('0.000');summary.getRange('B15:C17').setNumberFormat('0.000000');summary.getRange('B18:C18').setNumberFormat('0.000');summary.getRange('B21:C22').setNumberFormat('0.000');
summary.getRange('A25:D25').values=[['主功能配对改善',d.paired['主功能集'].improved,'配对退步',d.paired['主功能集'].regressed]];
summary.getRange('A27:D27').values=[['费用停止条件','已按用户要求解除','截至结束保守占用元',Number(d.complete.budget_after?.charged_or_reserved_cny??0)]];
summary.getRange('D27').setNumberFormat('0.000000');
summary.getRange('A29').values=[['完成状态 '+(d.complete.complete?'计划执行完成':'提前结束 '+d.complete.stop_reason)]];
summary.getRange('A31').values=[['开启后是否值得保留，应结合改善题、退步题、快捷路由比例及新增超时判断。']];
summary.freezePanes.unfreeze();
const method=sheets['方法说明'];setup(method,'复查口径与接续工作','准确性、用量估算、保守预算和平台实扣分开。原始证据与首次失败始终保留。','D');
const notes=[['固定版本','c2d5ea6。AI入口P8.7，Jev 1.13.0。两组均为当前源码，不和历史旧成绩直接相减。'],['样本','128条单轮＋32个四轮场景，共256题次/遍。另加32条Jev专项。两模式各两遍1152题次。'],['配对顺序','按完整单轮或多轮场景交错开关顺序，第二遍反转。每种模式重建相同前提，场景后续上下文独立发展。'],['真实接口','使用当前create_app工厂与带合成认证的进程内HTTP；仅两家模型允许外网，不连接业务服务器。'],['密钥','Windows当前用户DPAPI保存在仓库外。Jev默认关闭不会自动读取隐藏密钥。'],['零调用','零模型规则路径正常保留。节点数量不当成HTTP次数。声明调用与实际出站分别记录。'],['费用','Jev原币USD、DeepSeek原币CNY。每1美元按8元仅作保守折算，不代表实际银行汇率或平台账单。'],['未知用量','失败或超时仍计请求、耗时和保守预留；未知费用留空。已知费用合计只是下界。'],['授权更新','初始10元及DeepSeek累计20元限制先触发。11月4日用户明确费用不再限制，授权续跑；原账本未清零。'],['续跑口径','原998题次含1次预算阻断。只续未执行或BLOCKED；已完成PASS和FAIL不重试，原阻断输出及费用保留。'],['原预期','历史预期不改。状态或错误码差异单列，人工标注继续待复核。'],['夹具修正','首次付费前修复历史引用签发时间，使其不晚于片段时间，仍保持15分钟有效期。'],['离线结果','AI原生1277通过、2跳过。适配器13通过。模拟预检576题次只检查流程，不当作模型正确率。'],['环境适配','Windows asyncio内部socketpair放行仅限标准库自身；初次网络拦截和导入错误日志保留。'],['小批量','18题次、34请求，3次Jev超时。原infrastructure_ok全HTTP成功门槛过严，另附validated.json说明，不删除原结果。'],['适用边界','中文、合成库存、本地AI入口。未测MuMu界面、正式业务数据库、生产请求流量和英语整体效果。'],['原始证据',d.run_folders.join('；')+'；具体编号见数据页最后一列。'],['价格来源','2026-11-03复核 https://docs.typesafe.ai/models 和 https://api-docs.deepseek.com/zh-cn/quick_start/pricing/']];
const nend=table(method,['项目','说明'],notes,[26,135],'Methodology');method.getRange(`B8:B${nend}`).format.wrapText=true;method.getRange(`A8:B${nend}`).format.rowHeight=44;
wb.recalculate();
await fs.mkdir(path.join(root,'.qa'),{recursive:true});
await fs.writeFile(path.join(root,'.qa/workbook-inspect.ndjson'),(await wb.inspect({kind:'table',range:'总览!A7:D19',include:'values,formulas',tableMaxRows:15,tableMaxCols:4})).ndjson);
await fs.writeFile(path.join(root,'.qa/formula-errors.ndjson'),(await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:30}})).ndjson);
for(const name of names){const blob=await wb.render({sheetName:name,range:name==='总览'?'A1:D31':name==='方法说明'?'A1:B17':'A1:H14',scale:1.3,format:'png'});await fs.writeFile(path.join(root,'.qa',name+'.png'),new Uint8Array(await blob.arrayBuffer()));}
await(await SpreadsheetFile.exportXlsx(wb)).save(path.join(root,'reports/Jev开关对照测试总览.xlsx'));
console.log('Exported paired workbook');
