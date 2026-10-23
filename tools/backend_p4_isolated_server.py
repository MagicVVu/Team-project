"""Test-only DNS mapping for the unchanged agent:8767 gateway allowlist."""
import os
from pathlib import Path
import socket
import sys

assert os.environ.get('P72_LOCAL_EPHEMERAL') == 'yes'
assert os.environ.get('ISOLATED_APP_TEST') == 'yes'
assert os.environ.get('DB_NAME') == 'magicvvu_p7_execution_test'
port = int(os.environ['P4_AGENT_LOOPBACK_PORT'])
assert port == 8767
original = socket.getaddrinfo


def isolated_agent(host, service, *args, **kwargs):
    if host in ('agent', b'agent') and str(service) == '8767':
        return original('127.0.0.1', port, *args, **kwargs)
    return original(host, service, *args, **kwargs)


socket.getaddrinfo = isolated_agent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/server'))
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=int(sys.argv[1]))
