from p0.domain import DomainError
from p2.schemas import Batch


class FixtureReader:
    """Test-only snapshot reader, never loaded by the runtime app factory."""
    def __init__(self, batches):
        self.batches = {b["id"]: Batch.model_validate(b) for b in batches}
        self.reads = []

    async def search(self, scope, name):
        self.reads.append(("search", name))
        return [b.model_copy(deep=True) for b in self.batches.values() if name is None or name.casefold() in b.name.casefold()]

    async def get_batch(self, scope, batch_id):
        self.reads.append(("get", batch_id))
        if batch_id not in self.batches:
            raise DomainError("BATCH_NOT_FOUND", "批次不可访问。", 404)
        return self.batches[batch_id].model_copy(deep=True)

    def snapshot(self):
        return {k: v.model_dump(mode="json") for k, v in self.batches.items()}
