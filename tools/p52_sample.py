"""Passive host-side sampler. Never starts helpers in the measured backend."""
import datetime,json,subprocess,time
from pathlib import Path
ROOT=Path('/home/admin/magicvvu-p7-p52-final-20261018/evidence')
names=['magicvvu-p7-execution-20261017-backend-1','magicvvu-p7-execution-20261017-agent-1']
groups={}
for name in names:
    pid=int(subprocess.check_output(['docker','inspect','--format','{{.State.Pid}}',name]))
    cg=next(x.split(':',2)[2] for x in Path(f'/proc/{pid}/cgroup').read_text().splitlines() if x.startswith('0:'))
    groups[name]=Path('/sys/fs/cgroup'+cg)
samples=[]
for i in range(72):
    row={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic':time.monotonic(),'containers':{}}
    row['meminfo']={k:int(v.split()[0])*1024 for k,v in (x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines()) if k in ('MemAvailable','SwapFree','SwapTotal')}
    row['loadavg']=Path('/proc/loadavg').read_text().strip()
    for name,g in groups.items():
        row['containers'][name]={f:(g/f).read_text().strip() for f in ('memory.current','memory.peak','memory.events','memory.swap.current','cpu.stat','pids.current')}
    samples.append(row);(ROOT/'resources.json').write_text(json.dumps(samples,indent=2))
    if row['meminfo']['MemAvailable']<128*1024**2:
        (ROOT/'resource-stop.json').write_text(json.dumps({'reason':'host_available_below_128MiB','sample':row}));break
    if i<71:time.sleep(5)
print(json.dumps({'samples':len(samples)}))
