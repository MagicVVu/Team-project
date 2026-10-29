"""Final file hashes and secret non-disclosure check, no paid calls."""
import hashlib,json,os
from pathlib import Path
from prepare import ROUND,write
def main():
    excluded={'.snapshot','.runtime','.qa','__pycache__','.pytest_cache'}
    files=[]; found=[]; secret=os.environ.get('DEEPSEEK_API_KEY')
    needles=[secret.encode('utf-8'),secret.encode('utf-16-le')] if secret else []
    for path in sorted(ROUND.rglob('*')):
        rel=path.relative_to(ROUND)
        if not path.is_file() or any(p in excluded for p in rel.parts) or rel.as_posix() in {'evidence/delivery-file-manifest.json','evidence/secret-audit.json'}: continue
        raw=path.read_bytes()
        if any(value and value in raw for value in needles): found.append(rel.as_posix())
        files.append({'path':rel.as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    write(ROUND/'evidence/secret-audit.json',{'key_available_for_exact_match':bool(secret),'matching_files':found,'secret_values_printed':False,'network_calls':0})
    if found: raise RuntimeError('SECRET_FOUND_IN_DELIVERY; do not upload')
    write(ROUND/'evidence/delivery-file-manifest.json',{'files':files,'secret_audit':'no plaintext match' if secret else 'exact-match scan unavailable; manually review before upload'})
    print(json.dumps({'files':len(files),'plaintext_secret_matches':len(found),'exact_match_key_available':bool(secret)}))
if __name__=='__main__':main()
