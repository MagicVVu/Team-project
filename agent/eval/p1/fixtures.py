from p0.domain import DomainError
from p1.schemas import Batch


class FixtureReader:
    """Test/evaluation input only. No server, write operation or runtime seed data."""
    def __init__(self, batches):
        self.batches = {item["id"]: Batch.model_validate(item) for item in batches}
        self.reads = []

    async def search(self, scope, name):
        self.reads.append(("search", name))
        return [batch.model_copy(deep=True) for batch in self.batches.values()
                if name is None or name.casefold() in batch.name.casefold()]

    async def get_batch(self, scope, batch_id):
        self.reads.append(("get", batch_id))
        if batch_id not in self.batches:
            raise DomainError("BATCH_NOT_FOUND", "批次已不存在。", 404)
        return self.batches[batch_id].model_copy(deep=True)

    def snapshot(self):
        return {key: value.model_dump(mode="json") for key, value in self.batches.items()}
