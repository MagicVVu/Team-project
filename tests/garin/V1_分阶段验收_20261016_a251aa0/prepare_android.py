"""Copy existing dependency caches to a private Gradle home; no shared writes."""
import json,pathlib,shutil,time
ROOT=pathlib.Path(__file__).resolve().parent
destination=ROOT/'.runtime/gradle-home'
source=pathlib.Path(r'E:\Development\Caches\Gradle')
paths=['wrapper/dists/gradle-9.3.1-bin','caches/modules-2']
counts={}
for rel in paths:
    origin=source/rel;target=destination/rel
    if not origin.exists():continue
    # Windows long-path form avoids failures in long Maven descriptor names.
    long_target=pathlib.Path('\\\\?\\'+str(target.absolute()))
    long_origin=pathlib.Path('\\\\?\\'+str(origin.absolute()))
    shutil.copytree(long_origin,long_target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.lock','*.lck','*.part'))
    files=[p for p in long_target.rglob('*') if p.is_file()];counts[rel]={'files':len(files),'bytes':sum(p.stat().st_size for p in files)}
(ROOT/'evidence/android-cache.json').write_text(json.dumps({'source_read_only':str(source),'private_gradle_home':str(destination),'copied':counts},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts,ensure_ascii=False))
