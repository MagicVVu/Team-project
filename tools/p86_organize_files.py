"""One-time local P8.6 filing; move evidence without rewriting its contents."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MOVES={
    'docs/ai-autonomous':'docs/versions/V1-P8.6',
    'reports/ai-autonomous':'reports/p86-autonomous/initial-20261029',
    'reports/runtime-adaptation-20261030':'reports/p86-autonomous/adaptation-20261030',
}
REPORT=ROOT/'reports/p86-autonomous/organization-20261030'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def relocate(path):
    for before,after in MOVES.items():
        origin=ROOT/before
        if path==origin or path.is_relative_to(origin):return ROOT/after/path.relative_to(origin)
    return path


def main():
    if (REPORT/'relocation.json').exists():raise SystemExit('Already organized; verify instead of moving again')
    # Check every absolute source/destination remains in this workspace.
    for before,after in MOVES.items():
        origin,target=(ROOT/before).resolve(),(ROOT/after).resolve()
        assert origin.is_relative_to(ROOT) and target.is_relative_to(ROOT)
        assert origin.is_dir() and not target.exists(),(before,after)
    evidence=[]
    for before in MOVES:
        for path in sorted((ROOT/before).rglob('*')):
            if path.is_file():evidence.append({'from':path.relative_to(ROOT).as_posix(),
                'to':relocate(path).relative_to(ROOT).as_posix(),'sha256_before':digest(path.read_bytes())})
    pages={p:p.read_text(encoding='utf-8') for p in (ROOT/'docs').rglob('*.md')}
    index=subprocess.check_output(['git','ls-files','--stage','-z'],cwd=ROOT)
    for before,after in MOVES.items():
        target=ROOT/after;target.parent.mkdir(parents=True,exist_ok=True)
        (ROOT/before).rename(target)
    changed=[]
    for original,body in pages.items():
        destination=relocate(original)
        def link(match):
            value=match[1]
            if value.startswith(('#','https:','http:','mailto:','codex:')):return match[0]
            path,mark,fragment=value.partition('#')
            target=(original.parent/path).resolve()
            moved=relocate(target)
            if original==destination and moved==target:return match[0]
            replacement=Path(os.path.relpath(moved,destination.parent)).as_posix()
            return ']('+replacement+(mark+fragment if mark else '')+')'
        updated=re.sub(r'\]\(([^)]+)\)',link,body)
        if updated!=body:
            destination.write_text(updated,encoding='utf-8');changed.append(destination.relative_to(ROOT).as_posix())
    # Keep module/tool names stable; only their filing destinations change.
    consumers=[*(ROOT/'tools').glob('autonomous*.py'),*(ROOT/'tools').glob('runtime_adaptation*.py'),
        ROOT/'agent/eval/autonomous/run.py',ROOT/'backend/server/tests/test_session_memory.py']
    for path in consumers:
        body=path.read_text(encoding='utf-8')
        for before,after in MOVES.items():body=body.replace(before,after)
        path.write_text(body,encoding='utf-8')
    # Previous links from chats keep a small pointer, with one canonical copy.
    old=ROOT/'docs/ai-autonomous';old.mkdir()
    for name in ('README.md','工作记录.md','前后端交接说明.md','评测记录.md','2026-10-30-服务器核对与适配记录.md'):
        (old/name).write_text('# V1-P8.6 归档入口\n\n自主循环工作已定义为 **V1-P8.6**，'
            '正文与契约统一在版本目录维护。\n\n'
            f'请查看 [V1-P8.6 对应文档](../versions/V1-P8.6/{name}) 和 '
            '[阶段总入口](../versions/V1-P8.6/README.md)。本目录仅保留旧链接跳转。\n',encoding='utf-8')
    REPORT.mkdir(parents=True)
    value={'stage':'V1-P8.6','date':'2026-10-30','moves':MOVES,'files':evidence,
        'markdown_links_updated':changed,'git_index_sha256':digest(index),'git_index_changed':False,
        'raw_report_contents_changed':False,'deployed':False,'committed':False,'pushed':False}
    assert subprocess.check_output(['git','ls-files','--stage','-z'],cwd=ROOT)==index
    (REPORT/'relocation.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stage':'V1-P8.6','moved_files':len(evidence),'pages_relinked':len(changed),'git_index_changed':False}))


if __name__=='__main__':main()
