package com.example.teamapp.data

/** One durable confirmation envelope for every view of the same draft. */
internal object DraftConfirmations {
    fun owner(entries: List<AssistantEntry>, item: AssistantEntry): AssistantEntry? {
        if (item.draftId.isBlank()) return null
        val saved = entries.filter { it.draftId == item.draftId && it.commitBody.isNotBlank() }
        check(saved.map { it.commitBody }.distinct().size <= 1) { "这份草稿存在不同的历史确认，请先核实回执，不能重新提交" }
        return saved.firstOrNull()
    }

    fun sameVersion(left: AssistantEntry, right: AssistantEntry) = left.draftId.isNotBlank() &&
        left.draftId == right.draftId && left.taskId == right.taskId && left.taskRevision == right.taskRevision &&
        left.draftRevision == right.draftRevision && left.action == right.action

    fun share(entries: List<AssistantEntry>): List<AssistantEntry> = entries.map { item ->
        val owners = entries.filter { it.draftId.isNotBlank() && it.draftId == item.draftId && it.commitBody.isNotBlank() }
        // Preserve conflicting legacy records for explicit receipt verification.
        if (owners.map { it.commitBody }.distinct().size != 1) item else {
            val owner = owners.firstOrNull { sameVersion(it, item) }
            val receipt = owners.firstOrNull { sameVersion(it, item) && it.receipt.isNotBlank() }
            if (owner == null) item else item.copy(commitBody = owner.commitBody,
                receipt = receipt?.receipt ?: item.receipt,
                state = when {
                    receipt != null -> AssistantStatus.COMMITTED
                    item.commitBody.isBlank() -> owner.state
                    else -> item.state
                }, refreshNeeded = receipt?.refreshNeeded ?: item.refreshNeeded)
        }
    }
}
