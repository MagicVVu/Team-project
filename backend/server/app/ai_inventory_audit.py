"""Read-only counts of legacy inventory rows incompatible with AI P1.

Runs against currently configured PostgreSQL; outputs only aggregate counts.
Does not normalize or alter any user's inventory.
"""
from collections import Counter

from sqlalchemy import select

from app.database import SessionLocal
from app.models import InventoryItem
from app.services.ai_inventory import IncompatibleInventory, to_p1_batch


def main() -> None:
    problems = Counter()
    total = 0
    with SessionLocal() as db:
        for batch in db.scalars(select(InventoryItem).execution_options(yield_per=200)):
            total += 1
            try:
                to_p1_batch(batch)
            except IncompatibleInventory as error:
                problems[str(error)] += 1
    print(f"AI INVENTORY AUDIT: total_batches={total}, incompatible_batches={sum(problems.values())}")
    for description, count in sorted(problems.items()):
        print(f"  {count} x {description}")
    print("READ-ONLY AUDIT FINISHED; NO DATABASE CHANGES")
    if problems:
        print("ACTION NEEDED: Resolve legacy incompatible fields before enabling AI read queries")


if __name__ == "__main__":
    main()
