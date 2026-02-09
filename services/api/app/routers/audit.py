from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from services.api.app.db.deps import get_db
from services.api.app.db.models import (
    Confirmation,
    Draft,
    Execution,
    ExecutionRequest,
    ReceiptArtifact,
)
from services.api.app.models.audit import ExecutionDetail, ExecutionListItem, ReceiptArtifactOut
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/v1/executions", response_model=list[ExecutionListItem])
def list_executions(household_id: str, db: Session = Depends(get_db)) -> list[ExecutionListItem]:
    rows = (
        db.query(Execution, Draft, ExecutionRequest)
        .join(Draft, Draft.id == Execution.draft_id)
        .join(ExecutionRequest, ExecutionRequest.id == Draft.execution_request_id)
        .filter(ExecutionRequest.household_id == household_id)
        .order_by(Execution.started_at.desc())
        .limit(200)
        .all()
    )

    out: list[ExecutionListItem] = []
    for execution, draft, _req in rows:
        out.append(
            ExecutionListItem(
                execution_id=execution.id,
                draft_id=draft.id,
                verb=draft.verb,
                status=execution.status,
                started_at=execution.started_at.isoformat(),
                finished_at=execution.finished_at.isoformat() if execution.finished_at else None,
                vendor=draft.vendor,
                final_cost_cents=execution.final_cost_cents,
            )
        )

    return out


@router.get("/v1/executions/{execution_id}", response_model=ExecutionDetail)
def get_execution(execution_id: str, db: Session = Depends(get_db)) -> ExecutionDetail:
    row = (
        db.query(Execution, Draft, ExecutionRequest)
        .join(Draft, Draft.id == Execution.draft_id)
        .join(ExecutionRequest, ExecutionRequest.id == Draft.execution_request_id)
        .filter(Execution.id == execution_id)
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution, draft, req = row

    confirmation = (
        db.query(Confirmation)
        .filter(Confirmation.draft_id == draft.id)
        .order_by(Confirmation.confirmed_at.desc())
        .first()
    )

    receipts = (
        db.query(ReceiptArtifact)
        .filter(ReceiptArtifact.execution_id == execution.id)
        .order_by(ReceiptArtifact.created_at.desc())
        .all()
    )

    receipt_out = [
        ReceiptArtifactOut(
            id=r.id,
            type=r.type,
            content_text=r.content_text,
            external_reference_id=r.external_reference_id,
            created_at=r.created_at.isoformat(),
        )
        for r in receipts
    ]

    return ExecutionDetail(
        execution_id=execution.id,
        draft_id=draft.id,
        verb=draft.verb,
        status=execution.status,
        started_at=execution.started_at.isoformat(),
        finished_at=execution.finished_at.isoformat() if execution.finished_at else None,
        raw_command_text=req.raw_command_text,
        normalized_intent_json=req.normalized_intent_json,
        draft_payload_json=draft.draft_payload_json,
        confirmation_latency_ms=confirmation.confirmation_latency_ms if confirmation else None,
        execution_payload_json=execution.execution_payload_json,
        error_message=execution.error_message,
        receipts=receipt_out,
    )


@router.get("/v1/receipts/{execution_id}", response_model=list[ReceiptArtifactOut])
def get_receipts(execution_id: str, db: Session = Depends(get_db)) -> list[ReceiptArtifactOut]:
    receipts = (
        db.query(ReceiptArtifact)
        .filter(ReceiptArtifact.execution_id == execution_id)
        .order_by(ReceiptArtifact.created_at.desc())
        .all()
    )

    return [
        ReceiptArtifactOut(
            id=r.id,
            type=r.type,
            content_text=r.content_text,
            external_reference_id=r.external_reference_id,
            created_at=r.created_at.isoformat(),
        )
        for r in receipts
    ]
