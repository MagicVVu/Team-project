"""Anonymous public probes with ordinary TLS validation; never reads private data."""
import json
import urllib.error
import urllib.request
from pathlib import Path

origin = 'https://iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
results = []
for path in ['/api/v1/health', '/api/v1/ready', '/api/v1/agent/execution-capabilities', '/api/v1/users/me']:
    row = {'path': path}
    try:
        with opener.open(origin + path, timeout=15) as response:
            row['status'] = response.status
            if path in {'/api/v1/health', '/api/v1/ready'}: row['body'] = json.load(response)
    except urllib.error.HTTPError as error:
        row['status'] = error.code
        error.close()
    except (OSError, ValueError): row['status'] = 'network_or_tls_error'
    results.append(row)
result = {'origin': origin, 'tls_verification_disabled': False, 'login_tested': False, 'observations': results}
target = Path(__file__).resolve().parents[1] / 'reports/p72/evidence/P1-public-checks.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
