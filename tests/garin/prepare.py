"""Copy only test-relevant source files; never copy secrets or live data."""
import argparse, datetime, hashlib, json, pathlib, shutil, subprocess

ROOT = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', default=r'D:\Team_Project\Team-project')
SOURCE = pathlib.Path(parser.parse_args().source).resolve()
DEST = ROOT / 'source_snapshot'
if DEST.exists():
    archive = ROOT / 'source_snapshots_archive' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    assert DEST.resolve().is_relative_to(ROOT) and archive.resolve().is_relative_to(ROOT)
    archive.parent.mkdir(exist_ok=True)
    shutil.move(str(DEST), str(archive))
files = {}
for section in ('agent', 'backend', 'docs', 'frontend'):
    for path in (SOURCE / section).rglob('*'):
        rel = path.relative_to(SOURCE)
        if not path.is_file() or any(p in {'.git', '.cache', '.venv', '__pycache__', 'build', '.gradle', 'results'} for p in rel.parts):
            continue
        if path.name.startswith('.env') or path.name == 'local.properties':
            continue
        if path.suffix not in {'.py', '.md', '.txt', '.toml', '.json', '.jsonl', '.kt', '.kts', '.xml', '.properties'}:
            continue
        target = DEST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory='+SOURCE.as_posix(), '-C', str(SOURCE), *args], encoding='utf-8').strip()
archives = [pathlib.Path(r'D:\下载\Garin_AI_Agent_回归测试包_v1.0.zip'), pathlib.Path(r'F:\微信聊天记录\xwechat_files\wxid_mq05ma6m9ko712_f29f\msg\file\2026-10\V0-p0(1).zip')]
metadata = {'source_path': str(SOURCE), 'commit': git('rev-parse','HEAD'), 'branch': git('branch','--show-current'), 'original_status': git('status','--short'), 'snapshot_hashes': files, 'archive_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in archives if p.exists()}, 'excluded': ['secrets', 'caches', 'live data', 'previous result directories', 'build output'], 'snapshot_is_local_checkout': True}
(ROOT / 'source_manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
(ROOT / 'evidence').mkdir(exist_ok=True)
if pathlib.Path(r'D:\下载\先读我_150条核查.md').exists():
    shutil.copy2(r'D:\下载\先读我_150条核查.md', ROOT / 'evidence' / '先读我_150条核查.md')
print('snapshot:', DEST, 'files:', len(files), 'commit:', metadata['commit'])
