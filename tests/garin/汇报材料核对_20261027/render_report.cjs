const { chromium } = require('C:/Users/ASUS/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs/promises');
const path = require('node:path');
(async()=>{
 const root='D:/Team_Project/Team-project/tests/garin/汇报材料核对_20261027';
 const out='D:/Team_Project/Team-project/tests/交接文件夹/2026-10-27_汇报截图与测试范围核对';
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,chromiumSandbox:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:900},deviceScaleFactor:1.5});
  await page.route('**/*',route=>route.request().url().startsWith('file:')?route.continue():route.abort());
  await page.goto(pathToFileURL(path.join(root,'report.html')).href,{waitUntil:'load'});
  await page.evaluate(()=>document.fonts.ready);
  const checks=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollHeight:document.documentElement.scrollHeight,imageLoaded:[...document.images].every(x=>x.complete&&x.naturalWidth>0),footer:document.querySelector('footer').getBoundingClientRect().toJSON(),right:document.querySelector('.right').getBoundingClientRect().toJSON(),lastNote:document.querySelector('.note').getBoundingClientRect().toJSON()}));
  if(!checks.imageLoaded || checks.footer.bottom>900 || checks.lastNote.bottom>checks.footer.top) throw new Error(JSON.stringify(checks));
  await page.screenshot({path:path.join(out,'可提交截图_阶段性测试记录.png'),fullPage:false});
  await fs.writeFile(path.join(root,'render-check.json'),JSON.stringify(checks,null,2));
  console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
