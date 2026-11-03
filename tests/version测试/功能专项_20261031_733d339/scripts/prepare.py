"""Freeze tracked source, read stage documents, and preserve original working files."""
import hashlib,json,pathlib,shutil,subprocess,sys,zipfile
from xml.etree import ElementTree as ET
ROUND=pathlib.Path(__file__).resolve().parents[1];REPO=ROUND.parents[2]
HEAD='733d339ee5bbb73635413902cdd0d07d43a6075a'
OLD=REPO/'tests/8.6基线测试/P8.6_DeepSeek基线_20261031_733d339'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def main():
 if (ROUND/'evidence/source.json').exists():print('Frozen source retained');return
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==HEAD
 paths=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf-8').split('\0');protected=[];frozen=[]
 for name in filter(None,paths):
  src=REPO/name
  if not src.is_file():continue
  if name!='tests/交接文件夹/README.md' and not name.startswith('tests/version测试/'):protected.append({'path':name,'sha256':sha(src)})
  if name.startswith(('agent/','backend/','docs/versions/','docs/handoffs/','deploy/','tools/')) or name in {'README.md','.gitignore'}:
   if any(t in {'.env','.cache','__pycache__','node_modules','.git','credentials'} for t in pathlib.Path(name).parts):continue
   target=ROUND/'.snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target);frozen.append({'path':name,'sha256':sha(src)})
 for folder in ['datasets','runs','reports','stages','evidence','.runtime']: (ROUND/folder).mkdir(exist_ok=True)
 write(ROUND/'evidence/source.json',{'head':HEAD,'protected':protected,'snapshot':frozen})
 docs=[];ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
 for p in sorted((ROUND/'.snapshot/docs/versions').rglob('*')):
  if p.is_dir():continue
  text='';kind=p.suffix.lower()
  if kind=='.md':text=p.read_text(encoding='utf-8-sig')
  elif kind=='.docx':
   with zipfile.ZipFile(p) as z:
    root=ET.fromstring(z.read('word/document.xml'));text='\n'.join(''.join(t.itertext()) for t in root.findall('.//w:p',ns))
  elif kind=='.json':text=json.dumps(json.loads(p.read_text(encoding='utf-8-sig')),ensure_ascii=False)
  else:continue
  docs.append({'path':p.relative_to(ROUND/'.snapshot').as_posix(),'sha256':sha(p),'kind':kind,'characters_read':len(text),'headings':[line.strip() for line in text.splitlines() if line.startswith('#')][:60]})
  if kind in {'.md','.docx'}:
   dest=ROUND/'evidence/document-text'/p.relative_to(ROUND/'.snapshot/docs/versions');dest=dest.with_suffix(dest.suffix+'.txt');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
 write(ROUND/'evidence/documents-read.json',docs)
 for name in ['telemetry.py','analyze.py']:
  shutil.copy2(OLD/'scripts'/name,ROUND/'scripts'/('baseline_analysis.py' if name=='analyze.py' else name))
 (ROUND/'.gitignore').write_text('.snapshot/\n.runtime/\n.qa/\nnode_modules/\n__pycache__/\n.pytest_cache/\n*.pyc\n',encoding='utf-8')
 write(ROUND/'evidence/pricing.json',{'verified_date':'2026-10-31','official_url':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/','model':'deepseek-flash','peak_per_million_cny':{'hit':'.04','miss':'2','output':'8'},'offpeak_per_million_cny':{'hit':'.02','miss':'1','output':'4'},'budget_uses_peak_cache_miss':True,'search_fetch_disabled':True,'invoice_checked':False})
 print(json.dumps({'source':HEAD,'protected':len(protected),'snapshot':len(frozen),'documents_read':len(docs)},ensure_ascii=False))
if __name__=='__main__':main()
