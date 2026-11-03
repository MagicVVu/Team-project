import pathlib,json,hashlib,shutil,subprocess,os,xml.etree.ElementTree as ET
repo=pathlib.Path(r'D:\Team_Project\Team-project')
raw=repo/'tests/garin/V1_分阶段验收_20261016_a251aa0'
mumu=repo/'tests/garin/MuMu_游客本地测试_20261016'
work=repo/'tests/garin/汇报材料核对_20261027'
out=repo/'tests/交接文件夹/2026-10-27_汇报截图与测试范围核对'
if work.exists() or out.exists():raise FileExistsError('Refuse to overwrite prior records')
git=['git','--no-optional-locks','-c','safe.directory='+repo.as_posix(),'-C',str(repo)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
index=repo/'tests/交接文件夹/README.md'
tracked=subprocess.check_output(git+['ls-files','-z']).decode('utf8').split('\0')
protected={p:sha(repo/p) for p in tracked if p and (repo/p).is_file() and repo/p!=index}
work.mkdir();out.mkdir();(out/'原始截图').mkdir()
stat=json.loads((raw/'results/分阶段统计.json').read_text(encoding='utf8'))
android=json.loads((raw/'results/Android结果.json').read_text(encoding='utf8'))
check=json.loads((mumu/'checkpoints/before_background_unconfirmed.json').read_text(encoding='utf8'))
assert stat['pytest'][1]['counts']=={'PASS':464}
assert stat['pytest'][2]['counts']=={'PASS':40}
assert android['testDebugUnitTest']['pass']==17
assert check['item_count']==15 and not check['test_items'] and not check['cloud_session_present']
copied=out/'原始截图/游客手动录入_未确认草稿.png'
shutil.copy2(mumu/'screenshots/032_manual_unit_box.png',copied)
assert sha(copied)==sha(mumu/'screenshots/032_manual_unit_box.png')
shutil.copy2(mumu/'screenshots/009_assistant_open_settled.png',out/'原始截图/游客本地助手.png')
def link(p):return os.path.relpath(p,out).replace('\\','/')
rows=[
('P8后端266通过35跳过','未找到对应记录','你的已执行后端本地测试为40通过；当前本地仓库仍为c27834c/P6，没有P8对应报告。','40项JUnit与Git基线'),
('移动端单元测试32通过','数量不符','已有独立执行记录为17通过，不是32；Android调试构建通过，Lint受依赖阻塞。','Android结果.json与17项JUnit'),
('独立MuMu Android12环境','环境已使用','确有Android12 MuMu安装与操作记录，但属于游客本机测试，不是共享云验收。','installation-result.json与ui_actions.jsonl'),
('注册','App云端未验证','只观察过登录页；本地后端认证测试不能当作MuMu注册流程已完成。','安装报告cloud_login_performed=false'),
('自动登录','未找到执行证据','未记录登录后重启或恢复会话的云端验证。','游客基线cloud_session_present=false'),
('家庭创建','App云端未验证','本地后端有相关权限/家庭规则检查，未完成MuMu创建家庭闭环。','40项后端JUnit与联调待办I-02'),
('库存增删改','本地部分已测','后端本地库存接口已测；MuMu只填写未确认草稿，持久库存仍15条、测试新增0条，不能当成云端增删改通过。','checkpoint before_background_unconfirmed与手动录入截图'),
('购物清单转库存','SQLite本地闭环通过','2盒减0.5盒，再实际购入1.5盒得到合计3盒；尚非App/远程数据库闭环。','backend-reference-flow JUnit与10次合成HTTP记录'),
('远程智能体查询','未找到远程执行证据','AI规则和本地只读契约已测，MuMu助手走游客本地问答，不能冒充远程真实模型调用。','P1/P2/P3/P5规则报告及游客助手截图'),
('登出令牌失效','App云端未验证','本地后端有认证、禁用及过期会话检查；未完成MuMu云端登录后登出、再用旧令牌验证。','test_auth_fail_closed等JUnit与联调待办I-01'),
('完整联合验收仍在进行','尚未完成','可以写待完成/待隔离环境验证，现有证据不能写同一次操作已在App、Agent、Backend、DB全链路一致。','联调待办与当前阶段报告')]
md=['# 第二张图的内容是否都已做过','','结论：按本机现有记录，不能认定都做过，也不能把图中P8和32项成绩登记为Garin实测。本次仅核对已有资料，没有运行新测试。截图第二张下方被截断的内容不在本次判断范围。','','测试记录主要来自2026-10-16，当前本地HEAD为c27834c，最新AI目录为P6；10月27日只是材料汇总日期。没有自动拉取代码或更改队友文件。','','|截图中的表述|核对结论|具体说明|主要依据|','|---|---|---|---|']
md += ['|'+'|'.join(x)+'|' for x in rows]
md += ['','## 第一张图建议放什么','','第一张图要求证明同一次操作在App、Agent、Backend和DB中结果一致。当前只能提交分层测试证据，不能把本地SQLite测试和独立游客截图拼成已完成云端闭环的证明。','','可以放本包的“可提交截图_阶段性测试记录.png”，但它是根据原始日志与未改动MuMu截图排版的汇总图，不是新的测试运行截图；页内已明确标注范围。若老师要求原始模拟器截图，可用“原始截图/游客手动录入_未确认草稿.png”，它证明的是确认前未入库。','','## 可直接替换到汇报中的文字','','> 已完成AI及网关源码回归464项、后端本地测试40项、移动端单元测试17项，以及22项独立专项检查。MuMu Android12已开展游客界面、拉绳及手动输入检查；未确认草稿未写入本机库存。库存采购参考闭环在临时SQLite中通过。共享云业务与App、Agent、Backend、DB的完整一致性验收尚未完成。','','不把原37条旧FAIL、样本REVIEW或BLOCKED改为PASS。已有MuMu后台恢复观察出现桌面重开回登录页，尚未完成重复Activity/启动方式影响排查，不登记恢复通过。','','## 原始证据入口','']
refs=[('分阶段统计',raw/'results/分阶段统计.json'),('后端40项JUnit',raw/'evidence/backend-local/junit.xml'),('Android17项结果',raw/'results/Android结果.json'),('独立采购闭环JUnit',raw/'evidence/backend-reference-flow/junit.xml'),('采购HTTP原始记录',raw/'evidence/backend-special-http.jsonl'),('未确认前库存检查点',mumu/'checkpoints/before_background_unconfirmed.json'),('MuMu操作时间线',mumu/'ui_actions.jsonl'),('安装与环境记录',repo/'tests/garin/android_install_20261016_20261016T132621Z/installation-result.json'),('待完成联调步骤',raw/'联调待办.md'),('旧失败清单',raw/'失败清单.md')]
for title,p in refs:
    assert p.is_file(),p
    md.append(f'- [{title}]({link(p)})')
(out/'第二张图逐项核对.md').write_text('\n'.join(md)+'\n',encoding='utf8')
(out/'README.md').write_text('''# 汇报截图与测试范围核对

汇总日期：2026-10-27。原测试执行日期：2026-10-16；离线测试基线a251aa0。

- [可提交的汇总截图](可提交截图_阶段性测试记录.png)：16比9，适合放入第一张图的展示位，明确标注离线与游客范围。
- [第二张图逐项核对](第二张图逐项核对.md)：哪些做过、哪些仅本地部分验证、哪些缺证据。
- [原始MuMu截图](原始截图/游客手动录入_未确认草稿.png)：未改动的真实模拟器截图，供需要原始界面图片时使用。
- [原始游客助手截图](原始截图/游客本地助手.png)：展示本机问答界面，不能作为远程模型测试证据。

汇总图中的自动化统计与MuMu截图属于分层证据，不代表同一次云端操作。当前没有找到P8后端266通过35跳过或移动端32通过的Garin执行记录。如果P8成绩来自队友，需要提供对应版本和日志并注明来源，不能写成Garin已独立复测通过。
''',encoding='utf8')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Garin 测试记录与验证范围</title><style>
*{box-sizing:border-box}html,body{margin:0;width:1600px;height:900px;overflow:hidden;font-family:"Microsoft YaHei",sans-serif;color:#202c24;background:#fafbf7}body{padding:34px 46px}header{height:112px;display:flex;justify-content:space-between;align-items:start;border-bottom:2px solid #dce5d5}h1{margin:0 0 13px;font-size:38px;letter-spacing:1px}.sub{font-size:18px;color:#5b695e}.tag{background:#e5eddd;color:#405b37;padding:12px 20px;border-radius:10px;font-size:20px;font-weight:600;margin-top:6px}.main{height:679px;display:grid;grid-template-columns:344px 1fr;gap:34px;padding-top:22px}.photo{margin:0;text-align:center}.photo img{height:580px;max-width:100%;object-fit:contain;box-shadow:0 4px 15px #22332216;border:1px solid #d5ddce;border-radius:9px}.photo figcaption{font-size:17px;line-height:1.5;margin-top:9px;color:#4c5e4e}.right{min-width:0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin-bottom:20px}.stat{border:1px solid #d7e1d1;background:#f0f5e9;border-radius:12px;padding:16px 14px}.stat b{font-size:42px;display:block;color:#405d36}.stat span{display:block;font-size:18px;margin:7px 0}.stat small{font-size:14px;color:#5c6a5c}.section{font-size:24px;font-weight:600;margin:14px 0 10px}.proof{background:white;border:1px solid #dbe4d5;padding:18px 20px;border-radius:12px;font-size:21px;line-height:1.65}.proof strong{font-weight:600}.proof .minor{font-size:17px;color:#5d6b60}.flow{font-size:22px;line-height:1.7;padding:12px 0 8px}.flow span{font-size:17px;color:#5d6b60;display:block}.pending{border-top:1px solid #d8e1d1;padding-top:13px;font-size:19px;line-height:1.65;color:#695435}.note{font-size:15px;color:#697269;line-height:1.6;margin-top:9px}footer{font-size:16px;line-height:1.5;color:#485d46;border-top:1px solid #dbe4d3;padding-top:10px}footer strong{color:#354c32}</style>
<header><div><h1>Garin 测试记录与验证范围</h1><div class="sub">测试执行 2026-10-16　｜　材料汇总 2026-10-27　｜　离线基线 a251aa0</div></div><div class="tag">阶段性验证 · 未完成云端联合验收</div></header>
<main class="main"><figure class="photo"><img src="raw-mumu.png"><figcaption>MuMu Android 12 · 游客手动录入<br>原始模拟器截图，未确认草稿</figcaption></figure><section class="right"><div class="stats"><div class="stat"><b>464</b><span>源码回归通过</span><small>AI及网关 · 规则模式</small></div><div class="stat"><b>40</b><span>后端本地通过</span><small>临时SQLite环境</small></div><div class="stat"><b>17</b><span>移动端单测通过</span><small>Android构建亦通过</small></div><div class="stat"><b>22</b><span>独立专项通过</span><small>对应24条观察记录</small></div></div>
<div class="section">本机操作证据　确认前不改变库存</div><div class="proof"><strong>录入草稿：</strong>GarinTestMilk1016　／　2 box<br><strong>持久库存：</strong>15条；新增测试物品 0条<br><strong>数据校验：</strong>原15条记录无变化，云端登录会话不存在<div class="minor">依据：032_manual_unit_box.png 与 before_background_unconfirmed.json</div></div>
<div class="section">另已验证　库存与采购的本地接口闭环</div><div class="flow">新增2盒 → 消耗0.5盒 → 实购1.5盒 → 合计3盒<span>独立SQLite测试通过；已检查重复请求、旧版本冲突及家庭权限。</span></div>
<div class="pending"><strong>仍待验证：</strong>共享云注册/自动登录、远程模型查询、云端登出失效，以及同一操作在App → Agent → Backend → DB中的一致性。</div><div class="note">AI 464项为补齐副本后的复跑；首轮失败及37条旧FAIL保留。Lint受依赖阻塞。<br>左侧与右侧为分层证据，不是同一轮云端闭环，统计不跨组相加。</div></section></main>
<footer><strong>汇报结论：</strong>离线功能与游客本地检查已有证据；完整联合验收尚未完成。本页依据既有记录排版，非10月27日重新执行。</footer></html>'''
(work/'report.html').write_text(html,encoding='utf8');shutil.copy2(copied,work/'raw-mumu.png')
manifest={'assembled_date':'2026-10-27','original_execution_date':'2026-10-16','current_local_head':subprocess.check_output(git+['rev-parse','HEAD'],encoding='utf8').strip(),'test_baseline':stat['baseline'],'new_tests_executed':False,'p8_claim_verified':False,'source_files':{str(p.relative_to(repo)):sha(p) for _,p in refs},'original_screenshot_sha256':sha(copied),'image_description':'Browser-rendered evidence summary with untouched original MuMu screenshot; not an AI-generated or newly executed test screenshot'}
(work/'source-record.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
(out/'来源与范围.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
(work/'.gitignore').write_text('.render-cache/\n',encoding='utf8')
index.write_text(index.read_text(encoding='utf8')+'\n## 汇报材料核对\n\n[2026-10-27 汇报截图与测试范围核对](2026-10-27_汇报截图与测试范围核对/README.md)：仅汇总已有证据，未将P8截图中的成绩登记为个人实测。\n',encoding='utf8')
assert all(sha(repo/p)==v for p,v in protected.items()),'Unexpected modification outside owned index'
print(json.dumps({'work':str(work),'output':str(out),'protected_tracked_files_unchanged':len(protected)},ensure_ascii=False))
