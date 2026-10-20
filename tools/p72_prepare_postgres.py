"""Prepare the portable test runtime in this workspace; installs no service."""
import hashlib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
CACHE.mkdir(exist_ok=True)
ARCHIVE = CACHE / 'p72-postgresql.zip'
URL = 'https://get.enterprisedb.com/postgresql/postgresql-17.11-5-windows-x64-binaries.zip'
SHA256 = '80379b2c04d51c30225532e0ae04509899141e9957ed096fe749d7fd9df8f82f'
if not ARCHIVE.exists():
    with urllib.request.urlopen(URL, timeout=40) as response, ARCHIVE.open('wb') as output:
        while block := response.read(1024 * 1024): output.write(block)
if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != SHA256:
    raise RuntimeError('Portable PostgreSQL archive differs from the verified P72 runtime')
destination = (CACHE / 'p72-postgresql').resolve()
with zipfile.ZipFile(ARCHIVE) as archive:
    for name in archive.namelist():
        if not name.startswith(('pgsql/bin/', 'pgsql/lib/', 'pgsql/share/')) or name.endswith('/'):
            continue
        target = (destination / name).resolve()
        if not target.is_relative_to(destination): raise RuntimeError('Unsafe archive member')
        archive.extract(name, destination)
print('Portable PostgreSQL test runtime ready; no service installed')
