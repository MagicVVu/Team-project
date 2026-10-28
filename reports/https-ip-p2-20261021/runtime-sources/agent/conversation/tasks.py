from interaction.tasks import (Task as BaseTask, TaskClient as BaseClient, PublicClarification,
                               parse_task as base_parse_task, Draft)
from .schemas import AgentResult


class PublicResult(AgentResult):
    clarification: PublicClarification | None = None


class Task(BaseTask):
    result: PublicResult | None


class TaskClient(BaseClient):
    task_type = Task


def parse_task(value, household_id):
    return base_parse_task(value, household_id, task_type=Task)
