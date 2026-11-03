import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const d=JSON.parse(await fs.readFile(path.join(root,'reports/workbook-data.json'),'utf8'));
const {summary:s,questions:qs,apis,averages,stages,native,native_runs,extremes}=d;
const wb=Workbook.create(),names=['总览','功能覆盖','问题清单','每题均值','逐题执行','API明细','离线明细','方法说明'];
const sh=Object.fromEntries(names.map(x=>[x,wb.worksheets.add(x)]));
const navy='#183B56',teal='#137C8B',muted='#526776';
const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
const end=7+qs.length,aend=7+apis.length;
const qr=c=>`'逐题执行'!$${c}$8:$${c}$${end}`,ar=c=>`'API明细'!$${c}$8:$${c}$${aend}`;
function title(s,t,n,last='L'){
 s.showGridLines=false;s.tabColor=teal;s.getRange(`A1:${last}2`).merge();s.getRange('A1').values=[[t]];s.getRange(`A1:${last}2`).format={fill:navy,font:{name:'Arial',size:17,color:'#FFFFFF',bold:true},rowHeight:24,verticalAlignment:'center'};
 s.getRange(`A3:${last}4`).merge();s.getRange('A3').values=[[n]];s.getRange(`A3:${last}4`).format={font:{name:'Arial',size:11,color:muted},rowHeight:23,wrapText:true,verticalAlignment:'center'};
}
function table(s,headers,rows,widths,id){
 const last=col(headers.length),e=7+rows.length;s.getRange(`A7:${last}7`).values=[headers];if(rows.length)s.getRange(`A8:${last}${e}`).values=rows;
 s.getRange(`A7:${last}${Math.max(8,e)}`).format={font:{name:'Arial',size:10,color:'#203544'},rowHeight:32,verticalAlignment:'center'};s.getRange(`A7:${last}7`).format={fill:navy,font:{bold:true,color:'#FFFFFF'},rowHeight:38,wrapText:true};
 widths.forEach((w,i)=>s.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);
 if(rows.length){s.tables.add(`A7:${last}${e}`,true,id).showFilterButton=true;s.freezePanes.freezeRows(7);s.freezePanes.freezeColumns(2);}
 return e;
}
title(sh['逐题执行'],'每次问题的真实执行','当前P8.6入口。主表采用有效执行；原始夹具错误与修正补测分别保留，详见方法说明。','R');
table(sh['逐题执行'],['执行编号','问题编号','功能阶段','功能','遍数','输入','自动结果','处理状态','停止原因','实际API次数','整题秒','API合计秒','用量费用元','费用覆盖','未满足断言','证据索引','是否夹具补测','原异常'],qs.map(q=>[q.execution_id,q.id,q.group_id,q.category,q.repeat,q.text,q.status,q.output.status??'',q.stop_reason??'',q.actual_http_calls,q.seconds,q.api_seconds,null,q.cost_known?'已知':'未知',q.failed_checks.join('；'),q.evidence,q.evidence.includes('archive-recheck-')?'是':'否',q.error_code??'']),[29,25,13,23,8,65,13,24,28,15,15,16,19,12,50,62,17,25],'QuestionExecutions');
sh['逐题执行'].getRange(`F8:F${end}`).format.wrapText=true;sh['逐题执行'].getRange(`A8:R${end}`).format.rowHeight=46;sh['逐题执行'].getRange(`K8:L${end}`).setNumberFormat('0.000000');sh['逐题执行'].getRange(`M8:M${end}`).setNumberFormat('0.00000000');
sh['逐题执行'].getRange(`G8:G${end}`).conditionalFormats.add('containsText',{text:'FAIL',format:{fill:'#FCE7E7',font:{color:'#9C2828',bold:true}}});
title(sh['API明细'],'实际DeepSeek请求与用量','只计真实出站HTTP；单价单位为元每百万Token，费用不是平台账单。','S');
table(sh['API明细'],['请求编号','执行编号','问题编号','遍数','决策步','HTTP状态','请求秒','输入Token','缓存命中','缓存未命中','输出Token','命中单价','未命中单价','输出单价','费用元','费用覆盖','返回模型','网络错误','证据索引'],apis.map(a=>[a.wire_id,a.execution_id,a.question_id,a.repeat,a.step,a.http_status,a.seconds,a.input_tokens,a.cache_hit_tokens,a.cache_miss_tokens,a.output_tokens,a.hit_rate,a.miss_rate,a.output_rate,null,a.cost_known?'已知':'未知',a.model??'',a.transport_error??'',a.evidence]),[18,29,25,8,10,12,16,16,16,17,16,16,16,16,19,12,23,21,65],'ApiCalls');
sh['API明细'].getRange(`G8:G${aend}`).setNumberFormat('0.000000');sh['API明细'].getRange(`L8:O${aend}`).setNumberFormat('0.00000000');
sh['API明细'].getRange(`O8:O${aend}`).formulas=apis.map((a,i)=>{let r=i+8;return [`=IF(P${r}="未知","",(I${r}*L${r}+J${r}*M${r}+K${r}*N${r})/1000000)`]});
sh['逐题执行'].getRange(`M8:M${end}`).formulas=qs.map((q,i)=>{let r=i+8;return [`=IF(COUNTIFS(${ar('B')},A${r},${ar('P')},"未知")>0,"",SUMIF(${ar('B')},A${r},${ar('O')}))`]});
title(sh['每题均值'],'同一问题的两遍均值','均值按实际有效遍数计算；业务输入与数据前提冻结，重复运行不算新的独立样本。','N');
const avgEnd=table(sh['每题均值'],['问题编号','功能阶段','输入','有效遍数','PASS次数','FAIL次数','平均整题秒','最短秒','最长秒','平均API次数','平均费用元','最高费用元','两遍均通过','执行编号'],averages.map(q=>[q.id,qs.find(r=>r.id===q.id)?.group_id,q.text,q.runs,q.counts.PASS??0,q.counts.FAIL??0,null,q.time.min,q.time.max,null,null,q.cost.max,q.all_runs_pass?'是':'否',q.evidence_ids.join('，')]),[25,14,65,15,13,13,18,15,15,18,19,19,17,65],'QuestionMeans');
for(const [dest,source] of [['G','K'],['J','J'],['K','M']])sh['每题均值'].getRange(`${dest}8:${dest}${avgEnd}`).formulas=averages.map((q,i)=>[`=AVERAGEIF(${qr('B')},A${i+8},${qr(source)})`]);
sh['每题均值'].getRange(`G8:I${avgEnd}`).setNumberFormat('0.000000');sh['每题均值'].getRange(`J8:J${avgEnd}`).setNumberFormat('0.000');sh['每题均值'].getRange(`K8:L${avgEnd}`).setNumberFormat('0.00000000');sh['每题均值'].getRange(`C8:C${avgEnd}`).format.wrapText=true;sh['每题均值'].getRange(`A8:N${avgEnd}`).format.rowHeight=46;
title(sh['功能覆盖'],'按阶段负责的功能分别看结果','模块测试与当前入口分开。模块列可能关联同一源码用例，禁止跨阶段相加成独立样本。','N');
const stageEnd=table(sh['功能覆盖'],['阶段','功能','主要检查','模块PASS','模块FAIL','模块跳过','入口题次','入口PASS','入口FAIL','入口通过率','平均整题秒','平均API次数','平均费用元','边界与注意'],stages.map(v=>[v.stage,v.title,v.features.join('；'),v.native_counts.PASS??0,v.native_counts.FAIL??0,v.native_counts.SKIP??0,null,null,null,null,null,null,null,v.notes.join('；')]),[14,24,65,15,15,15,15,15,15,18,18,18,19,85],'FeatureCoverage');
for(let i=0;i<stages.length;i++){const r=i+8;sh['功能覆盖'].getRange(`G${r}:M${r}`).formulas=[[
 `=COUNTIF(${qr('C')},A${r})`,`=COUNTIFS(${qr('C')},A${r},${qr('G')},"PASS")`,`=COUNTIFS(${qr('C')},A${r},${qr('G')},"FAIL")`,`=IF(H${r}+I${r}=0,"",H${r}/(H${r}+I${r}))`,`=IF(G${r}=0,"",AVERAGEIF(${qr('C')},A${r},${qr('K')}))`,`=IF(G${r}=0,"",AVERAGEIF(${qr('C')},A${r},${qr('J')}))`,`=IF(G${r}=0,"",AVERAGEIF(${qr('C')},A${r},${qr('M')}))`]];}
sh['功能覆盖'].getRange(`J8:J${stageEnd}`).setNumberFormat('0.00%');sh['功能覆盖'].getRange(`K8:L${stageEnd}`).setNumberFormat('0.000');sh['功能覆盖'].getRange(`M8:M${stageEnd}`).setNumberFormat('0.00000000');sh['功能覆盖'].getRange(`C8:N${stageEnd}`).format.wrapText=true;sh['功能覆盖'].getRange(`A8:N${stageEnd}`).format.rowHeight=62;
title(sh['离线明细'],'源码及本地接口的原始结果','包含AI源码、后端源码和Garin补充检查；原始ERROR、FAIL和SKIP保留，问题分类另列。','I');
table(sh['离线明细'],['层次','功能阶段','测试编号','原始结果','报告结果','问题分类','说明','耗时秒','证据'],native.map(r=>[r.layer,r.stage??'关联范围未细分',r.node,r.raw_status,r.status,r.classification,r.analysis,r.seconds,r.evidence]),[22,20,95,14,14,31,90,16,65],'OfflineCases');
title(sh['问题清单'],'需要队友继续处理的问题','真实模型问题与后端旧夹具、SQLite环境、文档契约差异分开，不将所有失败都归为程序缺陷。','H');
const issues=[...d.live_failures.map(q=>[q.execution_id,q.group_id,'当前入口真实模型',q.status,q.classification,q.reply,q.failed_checks.join('；')+'。'+q.analysis,q.evidence]),...d.offline_issues.map(r=>[r.execution_id,r.stage??'相关模块',r.layer,r.raw_status,r.classification,r.analysis,'完整trace见原始JUnit',r.evidence])];
const issueEnd=table(sh['问题清单'],['编号','阶段','层次','原始结果','分类','实际输出或问题','分析与下一步','证据'],issues,[90,16,25,14,35,85,95,70],'Issues');sh['问题清单'].getRange(`E8:H${issueEnd}`).format.wrapText=true;sh['问题清单'].getRange(`A8:H${issueEnd}`).format.rowHeight=66;
const over=sh['总览'];title(over,'AI各功能专项测试总览',`${s.live_finished?'本轮执行已结束':'仍在运行 不能作为最终成绩'}。源码733d339，P8.6当前入口，DeepSeek真实调用；人工复核待确认。`);
over.getRange('A:A').format.columnWidth=31;over.getRange('B:B').format.columnWidth=23;over.getRange('C:C').format.columnWidth=45;over.getRange('D:D').format.columnWidth=3;over.getRange('E:L').format.columnWidth=14;
const metrics=[['有效题次',`=COUNTA(${qr('A')})`,'计划512，夹具补测与原记录分开'],['自动PASS',`=COUNTIF(${qr('G')},"PASS")`,'冻结关键断言全部满足'],['自动FAIL',`=COUNTIF(${qr('G')},"FAIL")`,'未人工裁定，不改正确预期'],['严格自动通过率','=B9/(B9+B10)','不是实际用户总体正确率'],['实际API次数',`=COUNTA(${ar('A')})`,'单次HTTP，包含所有有效失败'],['每题平均API','=B12/B8','包含合法零调用'],['每题平均秒',`=AVERAGE(${qr('K')})`,'本地AI全流程'],['每题P95秒',`=PERCENTILE(${qr('K')},0.95)`,'线性分位数'],['每题最大秒',`=MAX(${qr('K')})`,'极端值不删除'],['单次API平均秒',`=AVERAGE(${ar('G')})`,'实际请求到完整响应'],['正式用量估算元',`=SUM(${ar('O')})`,'平台实扣账单未核对'],['每题平均费用元','=B18/B8','先汇总单题所有调用'],['单次API平均费用元','=B18/B12','总费用除以实际请求'],['零调用题次',`=COUNTIF(${qr('J')},0)`,'不参与单次API耗时平均']];
over.getRange('A7:C7').values=[['指标','数值','口径']];over.getRange('A8:C21').values=metrics.map(r=>[r[0],null,' '+r[2]]);over.getRange('B8:B21').formulas=metrics.map(r=>[r[1]]);over.getRange('A7:C21').format={font:{name:'Arial',size:11},rowHeight:29};over.getRange('A7:C7').format={fill:navy,font:{bold:true,color:'#FFFFFF'}};over.getRange('B11').setNumberFormat('0.00%');over.getRange('B13:B17').setNumberFormat('0.000');over.getRange('B18:B20').setNumberFormat('0.00000000');
over.getRange('A24:C27').values=[['本轮保守记账元',s.new_conservative_cny,'含小批量和夹具修正补测'],['本轮预算上限元',10,'独立新额度，旧账本不清零'],['AI源码回归PASS',1140,'另1条跳过，详见原始JUnit'],['Garin本地接口PASS',6,'临时SQLite实际状态校验']];over.getRange('A24:C27').format={font:{name:'Arial',size:11},rowHeight:29};over.getRange('B24:B25').setNumberFormat('0.000000');
over.getRange('E7:F7').values=[['每题API次数','题次']];over.getRange('E8:E14').values=[0,1,2,3,4,5,6].map(n=>[n===6?'6次及以上':n+'次']);over.getRange('F8:F14').formulas=[0,1,2,3,4,5,6].map(n=>[`=COUNTIF(${qr('J')},${n<6?n:'">=6"'})`]);over.getRange('E7:F7').format={fill:navy,font:{bold:true,color:'#FFFFFF'}};
const chart=over.charts.add('bar',over.getRange('E7:F14'));chart.title='当前入口每题API次数';chart.hasLegend=false;chart.setPosition('E17','L29');chart.titleTextStyle.fontSize=13;chart.series.items[0].fill=teal;chart.yAxis={numberFormatCode:'0',numberFormatSourceLinked:false};
over.getRange('A30:L32').merge();over.getRange('A30').values=[['后端原始回归：166 PASS、12 FAIL、415 ERROR、45 SKIP。主要为旧批次夹具、数量契约、SQLite迁移与文档差异，不能用6条本地专项代替全部验收。当前入口和功能模块分别看“功能覆盖”。']];over.getRange('A30:L32').format={wrapText:true,font:{name:'Arial',size:11,color:muted},fill:'#EDF4F6'};
const exRows=extremes.filter(e=>e.rank===1&&e.kind==='最大值').map(e=>[e.metric,e.execution_id,e.value,e.observed_explanation]);
over.getRange('A35:L35').merge();over.getRange('A35').values=[['极端值定位']];over.getRange('A35:L35').format={fill:navy,font:{bold:true,color:'#FFFFFF'}};
for(let i=0;i<exRows.length;i++){let r=36+i*2;over.getRange(`A${r}:B${r+1}`).merge();over.getRange(`A${r}`).values=[[exRows[i][0]+' '+exRows[i][2].toFixed(6)]];over.getRange(`C${r}:L${r+1}`).merge();over.getRange(`C${r}`).values=[[exRows[i][1]+'；'+exRows[i][3]]];over.getRange(`A${r}:L${r+1}`).format={wrapText:true,font:{name:'Arial',size:10},rowHeight:32};}
title(sh['方法说明'],'读表口径与未验证范围','AI功能测试与8.6性能基线分别归档；当前入口使用相同源码，但数据集和测试目的不同。','B');
const methods=[['读取次序','总览看总体，功能覆盖按每个阶段看模块与当前入口；问题清单定位；每题均值、逐题执行与API明细追溯。'],['样本单位','128条单轮加32个四轮场景，256个输入/遍，独立运行两遍。重复观测不算新增独立样本。'],['夹具错误处理','原始正式批次40题次因旧话题引用晚于片段被拒绝，未调用模型。原FAIL完整保留；修正夹具时间后单独补测同样40题次，预期不变。主表选有效执行，工具错误不算AI质量失败。'],['成本','每题费用为该题实际请求费用之和；每题均值按有效遍数。API均费为总费用除以实际HTTP。保守额度与平台实扣另列。'],['价格','官方定价页https://api-docs.deepseek.com/zh-cn/quick_start/pricing/，2026-10-31复核。周末按空闲时段及真实缓存分项估算，不是平台账单。'],['数据与时钟','只有虚拟家庭和合成库存。业务时间固定2026-10-15 10:00上海；计费和HTTP时间用实际时钟。'],['模块与入口','旧模块可算出参考公式不代表当前入口已提供对应事实；当前商品级覆盖/可用量缺口必须保守降级。'],['旧契约','历史半盒扣减只作旧入口兼容回归；当前single-object-1按整件，重量容量属于规格。'],['后端原始结果','415个准备错误不等于415个已执行业务错误；原始FAIL与环境/契约分类分开，跳过列BLOCKED。'],['历史65次失败','逐项关联本轮功能覆盖，未做同原文同前提重放，不宣布原问题已修复。'],['未执行','MuMu、正式服务、PostgreSQL并发/回滚、人工自然度和规则专业审核；P9 Jev不调用，V1.5未开发项不算当前程序失败。'],['范围内修改','仅Garin测试和交接文件，原源码与快照有哈希校验。没有修改生产接口、数据库、团队源码或正确预期。']];
sh['方法说明'].getRange(`A7:B${6+methods.length}`).values=methods;sh['方法说明'].getRange(`A7:B${6+methods.length}`).format={font:{name:'Arial',size:11},rowHeight:62,wrapText:true,verticalAlignment:'center'};sh['方法说明'].getRange('A:A').format.columnWidth=25;sh['方法说明'].getRange('B:B').format.columnWidth=120;
wb.recalculate();const val=c=>over.getRange(c).values[0][0],near=(a,b)=>typeof a==='number'&&Math.abs(a-b)<1e-8;
if(!near(val('B8'),qs.length)||!near(val('B12'),apis.length)||!near(val('B18'),s.known_cost_cny)||!near(val('B14'),s.question_seconds.mean))throw new Error('Workbook/source reconciliation failed');
const fee=val('B18'),rate=apis[0].miss_rate,delta=apis[0].cache_miss_tokens/1000000;
sh['API明细'].getRange('M8').values=[[rate+1]];wb.recalculate();if(!near(val('B18'),fee+delta))throw new Error('Fee dependency recalculation failed');sh['API明细'].getRange('M8').values=[[rate]];wb.recalculate();if(!near(val('B18'),fee))throw new Error('Validation rate was not restored');
await fs.writeFile(path.join(root,'evidence/workbook-validation.json'),JSON.stringify({headlines_match:true,fee_dependency_recalculated_and_restored:true,questions:qs.length,apis:apis.length,fee},null,2));
const scan=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20}});await fs.writeFile(path.join(root,'evidence/workbook-formula-scan.ndjson'),scan.ndjson);
await fs.mkdir(path.join(root,'.qa'),{recursive:true});
for(const [name,range] of [['总览','A1:L41'],['功能覆盖','A1:M16'],['问题清单','A1:H11'],['每题均值','A1:M12'],['逐题执行','A1:N12'],['API明细','A1:P12'],['离线明细','A1:I12'],['方法说明','A1:B18']]){const image=await wb.render({sheetName:name,range,scale:1.2,format:'png'});await fs.writeFile(path.join(root,'.qa',name+'.png'),new Uint8Array(await image.arrayBuffer()));}
const output=path.join(root,'reports/AI各功能专项测试总览.xlsx');await(await SpreadsheetFile.exportXlsx(wb)).save(output);
try{await fs.rename(output+'.inspect.ndjson',path.join(root,'evidence/workbook-export-inspection.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log(JSON.stringify({sheets:names,questions:qs.length,apis:apis.length,output}));
