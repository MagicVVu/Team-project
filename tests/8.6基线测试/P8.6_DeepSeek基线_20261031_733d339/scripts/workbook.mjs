import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const data=JSON.parse(await fs.readFile(path.join(root,'reports/workbook-data.json'),'utf8'));
const {summary:s,questions:qs,averages:av,apis,extremes}=data;
const wb=Workbook.create();
const names=['总览','每题均值','极端值','逐题记录','API明细','方法说明'];
const sheets=Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const navy='#183B56',teal='#137C8B',light='#EAF3F5',muted='#617381';
const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
const qr=8,qe=qr+qs.length-1,ar=8,ae=ar+apis.length-1;
const range=(sheet,column)=>`'${sheet}'!$${column}$8:$${column}$${sheet==='API明细'?ae:qe}`;
const qcol=c=>range('逐题记录',c),acol=c=>range('API明细',c);
function title(sh,text,note,last){
  sh.showGridLines=false;sh.tabColor=teal;
  sh.getRange(`A1:${last}2`).merge();sh.getRange('A1').values=[[text]];
  sh.getRange(`A1:${last}2`).format={fill:navy,font:{name:'Arial',size:16,bold:true,color:'#FFFFFF'},verticalAlignment:'center'};
  sh.getRange(`A3:${last}4`).merge();sh.getRange('A3').values=[[note]];
  sh.getRange(`A3:${last}4`).format={font:{name:'Arial',size:10,color:muted},wrapText:true,verticalAlignment:'center'};
  sh.getRange('A1:A4').format.rowHeight=22;
}
function table(sh,headers,rows,id,widths){
  const end=Math.max(8,7+rows.length),last=col(headers.length);
  sh.getRange(`A7:${last}7`).values=[headers];if(rows.length)sh.getRange(`A8:${last}${end}`).values=rows;
  sh.getRange(`A7:${last}${end}`).format={font:{name:'Arial',size:10,color:'#203544'},verticalAlignment:'center',rowHeight:25};
  sh.getRange(`A7:${last}7`).format={fill:navy,font:{bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:34};
  sh.getRange(`A8:${last}${end}`).format.borders={bottom:{style:'hair',color:'#E3EBEF'}};
  for(let i=0;i<headers.length;i++)sh.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=widths[i]??15;
  sh.tables.add(`A7:${last}${end}`,true,id).showFilterButton=true;
  sh.freezePanes.freezeRows(7);sh.freezePanes.freezeColumns(3);
  return end;
}
const qrows=qs.map(q=>[q.execution_id,q.id,q.repeat,q.category,q.text,q.status,q.output.status??'',q.stop_reason??'',q.actual_http_calls,q.declared_model_invocations??null,q.seconds,q.api_seconds,q.non_api_seconds,null,q.cost_known?'已知':'未知',q.input_tokens,q.output_tokens,q.output.fallback_used??false,q.failed_checks.join('；'),q.evidence,q.call_behavior]);
title(sheets['逐题记录'],'每次问题的实际执行记录','一行是一个问题的一次执行；耗时单位秒，费用单位元。合法零调用保留，失败未删除。','U');
table(sheets['逐题记录'],['执行编号','问题编号','遍数','功能','输入问题','自动结果','处理状态','停止原因','实际API次数','程序声明次数','整题耗时 秒','API合计 秒','本地及记录 秒','用量费用 元','费用覆盖','输入Token','输出Token','备用回复','未满足的断言','证据索引','调用路径'],qrows,'QuestionRuns',[25,20,7,20,58,12,19,24,13,13,15,15,17,17,11,15,15,12,40,50,27]);
sheets['逐题记录'].getRange(`E8:E${qe}`).format.wrapText=true;sheets['逐题记录'].getRange(`A8:T${qe}`).format.rowHeight=42;
sheets['逐题记录'].getRange(`K8:N${qe}`).setNumberFormat('0.000000');
sheets['逐题记录'].getRange(`I8:J${qe}`).setNumberFormat('0');
sheets['逐题记录'].getRange(`F8:F${qe}`).conditionalFormats.add('containsText',{text:'FAIL',format:{fill:'#FCE7E7',font:{color:'#A52A2A',bold:true}}});
const arows=apis.map(a=>[a.wire_id,a.execution_id,a.id??a.question_id,a.repeat,a.step??null,a.http_status??null,a.seconds,a.input_tokens,a.cache_hit_tokens,a.cache_miss_tokens,a.output_tokens,a.hit_rate,a.miss_rate,a.output_rate,null,a.cost_known?'已知':'未知',a.model??'未知',a.transport_error??'',a.evidence,a.decision_action??'',a.plan_action??'',a.observation_error??'',a.read_kinds??'']);
title(sheets['API明细'],'逐次实际 API 请求','一行只对应一次出站HTTP请求。Token和费率来自真实响应及执行日价格，鉴权密钥不进入本表。','S');
table(sheets['API明细'],['请求编号','执行编号','问题编号','遍数','决策步','HTTP状态','请求耗时 秒','输入Token','缓存命中','缓存未命中','输出Token','命中输入单价','未命中输入单价','输出单价','估算费用 元','费用覆盖','返回模型名','网络错误','证据索引','决策类型','业务动作','前轮错误反馈','本次读取种类'],arows,'ActualApiRequests',[17,25,21,7,9,11,17,15,15,15,15,17,18,15,18,11,25,22,52,19,19,35,30]);
sheets['API明细'].getRange(`G8:G${ae}`).setNumberFormat('0.000000');sheets['API明细'].getRange(`L8:O${ae}`).setNumberFormat('0.00000000');
const costFormulas=apis.map((a,i)=>{let r=ar+i;return [`=IF(P${r}="未知","",(I${r}*L${r}+J${r}*M${r}+K${r}*N${r})/1000000)`];});
sheets['API明细'].getRange(`O8:O${ae}`).formulas=costFormulas;
sheets['逐题记录'].getRange(`N8:N${qe}`).formulas=qs.map((q,i)=>{let r=qr+i;return [`=IF(COUNTIFS(${acol('B')},A${r},${acol('P')},"未知")>0,"",SUMIF(${acol('B')},A${r},${acol('O')}))`];});
const avgrows=av.map(q=>[q.id,q.category,q.text,q.runs,q.counts.PASS??0,q.counts.FAIL??0,q.counts.REVIEW??0,null,q.time.min,q.time.max,null,q.total_calls,null,q.cost.min,q.cost.max,q.all_runs_pass?'三遍均通过':'存在非通过或未满三遍',q.same_result?'一致':'有差异',q.evidence_ids.join('，')]);
title(sheets['每题均值'],'每个问题的三遍均值','一行对应一个独立输入。先看执行遍数，再看均值、最小值和最大值；六轮问题的前序上下文按场景保存。','R');
table(sheets['每题均值'],['问题编号','功能','输入问题','已执行遍数','PASS次数','FAIL次数','REVIEW次数','平均整题 秒','最短整题 秒','最长整题 秒','平均API次数','API总次数','平均费用 元','最低费用 元','最高费用 元','三遍通过情况','业务结果一致性','执行编号'],avgrows,'QuestionMeans',[21,20,60,13,12,12,14,17,17,17,17,15,18,18,18,27,22,60]);
const ve=7+av.length;
sheets['每题均值'].getRange(`C8:C${ve}`).format.wrapText=true;sheets['每题均值'].getRange(`A8:R${ve}`).format.rowHeight=42;
sheets['每题均值'].getRange(`H8:J${ve}`).setNumberFormat('0.000000');sheets['每题均值'].getRange(`K8:K${ve}`).setNumberFormat('0.000');sheets['每题均值'].getRange(`L8:L${ve}`).setNumberFormat('0');sheets['每题均值'].getRange(`M8:O${ve}`).setNumberFormat('0.00000000');
for(const [c,source] of [['H','K'],['K','I'],['M','N']])sheets['每题均值'].getRange(`${c}8:${c}${ve}`).formulas=av.map((q,i)=>{let r=i+8;return [`=AVERAGEIF(${qcol('B')},A${r},${qcol(source)})`];});
sheets['每题均值'].getRange(`M8:M${ve}`).formulas=av.map((q,i)=>{let r=i+8;return [`=IF(COUNTIFS(${qcol('B')},A${r},${qcol('O')},"未知")>0,"",AVERAGEIF(${qcol('B')},A${r},${qcol('N')}))`];});
title(sheets['极端值'],'极端值及证据分析','Top 5不一定都是统计异常。上界采用Q3加1.5倍IQR，最小值单列；客户端日志不能确认供应商排队或公网慢的具体责任。','M');
const erows=extremes.map(e=>[e.metric,e.kind,e.rank,e.execution_id,e.text,e.seconds,e.api_calls,e.cost_cny,e.status,e.above_iqr_threshold===undefined?'最小值对照':e.above_iqr_threshold?'超过IQR上界':'仅高值排名',e.observed_explanation,e.unconfirmed_cause,e.evidence]);
const ee=table(sheets['极端值'],['指标','类型','排名','执行编号','问题','整题 秒','API次数','费用 元','自动结果','是否统计异常','日志可证明的原因','尚不能确认的原因','证据索引'],erows,'ExtremeValues',[17,12,8,25,55,15,13,17,12,23,85,75,55]);
sheets['极端值'].getRange(`E8:M${ee}`).format.wrapText=true;sheets['极端值'].getRange(`A8:M${ee}`).format.rowHeight=75;
sheets['极端值'].getRange(`F8:F${ee}`).setNumberFormat('0.000');sheets['极端值'].getRange(`H8:H${ee}`).setNumberFormat('0.00000000');
title(sheets['方法说明'],'测试口径与使用范围','源码733d339，P8.6自主循环，single-object-1逐件库存。只读合成环境，未使用Jev或真实用户数据库。','H');
const method=[['数据单位','一次问题是单轮输入或多轮场景的一轮；三遍是重复观测，不当作三倍独立样本。'],['每题耗时','该输入进入本地AI流程到最终返回的墙钟时间，包含模型请求、只读计算和记录开销，不含App网络和业务数据库。'],['单次API耗时','一次实际DeepSeek HTTP请求到完整响应读取结束；不含没有出站的程序路径。'],['每题平均费用','正式批次完整可计算费用合计除以已执行问题数；零调用为0，未知费用不伪装为0。'],['单次API平均费用','正式批次费用合计除以实际HTTP次数，不是每题费用的非加权再平均。'],['费率单位','API明细中费率单位均为元每百万Token。缓存、未缓存输入和输出分别计价。'],['正确率','PASS除以PASS加FAIL；REVIEW、BLOCKED和未执行数量单列。模型自称正确不是评分依据。'],['极端值','保留全部样本，列慢题、贵题和调用最多题Top5；另列最小耗时，Q3加1.5IQR只作描述标记。'],['预算','本轮另设5元上限，与前轮4.534698元分账；同一个累计账本，不清零。保守预留与用量估算、平台账单分开。'],['调用次数','同时记录实际HTTP与程序声明次数；预算门控可能使声明一次但未出站。模型和工具读取次数不混用。'],['人工复核','用例为原创合成数据，人工标注和自然度评分仍pending；没有代签。'],['旧版比较','旧批次数量模型与当前逐件模型不同，不能把两套数据的通过率差直接归因于P8.6或Jev。'],['后续Jev','固定同样代码、事实、用例及评分，统计DeepSeek和Jev合计成本；若用于调优，需另备未见评估集。'],['价格来源','https://api-docs.deepseek.com/zh-cn/quick_start/pricing/，2026-10-31复核；平台实扣账单未核对。']];
method.push(['最后一题未执行','r3-p86-m10-2-t6在HTTP发送前被预算门控拦截。其输入仅有前两遍数据；均值按2遍计算，不补零、不伪造第三遍。'],['预算最终状态','本轮含小批量保守记账4.957662元，限额5元。正式批次用量估算0.74768412元；平台实际账单尚未核对。'],['读表顺序','总览看汇总，每题均值看同一问题的重复结果，逐题记录看每次执行，API明细查真实请求，极端值页查原因及证据。']);
sheets['方法说明'].getRange('A7:B23').values=method;sheets['方法说明'].getRange('A7:B23').format={font:{name:'Arial',size:11},wrapText:true,rowHeight:45,verticalAlignment:'center'};
sheets['方法说明'].getRange('A:A').format.columnWidth=23;sheets['方法说明'].getRange('B:B').format.columnWidth=105;
const finished=s.runs.every(r=>r.completion.stop_reason!=='RUNNING');
const runLabel=!finished?'运行中 不能作为最终成绩':s.not_run_questions?`预算保护停止 未执行${s.not_run_questions}题次`:'正式运行已结束';
const over=sheets['总览'];title(over,'P8.6 DeepSeek 基线总览',`${runLabel}；人工标签待复核；费用为用量估算。单题与单次API分别统计。`,'L');
over.getRange('A7:C7').values=[['指标','结果','定义']];
const metrics=[['正式题次',`=COUNTA(${qcol('A')})`,'包含单轮和六轮场景的每一轮'],['自动通过',`=COUNTIF(${qcol('F')},"PASS")`,'所有关键断言满足'],['自动失败',`=COUNTIF(${qcol('F')},"FAIL")`,'保留原始失败'],['自动正确率','=IF(B9+B10=0,"",B9/(B9+B10))','人工标签仍待复核'],['实际API请求',`=COUNTA(${acol('A')})`,'实际出站，不用程序阶段计数替代'],['每题平均API','=B12/B8','包括合法零调用问题'],['每题平均耗时 秒',`=AVERAGE(${qcol('K')})`,'本机AI处理整题'],['每题中位耗时 秒',`=MEDIAN(${qcol('K')})`,'P50'],['每题P95 秒',`=PERCENTILE(${qcol('K')},0.95)`,'线性分位数'],['每题最大耗时 秒',`=MAX(${qcol('K')})`,'不删除极端值'],['每题最小耗时 秒',`=MIN(${qcol('K')})`,'常见于零API路径'],['单次API平均耗时 秒',`=AVERAGE(${acol('G')})`,'只含实际请求'],['单次API最大耗时 秒',`=MAX(${acol('G')})`,'网络与服务合计'],['已知用量费用 元',`=SUM(${acol('O')})`,'有未知费用时只是小计'],['每题平均费用 元',`=IF(COUNTIF(${qcol('O')},"未知")>0,"",B21/B8)`,'含零调用的0元'],['单次API平均费用 元',`=IF(COUNTIF(${acol('P')},"未知")>0,"",B21/B12)`,'加权总费用除以总请求'],['零调用题数',`=COUNTIF(${qcol('I')},0)`,'不参与单次API均值'],['超过两次调用题数',`=COUNTIF(${qcol('I')},">2")`,'真实多次调用的证据'],['费用未知请求数',`=COUNTIF(${acol('P')},"未知")`,'不能视为免费']];
metrics[0][0]='已执行题次';
over.getRange('A8:C26').values=metrics.map(x=>[x[0],null,' '+x[2]]);over.getRange('B8:B26').formulas=metrics.map(x=>[x[1]]);
over.getRange('A7:C26').format={font:{name:'Arial',size:11},rowHeight:28,verticalAlignment:'center'};over.getRange('A7:C7').format={fill:navy,font:{color:'#FFFFFF',bold:true}};
over.getRange('A:A').format.columnWidth=31;over.getRange('B:B').format.columnWidth=21;over.getRange('C:C').format.columnWidth=42;over.getRange('D:D').format.columnWidth=3;over.getRange('E:K').format.columnWidth=14;
over.getRange('B11').setNumberFormat('0.00%');over.getRange('B13:B20').setNumberFormat('0.000');over.getRange('B21:B23').setNumberFormat('0.00000000');
over.getRange('E7:F7').values=[['每题API次数','题次']];const bins=[0,1,2,3,4,5,6];over.getRange('E8:E14').values=bins.map(x=>[x<6?`${x}次`:'6次及以上']);over.getRange('F8:F14').formulas=bins.map(x=>[`=COUNTIF(${qcol('I')},${x<6?x:'">=6"'})`]);
over.getRange('E7:F7').format={fill:navy,font:{color:'#FFFFFF',bold:true}};
const chart=over.charts.add('bar',over.getRange('E7:F14'));chart.title='每题实际 API 次数分布';chart.hasLegend=false;chart.setPosition('E17','L30');chart.titleTextStyle.typeface='Arial';chart.titleTextStyle.fontSize=13;chart.series.items[0].fill=teal;chart.yAxis={numberFormatCode:'0',numberFormatSourceLinked:false,textStyle:{typeface:'Arial'}};
over.getRange('A29:C29').values=[['分遍对照','问题数','平均整题 秒']];over.getRange('A29:C29').format={fill:navy,font:{color:'#FFFFFF',bold:true}};
for(const r of s.by_repeat){let n=29+r.repeat;over.getRange(`A${n}:C${n}`).values=[[`第${r.repeat}遍`,r.questions,null]];over.getRange(`C${n}`).formulas=[[`=AVERAGEIF(${qcol('C')},${r.repeat},${qcol('K')})`]];over.getRange(`C${n}`).setNumberFormat('0.000');}
over.getRange('A35:C35').values=[['重复性','数量','说明']];over.getRange('A35:C35').format={fill:navy,font:{color:'#FFFFFF',bold:true}};
over.getRange('A36:C38').values=[['有三遍记录的问题',s.three_repeat_questions,'独立输入数'],['三遍均通过',s.all_three_pass,'不把重复观测当新样本'],['业务结果一致',s.same_semantic_result,'忽略随机ID与事实显示顺序']];
const behaviors=['规则零调用','一次模型决策','核对后单独结束','追加读取后再决策','校验反馈后再决策','其他多次决策'];
over.getRange('E33:H33').merge();over.getRange('E33').values=[['调用路径分布']];over.getRange('E33:H33').format={fill:navy,font:{color:'#FFFFFF',bold:true}};
for(let i=0;i<behaviors.length;i++){let r=34+i;over.getRange(`E${r}:G${r}`).merge();over.getRange(`E${r}`).values=[[behaviors[i]]];over.getRange(`H${r}`).formulas=[[`=COUNTIF(${qcol('U')},"${behaviors[i]}")`]];}
over.getRange('A41:L43').merge();over.getRange('A41').values=[['本轮含小批量保守记账4.957662元，5元上限已停止调用；正式用量估算见左表。最后1题未执行，该输入均值按前2遍计算。多次API、长上下文、缓存变化都可能影响成本，具体原因见极端值页。']];over.getRange('A41:L43').format={wrapText:true,font:{name:'Arial',size:11,color:muted},fill:light};
for(const sh of Object.values(sheets)){sh.getUsedRange().format.verticalAlignment='center';}
wb.recalculate();
const value=cell=>over.getRange(cell).values[0][0];
const near=(a,b)=>typeof a==='number' && Math.abs(a-b)<1e-8;
const expectedFee=apis.reduce((n,a)=>n+(a.cost_cny??0),0);
if(!near(value('B8'),qs.length)||!near(value('B12'),apis.length)||!near(value('B21'),expectedFee))throw new Error('Headline/source reconciliation failed');
if(!near(value('B14'),s.question_seconds.mean)||!near(value('B19'),s.api_seconds.mean)||!near(value('B16'),s.question_seconds.p95))throw new Error('Timing formulas differ from independent statistics');
const baseline=value('B21'),originalRate=apis[0].miss_rate,delta=apis[0].cache_miss_tokens/1000000;
if(apis[0].cost_known && delta>0){
  sheets['API明细'].getRange('M8').values=[[originalRate+1]];wb.recalculate();
  if(!near(value('B21'),baseline+delta)||!near(value('B22'),(baseline+delta)/qs.length)||!near(value('B23'),(baseline+delta)/apis.length))throw new Error('Cost dependency recalculation failed');
  sheets['API明细'].getRange('M8').values=[[originalRate]];wb.recalculate();
  if(!near(value('B21'),baseline))throw new Error('Temporary validation edit not restored');
}
await fs.writeFile(path.join(root,'evidence/workbook-validation.json'),JSON.stringify({headlines_match_source:true,timing_formulas_match:true,cost_dependency_edit_restored:true,questions:qs.length,apis:apis.length,known_fee:baseline},null,2));
await fs.mkdir(path.join(root,'.qa'),{recursive:true});
const inspected=await wb.inspect({kind:'table',range:'总览!A7:C26',include:'values,formulas',tableMaxRows:22,tableMaxCols:3,maxChars:5500});await fs.writeFile(path.join(root,'evidence/workbook-inspection.ndjson'),inspected.ndjson);
const errorScan=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},summary:'final formula errors'});await fs.writeFile(path.join(root,'evidence/workbook-errors.ndjson'),errorScan.ndjson);
for(const [name,range] of [['总览','A1:L43'],['每题均值','A1:M13'],['逐题记录','A1:N13'],['API明细','A1:P13'],['极端值','A1:L11'],['方法说明','A1:B23']]){
  const blob=await wb.render({sheetName:name,range,scale:1.4,format:'png'});await fs.writeFile(path.join(root,'.qa',`${name}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const output=await SpreadsheetFile.exportXlsx(wb);await output.save(path.join(root,'reports/P8.6 DeepSeek基线总览.xlsx'));
const inspection=path.join(root,'reports/P8.6 DeepSeek基线总览.xlsx.inspect.ndjson');
try{await fs.rename(inspection,path.join(root,'evidence/workbook-export-inspection.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log(JSON.stringify({sheets:names,questionRows:qs.length,apiRows:apis.length,output:'reports/P8.6 DeepSeek基线总览.xlsx'}));
