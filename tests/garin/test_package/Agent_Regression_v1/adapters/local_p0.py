"""Runs only an isolated in-process P0 mock. Never connects to real business DB."""
import asyncio,copy,json,os

def evaluate(case,config):
    if case['kind']=='scenario':raise NotImplementedError('scenario driver not implemented; no production environment attached')
    from p0.mock import MockBackend
    from p0.schemas import Message,Scope
    from p0.manager import Manager
    from p0.engines import RuleEngine
    from p0.deepseek import DeepSeekEngine
    if case['fixture']!='seed-v1':raise NotImplementedError('unknown fixture')
    if case['kind']=='flow':return flow(case)
    store=MockBackend()
    def snapshot():
        return json.loads(json.dumps(store.state,default=lambda v:v.model_dump(mode='json') if hasattr(v,'model_dump') else str(v)))
    before=snapshot()
    engine=RuleEngine() if config['engine']=='rules' else DeepSeekEngine()
    result=asyncio.run(Manager(engine,store).handle(Message(text=case['text'],request_id=case['id']),Scope(**case['scope'])))
    return dict(result=result.model_dump(mode='json'),before=before,after=snapshot(),execution='local MockBackend + '+config['engine'])

def flow(case):
    # The HTTP contract is exercised, but backend is still MockBackend.
    os.environ['P0_ENGINE']='rules'
    os.environ['P0_MODE']='mock'
    from p0.app import create_app
    from fastapi.testclient import TestClient
    app=create_app('mock');captures={};failures=[];evidence=[]
    def resolve(x):
        if isinstance(x,str):
            if x.startswith('$') and x[1:] in captures:return captures[x[1:]]
            for k,v in captures.items():x=x.replace('{'+k+'}',str(v))
            return x
        if isinstance(x,list):return [resolve(y) for y in x]
        if isinstance(x,dict):return {k:resolve(v) for k,v in x.items()}
        return x
    def at(obj,path):
        for k in path.split('.'):obj=obj[int(k)] if isinstance(obj,list) else obj[k]
        return obj
    with TestClient(app) as client:
        for i,s in enumerate(case['steps'],1):
            headers={'Authorization':'Bearer '+os.getenv('DEMO_TOKEN','demo-local')}
            if s.get('auth')=='other':headers['Authorization']='Bearer demo-other-household'
            if s.get('auth')=='none':headers={}
            headers.update(resolve(s.get('headers',{})))
            if s.get('inject_event_failure'):app.state.store.fail_event_once=True
            before=copy.deepcopy(app.state.store.state)
            kwargs={'headers':headers}
            if 'body' in s:kwargs['json']=resolve(s['body'])
            response=client.request(s['method'],resolve(s['path']),**kwargs);body=response.json()
            def snapshot(value):
                return json.loads(json.dumps(value,default=lambda v:v.model_dump(mode='json') if hasattr(v,'model_dump') else str(v)))
            row={'step':i,'request':{'method':s['method'],'path':resolve(s['path']),'body':kwargs.get('json'),'auth_mode':s.get('auth','default')},'http':response.status_code,'body':body,'before':snapshot(before),'after':snapshot(app.state.store.state)}
            if response.status_code not in s.get('http',[200]):failures.append(f'step {i}: HTTP {response.status_code}')
            for path,expected in s.get('assert',{}).items():
                try:
                    from run import same
                    if not same(at(body,path),resolve(expected),path.rsplit('.',1)[-1]):failures.append(f'step {i}: {path} mismatch')
                except (KeyError,TypeError,IndexError):failures.append(f'step {i}: missing {path}')
            for k,path in s.get('capture',{}).items():
                try:captures[k]=at(body,path)
                except (KeyError,TypeError,IndexError):raise RuntimeError(f'step {i}: cannot capture {path}')
            delta=len(app.state.store.state['events'])-len(before['events']);row['event_delta']=delta
            if delta!=s.get('event_delta',0):failures.append(f'step {i}: event delta {delta}')
            if s.get('inventory_unchanged',s.get('event_delta',0)==0) and before['batches']!=app.state.store.state['batches']:failures.append(f'step {i}: unexpected inventory change')
            if s.get('all_state_unchanged') and before!=app.state.store.state:failures.append(f'step {i}: rollback/state changed')
            evidence.append(row)
    return dict(failures=failures,steps=evidence,execution='in-process HTTP + mock database; no real LLM')
