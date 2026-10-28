package com.example.teamapp.data

import androidx.compose.runtime.mutableStateMapOf
import java.math.BigDecimal
import java.time.LocalDate
import java.util.UUID

/** Session-only UI data. Phase 2 must define a server identity and allocation protocol first. */
internal data class InventoryPreviewRecord(
    val id: String,
    val itemId: String,
    val location: String,
    val expiryDate: String?,
    val openedAt: String?,
    val batchId: String,
    val source: PreviewSource,
    // Always ONE in piece mode. Measured/legacy quantities stay exact and aggregated.
    val quantity: BigDecimal = BigDecimal.ONE
)

internal enum class PreviewSource { EXISTING, RECEIPT }

internal data class InventoryPreview(
    val baseline: StockItem,
    val individual: Boolean,
    val records: List<InventoryPreviewRecord>,
    val locallyModified: Boolean = false,
    // Keep receipt identities even after every record from a receipt has been consumed.
    val receivedBatchIds: Set<String> = emptySet()
) {
    val total: BigDecimal get() = if (individual) records.size.toBigDecimal()
        else records.fold(BigDecimal.ZERO) { sum, record -> sum + record.quantity }
    val hasReceipts get() = records.any { it.source == PreviewSource.RECEIPT }
    fun originalChanged(item: StockItem) = baseline.previewFacts() != item.previewFacts()
}

private fun StockItem.previewFacts() = listOf(quantityText, unit, location, expiry, openedAt, lifecycleStatus)
internal fun BigDecimal.previewText(): String = stripTrailingZeros().toPlainString()

/** Unknown units are deliberately aggregated; a whole number alone does not imply pieces. */
internal fun StockItem.hasPieceUnit() = InventoryContract.unit(unit) in setOf("盒", "瓶", "包", "袋", "个", "卷", "片", "台") || unit.trim() == "件"

internal class InventoryPreviewStore {
    companion object {
        // Bound prototype memory usage; unusually large existing stock remains exact aggregate data.
        const val MAX_PIECES = 10_000
    }
    private data class Key(val scope: String, val itemId: String)
    private val previews = mutableStateMapOf<Key, InventoryPreview>()

    fun preview(scope: String, item: StockItem): InventoryPreview {
        val key = Key(scope, item.id)
        val previous = previews[key]
        // Before any preview mutation, ordinary saved-stock changes can refresh the snapshot.
        // Once locally modified, retain it and disclose differences; never guess piece allocation.
        if (previous != null && (previous.locallyModified || previous.hasReceipts || !previous.originalChanged(item))) return previous
        return initialize(item).also { previews[key] = it }
    }

    fun amount(item: StockItem, input: String, preview: InventoryPreview): BigDecimal? {
        if (item.unit != preview.baseline.unit) return null
        val amount = InventoryContract.amount(input, positive = true) ?: return null
        if (item.hasPieceUnit() && (amount.stripTrailingZeros().scale() > 0 || '.' in input)) return null
        if (preview.individual && amount > (MAX_PIECES - preview.records.size).toBigDecimal()) return null
        return amount
    }

    /** Idempotent per dialog. No StockItem creation, persistence, history or network writes. */
    fun receive(scope: String, item: StockItem, input: String, expiry: LocalDate?, batchId: String): Boolean {
        if (!item.activeBatch) return false
        val current = preview(scope, item)
        if (batchId in current.receivedBatchIds || current.records.any { it.batchId == batchId }) return false
        val amount = amount(item, input, current) ?: return false
        val records = List(if (current.individual) amount.intValueExact() else 1) {
            InventoryPreviewRecord(UUID.randomUUID().toString(), item.id, item.location, expiry?.toString(),
                null, batchId, PreviewSource.RECEIPT, if (current.individual) BigDecimal.ONE else amount)
        }
        previews[Key(scope, item.id)] = current.copy(records = current.records + records, locallyModified = true,
            receivedBatchIds = current.receivedBatchIds + batchId)
        return true
    }

    /** Only these three fields are editable; unchanged legacy dates can be retained verbatim. */
    fun updateRecord(scope: String, itemId: String, recordId: String, location: String,
        expiryDate: String?, openedAt: String?): Boolean = changeRecord(scope, itemId, recordId) { record ->
        val expiry = expiryDate?.takeIf { it.isNotBlank() }
        val opened = openedAt?.takeIf { it.isNotBlank() }
        fun valid(value: String?, old: String?) = value == null || value == old || runCatching { LocalDate.parse(value) }.isSuccess
        if (location.isBlank() || !valid(expiry, record.expiryDate) || !valid(opened, record.openedAt)) null
        else record.copy(location = location.trim(), expiryDate = expiry, openedAt = opened)
    }

    fun markOpened(scope: String, itemId: String, recordId: String, today: LocalDate = LocalDate.now()): Boolean =
        changeRecord(scope, itemId, recordId) { record ->
            if (record.openedAt != null) null else record.copy(openedAt = today.toString())
        }

    /** Called only after the UI exit transition completes. Never maps to cloud consumption. */
    fun consumeRecord(scope: String, itemId: String, recordId: String): Boolean {
        val key = Key(scope, itemId)
        val current = previews[key] ?: return false
        if (!current.individual || current.records.none { it.id == recordId && it.itemId == itemId && it.quantity == BigDecimal.ONE }) return false
        previews[key] = current.copy(records = current.records.filterNot { it.id == recordId }, locallyModified = true)
        return true
    }

    private fun changeRecord(scope: String, itemId: String, recordId: String,
        change: (InventoryPreviewRecord) -> InventoryPreviewRecord?): Boolean {
        val key = Key(scope, itemId)
        val current = previews[key] ?: return false
        if (!current.individual) return false
        val record = current.records.firstOrNull { it.id == recordId && it.itemId == itemId && it.quantity == BigDecimal.ONE } ?: return false
        val updated = change(record) ?: return false
        if (updated != record) previews[key] = current.copy(
            records = current.records.map { if (it.id == recordId) updated else it }, locallyModified = true)
        return true
    }

    private fun initialize(item: StockItem): InventoryPreview {
        val amount = item.quantityText.toBigDecimalOrNull()?.takeIf { it >= BigDecimal.ZERO } ?: BigDecimal.ZERO
        val individual = item.hasPieceUnit() && amount.stripTrailingZeros().scale() <= 0 && amount <= MAX_PIECES.toBigDecimal()
        val count = if (amount.signum() == 0) 0 else if (individual) amount.intValueExact() else 1
        val batch = "existing:${item.id}"
        return InventoryPreview(item, individual, List(count) { index ->
            InventoryPreviewRecord("$batch:$index", item.id, item.location, item.expiry.takeIf { it.isNotBlank() },
                item.openedAt.takeIf { it.isNotBlank() }, batch, PreviewSource.EXISTING,
                if (individual) BigDecimal.ONE else amount)
        })
    }
}
