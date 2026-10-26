"""Read-only confirmation diagnostics. Automatic commits remain closed.

Reads the saved proposal, not client-supplied replacement evidence. Comparison
uses a fresh consistent snapshot and never turns an unknown risk into approval.
"""
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError
from app.execution_schemas import PlanFields
from app.services import draft_execution as execution, planning_context, ledger


def inspect(db, identity, draft_id, body):
    task, draft = execution.owned(db, identity, draft_id)
    execution.revision(task, draft, body)
    execution.pending(task, draft)
    from app.execution_models import DraftDecision
    if db.get(DraftDecision, draft_id) is not None:
        execution.fail('DRAFT_ALREADY_DECIDED')
    if execution.expiry(task, draft) <= execution.now():
        execution.fail('DRAFT_EXPIRED')
    if draft.command_json.get('action') != 'PLAN_ADD' or not execution.automated_plan(task):
        execution.fail('AUTOMATIC_PLAN_REQUIRED', 422)
    if not set(body.edits).issubset({'quantity', 'unit'}):
        execution.fail('PROTECTED_OR_UNKNOWN_FIELD', 422)
    raw = {**draft.command_json, **body.edits}
    try:
        fields = PlanFields.model_validate({k: v for k, v in raw.items() if k not in {'name', 'action'}})
        execution.converted(fields.quantity, fields.unit, draft.command_json['unit'])
    except (ValidationError, KeyError, TypeError):
        execution.fail('INVALID_DRAFT_FIELDS', 422)
    basis = (task.result_json or {}).get('planning_basis')
    current = planning_context.snapshot(db, identity.user.id, task.household_id, with_provenance=True)
    expected = current['provenance']['revalidation_basis']
    mismatches = []
    if not isinstance(basis, dict) or set(basis) != set(expected):
        mismatches.append('BASIS_MISSING_OR_UNSUPPORTED')
    else:
        mismatches.extend(key for key in expected if expected[key] != basis[key])
    if not current['data']['pending_complete']:
        mismatches.append('PENDING_ASSOCIATION_UNKNOWN')
    source = (task.result_json or {}).get('procurement_source')
    if not source:
        mismatches.append('PROCUREMENT_SOURCE_REQUIRED')
    else:
        try:
            execution.procurement_source(db, task, raw)
        except Exception as error:
            from fastapi import HTTPException
            if not isinstance(error, HTTPException):
                raise
            mismatches.append('PROCUREMENT_SOURCE_INVALID_OR_CHANGED')
    # Rule registry approval and stock/coverage freshness are independent gates.
    blockers = ['AUTOMATIC_PLANNING_NOT_APPROVED', 'RISK_RULE_REVIEW_REQUIRED']
    if source:
        from uuid import UUID
        from app.product_models import ProductBatch
        try:
            linked = db.get(ProductBatch, UUID(source['batch_id']))
        except (KeyError, ValueError, TypeError):
            linked = None
        if linked is None:
            blockers.append('PRODUCT_IDENTITY_REQUIRED')
    for item in current['data']['items']:
        if item['stock_verification'] is None:
            blockers.append('STOCK_VERIFICATION_REQUIRED')
        else:
            at = datetime.fromisoformat(str(item['stock_verification']['checked_at']))
            if execution.aware(at) < execution.now()-timedelta(hours=24):
                blockers.append('STOCK_VERIFICATION_STALE')
        if not item['coverage']:
            blockers.append('CONSUMPTION_COVERAGE_UNKNOWN')
        if any(not d['records_complete'] or d['unexplained_adjustment'] for d in item['coverage']):
            blockers.append('CONSUMPTION_COVERAGE_INCOMPLETE')
    return {'protocol_version': 'planning-revalidation-1', 'draft_id': str(draft.id),
        'status': 'stale' if mismatches else 'blocked', 'mismatches': mismatches,
        'blockers': sorted(set(blockers)), 'current_basis': expected,
        'original_suggestion': draft.command_json, 'effective_request': raw,
        'effective_request_hash': ledger.digest(raw), 'user_adjusted': bool(body.edits),
        'inventory_written': False, 'shopping_written': False, 'automatic_planning_commit': False}
