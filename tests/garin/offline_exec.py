"""Execute tests with cleared credentials and a socket guard; no external traffic."""
import os, pathlib, runpy, socket, sys

root = pathlib.Path(__file__).resolve().parent
for key in list(os.environ):
    if any(part in key for part in ('API_KEY','TOKEN','BASE_URL','P0_', 'P1_', 'APP_AI_ENGINE', 'LLM_')):
        os.environ.pop(key, None)
os.environ.update(P0_ENGINE='rules', P0_MODE='mock', P1_ENGINE='rules', APP_AI_ENGINE='rules', APP_API_TOKEN='local-development', DEMO_TOKEN='demo-local', PYTHONIOENCODING='utf-8')
def denied(*args, **kwargs):
    raise RuntimeError('Offline test guard: external socket connection blocked')
original_connect = socket.socket.connect
def guarded_connect(sock, address):
    frame = sys._getframe(1)
    # Windows asyncio needs its own connected wakeup pair. Allow exactly that
    # freshly bound pair, not arbitrary loopback servers or databases.
    if (frame.f_code is socket._fallback_socketpair.__code__
            and frame.f_locals.get('csock') is sock
            and address == frame.f_locals['lsock'].getsockname()[:2]):
        return original_connect(sock, address)
    return denied(sock, address)
socket.socket.connect = guarded_connect
socket.socket.connect_ex = denied
socket.create_connection = denied
sys.path[:0] = [str(root / 'source_snapshot'), str(root / 'source_snapshot' / 'agent'), str(root / 'test_package' / 'Agent_Regression_v1')]
mode, *args = sys.argv[1:]
if mode == 'pytest':
    import pytest
    raise SystemExit(pytest.main(args))
elif mode == 'module':
    sys.argv = [args[0], *args[1:]]
    runpy.run_module(args[0], run_name='__main__')
elif mode == 'script':
    path = pathlib.Path(args[0]).resolve()
    sys.path.insert(0, str(path.parent))
    sys.argv = [str(path), *args[1:]]
    runpy.run_path(str(path), run_name='__main__')
else:
    raise SystemExit('mode must be pytest, module or script')
