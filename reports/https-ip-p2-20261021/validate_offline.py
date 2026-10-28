"""LOCAL P2 static checks. NOT nginx -t, no sockets, no app import/deployment."""
import ast
import json
import pathlib
import posixpath
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
rows = json.loads((ROOT/'route-inventory.json').read_text(encoding='utf-8'))
live = json.loads((ROOT/'P2-runtime-routes.json').read_text(encoding='utf-8-sig'))
source_set = {(r['method'],r['path']) for r in rows}
live_set = {(r['method'],r['path']) for r in live['/openapi.json']['operations']}
assert source_set == live_set and len(live_set) == 38, 'Captured runtime/schema mismatch'
entries=[]
for line in (ROOT/'nginx-route-map.conf').read_text(encoding='utf-8').splitlines():
    m = re.fullmatch(r'"~(.+)" ([a-z_]+);', line)
    if m: entries.append((re.compile(m[1]), m[2]))
assert len(entries) == 30


def match(method, path):
    # Model only expected normalized $uri, NOT the entire nginx URI parser.
    uri = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
    uri = posixpath.normpath('/'+uri.lstrip('/'))
    return [label for regex,label in entries if regex.fullmatch(method+':'+uri)]


sample = '12345678-1234-1234-1234-123456789abc'
for row in rows:
    path = re.sub(r'\{[^}]+\}', sample, row['path'])
    expected = [row['label']] if row['allow'] else []
    assert match(row['method'],path) == expected, row
    if row['allow']:
        assert match(row['method'],path+'?token=SYNTHETIC_LOG_SENTINEL') == expected

denied = [
 ('GET','/internal/v1/inventory/search'),
 ('GET','/internal/v1/inventory/batches/'+sample),
 ('GET','/internal/v1/operations/'+sample),
 ('GET','/%69nternal/v1/inventory/search'),
 ('GET','/api/v1/../internal/v1/inventory/search'),
 ('GET','/api/v1/%2e%2e/internal/v1/operations/'+sample),
 ('GET','/api/v1/%2569nternal/v1/inventory/search'),
 ('GET','/docs'),('GET','/docs/oauth2-redirect'),('GET','/redoc'),
 ('GET','/openapi.json'),('GET','/metrics'),('GET','/debug'),('GET','/admin'),
 ('GET','/api/v1/internal/v1/inventory/search'),('GET','/api/v1/unknown'),
 ('POST','/api/v1/auth/register'),('GET','/api/v1/ready'),
 ('POST','/api/v1/agent/reference-messages'),('POST','/api/v1/agent/tasks/'+sample),
 ('GET','/api/v1/auth/login'),('TRACE','/api/v1/health'),('OPTIONS','/api/v1/users/me'),
 ('HEAD','/api/v1/health'),('GET','/api/v1/agent/tasks/not-a-uuid'),
 ('GET','/api/v1/agent/tasks/'+sample+'/anything'),
 ('POST','/api/v1/AUTH/login'),('post','/api/v1/auth/login'),
]
for case in denied: assert not match(*case), case

common = (ROOT/'nginx-http-common.conf').read_text(encoding='utf-8')
log = common[common.index('log_format magicvvu_min'):]
for unsafe in ['$request"','$request_uri','$uri','$args','$http_','$request_body','$remote_addr']:
    assert unsafe not in log, unsafe
for name in ['nginx-http01-server.conf','nginx-magicvvu-api.conf']:
    text=(ROOT/name).read_text(encoding='utf-8')
    assert 'error_log /dev/null crit;' in text
http=(ROOT/'nginx-magicvvu-http-only.conf').read_text(encoding='utf-8')+(ROOT/'nginx-http01-server.conf').read_text(encoding='utf-8')
assert not re.search(r'^\s*(ssl_certificate|proxy_pass|listen 443)',http,re.M)
proxy=(ROOT/'nginx-proxy-common.conf').read_text(encoding='utf-8')
assert 'proxy_pass http://127.0.0.1:8000;' in proxy
assert 'proxy_next_upstream off;' in proxy
assert 'proxy_ignore_client_abort off;' in proxy
for p in ROOT.glob('*.py'): ast.parse(p.read_text(encoding='utf-8-sig'))
assert 'DRAFT_ONLY=1' in (ROOT/'renewal-deploy-hook.DRAFT.sh').read_text(encoding='utf-8')
assert 'DRAFT_ONLY = True' in (ROOT/'cert-monitor.DRAFT.py').read_text(encoding='utf-8')
result={'kind':'offline_static_checks_only','runtime_source_operations':38,'allowed_operations':30,
 'withheld_or_internal':8,'denied_cases':len(denied),'passed':True,
 'not_performed':['nginx -t','nginx runtime proxy/normalization tests','TLS handshake','ACME issuance','Android device tests','server backup/restore execution']}
(ROOT/'P2-offline-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
