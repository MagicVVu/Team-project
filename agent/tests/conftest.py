"""Do not reuse shared Windows temp paths across sandbox execution identities."""
from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parents[1]
        parent = root / ".cache" / "test-temp"
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = parent / uuid4().hex
