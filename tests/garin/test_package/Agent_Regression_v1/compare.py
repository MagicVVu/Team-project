import sys,json,pathlib,collections
if len(sys.argv)!=3:raise SystemExit('Usage: python compare.py OLD_REPORT_DIR NEW_REPORT_DIR')
a,b=map(pathlib.Path,sys.argv[1:]);sa=json.loads((a/'summary.json').read_text(encoding='utf-8'));sb=json.loads((b/'summary.json').read_text(encoding='utf-8'))
if sa['case_hashes']!=sb['case_hashes']:raise SystemExit('用例或范围不同，不能直接比较分数；先统一套件版本和范围。')
if (sa['engine'],sa['adapter'])!=(sb['engine'],sb['adapter']):print('注意：引擎或适配器不同，结果不是同环境回归。')
def index(p):
 d=collections.defaultdict(set)
 for line in (p/'results.jsonl').read_text(encoding='utf-8').splitlines():
  r=json.loads(line);d[r['id']].add(r['status'])
 return d
x,y=index(a),index(b)
for i in sorted(x.keys() & y.keys()):
 if x[i]=={'PASS'} and y[i]!={'PASS'}:print('退步',i,sorted(y[i]))
 elif x[i]!={'PASS'} and y[i]=={'PASS'}:print('修复',i)
print('旧统计',sa['counts']);print('新统计',sb['counts'])
if sa['repeat']!=sb['repeat']:print('重复次数不同，稳定性结论不能直接等同比较。')
