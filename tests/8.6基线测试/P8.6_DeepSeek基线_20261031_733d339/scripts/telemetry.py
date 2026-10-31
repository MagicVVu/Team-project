"""Observe the original DeepSeek transport without changing prompts or retries."""
import asyncio, contextvars, hashlib, ipaddress, json, socket, time, os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import httpx

CURRENT=contextvars.ContextVar('case',default={})
STAGE=contextvars.ContextVar('stage',default='unknown')
ACTIVE_CALL=contextvars.ContextVar('engine_call',default=None)
def utc(): return datetime.now(timezone.utc).isoformat()
def clean(value):
    if isinstance(value,str):
        secret=os.environ.get('DEEPSEEK_API_KEY')
        return value.replace(secret,'[REDACTED]') if secret else value
    if isinstance(value,dict):
        return {k:('[REDACTED]' if k.lower() in {'authorization','api_key','access_token','refresh_token','password','cookie','set-cookie'} else clean(v)) for k,v in value.items()}
    if isinstance(value,list): return [clean(v) for v in value]
    return value
class Recorder:
    def __init__(self,directory,mode='mock'):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.mode=mode; self.requests=[]; self.extractions=[]; self.seq=0
    def append(self,kind,event):
        with (self.directory/(kind+'.jsonl')).open('a',encoding='utf-8') as f:
            f.write(json.dumps(clean(event),ensure_ascii=False,default=str)+'\n'); f.flush()
    @contextmanager
    def case(self,**metadata):
        token=CURRENT.set(metadata)
        try: yield
        finally: CURRENT.reset(token)
    @contextmanager
    def stage(self,name):
        token=STAGE.set(name)
        try: yield
        finally: STAGE.reset(token)
    @contextmanager
    def install(self):
        from p0.deepseek import DeepSeekEngine
        recorder=self
        original_handle=httpx.AsyncHTTPTransport.handle_async_request
        original_extract=DeepSeekEngine.extract
        async def handle(transport,request):
            if str(request.url)!='https://api.deepseek.com/chat/completions' or request.method!='POST':
                raise RuntimeError('NETWORK_TARGET_BLOCKED')
            recorder.seq+=1; start=time.perf_counter()
            body=await request.aread()
            event={'wire_id':f'http-{recorder.seq:06}','engine_call_id':ACTIVE_CALL.get(),**CURRENT.get(),
                'stage':STAGE.get(),'provenance':recorder.mode,'started_at':utc(),'method':request.method,
                'url':str(request.url),'request_sha256':hashlib.sha256(body).hexdigest(),
                'request':json.loads(body),'http_status':None,'response':None,'usage':None,
                'returned_model':None,'transport_error':None,'complete_body':False}
            try:
                response=await original_handle(transport,request)
                event['http_status']=response.status_code
                event['response_headers']={k:v for k,v in response.headers.items() if k.lower() in {'x-request-id','request-id','date','retry-after','content-type'}}
                raw=await response.aread()
                event['complete_body']=True
                try:
                    data=json.loads(raw); event['response']=data
                    if isinstance(data,dict):
                        event['usage']=data.get('usage'); event['returned_model']=data.get('model')
                except (ValueError,UnicodeError): event['response_text']=raw.decode('utf-8',errors='replace')
                return response
            except BaseException as error:
                event['transport_error']=type(error).__name__; raise
            finally:
                event['latency_ms']=(time.perf_counter()-start)*1000; event['finished_at']=utc()
                recorder.requests.append(event); recorder.append('requests',event)
        async def extract(engine,text):
            ident=f'engine-{len(recorder.extractions)+1:06}-{time.monotonic_ns()}'
            token=ACTIVE_CALL.set(ident); start=time.perf_counter()
            event={'engine_call_id':ident,**CURRENT.get(),'stage':STAGE.get(),'started_at':utc(),'error_code':None}
            try:
                value=await original_extract(engine,text)
                event['parsed_output']=value.model_dump(mode='json') if hasattr(value,'model_dump') else value
                return value
            except BaseException as error:
                event['error_code']=getattr(error,'code',type(error).__name__); raise
            finally:
                event['latency_ms']=(time.perf_counter()-start)*1000
                event['usage']=engine.last_usage; event['returned_model']=engine.last_model
                recorder.extractions.append(event); recorder.append('extractions',event)
                ACTIVE_CALL.reset(token)
        httpx.AsyncHTTPTransport.handle_async_request=handle; DeepSeekEngine.extract=extract
        try: yield self
        finally:
            httpx.AsyncHTTPTransport.handle_async_request=original_handle; DeepSeekEngine.extract=original_extract

@contextmanager
def network_guard(live=False):
    """Permit only DNS for api.deepseek.com and its TCP 443 addresses."""
    dns,connect,connect_ex=socket.getaddrinfo,socket.socket.connect,socket.socket.connect_ex
    allowed=set()
    def lookup(host,port,*args,**kwargs):
        if not live or host not in {'api.deepseek.com',b'api.deepseek.com'} or int(port)!=443:
            raise RuntimeError('NETWORK_DNS_BLOCKED')
        result=dns(host,port,*args,**kwargs)
        allowed.update(row[4][0] for row in result); return result
    def check(address):
        if not live or not isinstance(address,tuple) or address[0] not in allowed or address[1]!=443:
            raise RuntimeError('NETWORK_CONNECTION_BLOCKED')
    def guarded(sock,address): check(address); return connect(sock,address)
    def guarded_ex(sock,address): check(address); return connect_ex(sock,address)
    socket.getaddrinfo=lookup; socket.socket.connect=guarded; socket.socket.connect_ex=guarded_ex
    try: yield
    finally: socket.getaddrinfo=dns; socket.socket.connect=connect; socket.socket.connect_ex=connect_ex
