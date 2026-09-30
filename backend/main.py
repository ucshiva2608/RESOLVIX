"""
FastAPI application for ARES (Autonomous Response Engineering System).
Serves RESTful endpoints, Server-Sent Events (SSE) live updates, and frontend assets.
"""

import os
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, init_db, SessionLocal
from backend.models import (
    Incident, IncidentEvent, Evidence, Hypothesis, RootCause,
    RecoveryPlan, Approval, ToolCall, Verification, Postmortem,
    AuditLog, TokenAccount
)
from backend.tokens import TokenService
from backend.simulator import simulator
from backend.workflow import workflow_engine
from backend.event_bus import event_bus


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown handler."""
    init_db()
    # Initialize default token account
    db = SessionLocal()
    try:
        TokenService.get_or_create_account(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="ARES — Autonomous Response Engineering System",
    description="Detect. Investigate. Decide. Act. Verify.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend directory for static assets
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# Pydantic schemas for request payloads
class InjectIncidentRequest(BaseModel):
    scenario: str = "database_failure"  # database_failure, api_failure, high_latency
    incident_id: Optional[str] = None
    simulate_verification_failure: bool = False


class ApprovePlanRequest(BaseModel):
    approved_by: str = "SRE Commander"


class RejectPlanRequest(BaseModel):
    reason: str = "Operator manual override"


class AddTokensRequest(BaseModel):
    amount: int = 5000


# =============================================================================
# REAL-TIME SSE STREAM
# =============================================================================

@app.get("/api/events")
async def sse_events(request: Request):
    """
    Server-Sent Events endpoint streaming live workflow, agent, and telemetry updates.
    """
    async def event_generator():
        async for msg in event_bus.subscribe():
            if await request.is_disconnected():
                break
            yield f"event: {msg.get('event', 'message')}\ndata: {msg.get('data')}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# SYSTEM STATUS & TELEMETRY
# =============================================================================

@app.get("/api/system/status")
def get_system_status(db: Session = Depends(get_db)):
    """Return cluster telemetry, active incident, and token metrics."""
    telemetry = simulator.get_telemetry()
    tokens = TokenService.get_balance(db)

    active_incident = (
        db.query(Incident)
        .filter(Incident.status.in_([
            "ACTIVE", "INVESTIGATING", "APPROVAL_PENDING",
            "REMEDIATING", "VERIFYING", "VERIFICATION_FAILED"
        ]))
        .order_by(Incident.created_at.desc())
        .first()
    )

    return {
        "telemetry": telemetry,
        "tokens": tokens,
        "active_incident": active_incident.to_dict() if active_incident else None,
        "safe_tools": list(simulator.SAFE_TOOLS)
    }


@app.post("/api/system/reset")
def reset_system():
    """Reset the cluster simulator, tokens, and active incidents to healthy baseline."""
    return workflow_engine.reset_system()


# =============================================================================
# TOKEN ACCOUNTING & LEDGER
# =============================================================================

@app.get("/api/tokens")
def get_tokens(db: Session = Depends(get_db)):
    """Fetch current token budget, balance, and agent consumption breakdown."""
    return TokenService.get_balance(db)


@app.get("/api/tokens/transactions")
def get_token_transactions(limit: int = 50, db: Session = Depends(get_db)):
    """Fetch recent token transaction ledger."""
    return TokenService.get_transactions(db, limit=limit)


@app.post("/api/tokens/reset")
def reset_tokens(db: Session = Depends(get_db)):
    """Reset token budget back to initial 10,000."""
    return TokenService.reset_tokens(db)


@app.post("/api/tokens/add")
def add_tokens(payload: AddTokensRequest, db: Session = Depends(get_db)):
    """Replenish token budget."""
    return TokenService.add_tokens(db, amount=payload.amount)


# =============================================================================
# INCIDENT LIFECYCLE ENDPOINTS
# =============================================================================

@app.post("/api/incidents/inject")
def inject_incident(
    payload: InjectIncidentRequest,
    background_tasks: BackgroundTasks
):
    """
    Inject a failure scenario into the cluster and launch the ARES investigation pipeline.
    """
    incident = workflow_engine.inject_and_start(
        scenario=payload.scenario,
        incident_id=payload.incident_id,
        simulate_verification_failure=payload.simulate_verification_failure
    )

    # Launch autonomous investigation pipeline in background
    background_tasks.add_task(
        workflow_engine.run_investigation_pipeline_async,
        incident.id
    )

    return {
        "status": "INCIDENT_INJECTED",
        "incident": incident.to_dict()
    }


@app.get("/api/incidents/active")
def get_active_incident(db: Session = Depends(get_db)):
    """Fetch currently active or most recent incident."""
    incident = (
        db.query(Incident)
        .order_by(Incident.created_at.desc())
        .first()
    )
    if not incident:
        return {"active_incident": None}
    return {"active_incident": incident.to_dict()}


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    """Fetch incident metadata and status."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident.to_dict()


@app.get("/api/incidents/{incident_id}/timeline")
def get_incident_timeline(incident_id: str, db: Session = Depends(get_db)):
    """Fetch chronological event timeline for the incident."""
    events = (
        db.query(IncidentEvent)
        .filter(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.timestamp.asc())
        .all()
    )
    return [e.to_dict() for e in events]


@app.get("/api/incidents/{incident_id}/evidence")
def get_incident_evidence(incident_id: str, db: Session = Depends(get_db)):
    """Fetch all evidence items collected by the Observability Agent."""
    evidence = (
        db.query(Evidence)
        .filter(Evidence.incident_id == incident_id)
        .order_by(Evidence.collected_at.asc())
        .all()
    )
    return [e.to_dict() for e in evidence]


@app.get("/api/incidents/{incident_id}/hypotheses")
def get_incident_hypotheses(incident_id: str, db: Session = Depends(get_db)):
    """Fetch competing hypotheses generated by the Investigation Agent."""
    hypotheses = (
        db.query(Hypothesis)
        .filter(Hypothesis.incident_id == incident_id)
        .order_by(Hypothesis.rank.asc())
        .all()
    )
    return [h.to_dict() for h in hypotheses]


@app.get("/api/incidents/{incident_id}/root-cause")
def get_incident_root_cause(incident_id: str, db: Session = Depends(get_db)):
    """Fetch root cause determination, evidence matrix, and explainability."""
    rc = db.query(RootCause).filter(RootCause.incident_id == incident_id).first()
    if not rc:
        return {"root_cause": None}
    return rc.to_dict()


@app.get("/api/incidents/{incident_id}/plan")
def get_incident_plan(incident_id: str, db: Session = Depends(get_db)):
    """Fetch proposed recovery plan and risk classification."""
    plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident_id).first()
    if not plan:
        return {"plan": None}
    return plan.to_dict()


@app.post("/api/incidents/{incident_id}/approve")
async def approve_incident_plan(incident_id: str, payload: ApprovePlanRequest):
    """
    Human-in-the-Loop Approval Gate: Approve proposed remediation and execute.
    """
    res = await workflow_engine.approve_and_resume_async(
        incident_id=incident_id,
        approved_by=payload.approved_by
    )
    return res


@app.post("/api/incidents/{incident_id}/reject")
async def reject_incident_plan(incident_id: str, payload: RejectPlanRequest):
    """
    Operator rejects proposed remediation plan.
    """
    res = await workflow_engine.reject_plan_async(
        incident_id=incident_id,
        reason=payload.reason
    )
    return res


@app.post("/api/incidents/{incident_id}/execute")
async def execute_incident_remediation(incident_id: str):
    """Manually trigger remediation if approved or low risk."""
    await workflow_engine.resume_execution_async(incident_id)
    return {"status": "EXECUTION_DISPATCHED", "incident_id": incident_id}


@app.get("/api/incidents/{incident_id}/verification")
def get_incident_verification(incident_id: str, db: Session = Depends(get_db)):
    """Fetch before-vs-after verification results."""
    verifications = (
        db.query(Verification)
        .filter(Verification.incident_id == incident_id)
        .order_by(Verification.timestamp.desc())
        .all()
    )
    return [v.to_dict() for v in verifications]


@app.get("/api/incidents/{incident_id}/postmortem")
def get_incident_postmortem(incident_id: str, db: Session = Depends(get_db)):
    """Fetch comprehensive incident postmortem report."""
    pm = db.query(Postmortem).filter(Postmortem.incident_id == incident_id).first()
    if not pm:
        return {"postmortem": None}
    return pm.to_dict()


@app.get("/api/incidents/{incident_id}/flow")
def get_incident_flow(incident_id: str, db: Session = Depends(get_db)):
    """
    Fetch comprehensive flowchart state for the interactive visualization.
    Returns status of all 11 resolution flow nodes.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident_id).first()
    approval = db.query(Approval).filter(Approval.incident_id == incident_id).order_by(Approval.timestamp.desc()).first()
    verif = db.query(Verification).filter(Verification.incident_id == incident_id).order_by(Verification.timestamp.desc()).first()

    # Determine node statuses: PENDING, RUNNING, COMPLETED, FAILED
    stage = incident.current_stage
    status = incident.status

    stages_order = [
        "DETECTION",
        "TELEMETRY_COLLECTION",
        "COMPETING_HYPOTHESES",
        "RUNBOOK_SEARCH",
        "ROOT_CAUSE_ANALYSIS",
        "RECOVERY_PLANNING",
        "HUMAN_APPROVAL",
        "REMEDIATION",
        "POST_REMEDIATION_VERIFICATION",
        "POSTMORTEM",
        "INCIDENT_CLOSED"
    ]

    current_idx = stages_order.index(stage) if stage in stages_order else 0

    nodes = []
    for idx, s in enumerate(stages_order):
        if idx < current_idx:
            node_status = "COMPLETED"
        elif idx == current_idx:
            if status == "RESOLVED":
                node_status = "COMPLETED"
            elif status == "VERIFICATION_FAILED" and s == "POST_REMEDIATION_VERIFICATION":
                node_status = "FAILED"
            elif status == "APPROVAL_PENDING" and s == "HUMAN_APPROVAL":
                node_status = "PAUSED_FOR_APPROVAL"
            else:
                node_status = "RUNNING"
        else:
            node_status = "PENDING"

        nodes.append({"stage": s, "status": node_status})

    return {
        "incident_id": incident_id,
        "current_stage": stage,
        "status": status,
        "replan_count": incident.replan_count,
        "nodes": nodes
    }


# =============================================================================
# AUDIT LOGS
# =============================================================================

@app.get("/api/audit-logs")
def get_audit_logs(incident_id: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Fetch immutable audit logs."""
    query = db.query(AuditLog)
    if incident_id:
        query = query.filter(AuditLog.incident_id == incident_id)
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [l.to_dict() for l in logs]


# =============================================================================
# ONE-CLICK DEMO MODE
# =============================================================================

@app.post("/api/demo/start")
def start_ares_demo(background_tasks: BackgroundTasks):
    """
    Launch 1-click ARES hackathon demo flow:
    Resets system, injects Primary Database Connection Pool failure,
    and runs autonomous investigation pipeline.
    """
    workflow_engine.reset_system()

    incident = workflow_engine.inject_and_start(
        scenario="database_failure",
        incident_id=f"INC-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-001"
    )

    background_tasks.add_task(
        workflow_engine.run_investigation_pipeline_async,
        incident.id
    )

    return {
        "status": "DEMO_STARTED",
        "incident": incident.to_dict()
    }


# =============================================================================
# ROOT FRONTEND SERVING
# =============================================================================

@app.get("/")
@app.head("/")
def serve_index():
    """Serve the SRE Mission Control dashboard."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>ARES Backend Running. Frontend is loading...</h1>")
