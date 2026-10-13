import json
from pathlib import Path


def test_dataset_size_provenance_split_and_unique_text():
    path = Path(__file__).resolve().parents[1]/"eval/samples.jsonl"
    samples = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
    assert len(samples) == 150
    assert len(set(s["text"] for s in samples)) == 150
    assert sum(s["split"]=="dev" for s in samples) == 90
    assert sum(s["split"]=="test" for s in samples) == 60
    dev_groups={s["group_id"] for s in samples if s["split"]=="dev"}
    test_groups={s["group_id"] for s in samples if s["split"]=="test"}
    assert not dev_groups & test_groups
    assert all(s["source"]=="ai_constructed" and not s["human_reviewed"] for s in samples)
