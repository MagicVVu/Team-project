"""Run native AI checks on frozen source, with external sockets blocked."""
import os,sys
from pathlib import Path
from prepare import ROUND
sys.path.insert(0,str(ROUND/'.snapshot/agent'))
sys.path.insert(0,str(ROUND/'.snapshot'))
from telemetry import network_guard
import pytest
for key in ['DEEPSEEK_API_KEY','TYPESAFE_API_KEY','JEV_RUN_LIVE_SMOKE']:os.environ.pop(key,None)
os.chdir(ROUND/'.snapshot/agent')
with network_guard(False):
    code=pytest.main(['tests','jev/tests','-q','--junitxml='+str(ROUND/'evidence/native-junit.xml'),'--basetemp='+str(ROUND/'.runtime/native-pytest-temp')])
sys.exit(code)
