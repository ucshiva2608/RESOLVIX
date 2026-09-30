"""
End-to-End Workflow & Replanning Tests for ARES.
Verifies failure injection, multi-agent lifecycle, verification success,
verification failure, replanning loops, and postmortem generation.
"""

import pytest
import asyncio
from backend.database import SessionLocal, init_db
from backend.models import (
    Incident, Evidence, Hypothesis, RootCause, RecoveryPlan,
    Approval, Verification, Postmortem
)
from backend.simulator import simulator
from backend.workflow import workflow_engine
from backend.tokens import TokenService


@pytest.fixture(autouse=True)
def setup_workflow():
    init_db()
    workflow_engine.step_delay = 0.05
    workflow_engine.reset_system()
    db = SessionLocal()
    try:
        incidents = db.query(Incident).filter(Incident.id.like("TEST-INC-%")).all()
        for inc in incidents:
            db.delete(inc)
        db.commit()
    finally:
        db.close()
    yield


def test_incident_injection_telemetry():
    """Verify failure injection mutates simulator telemetry and creates DB incident."""
    incident = workflow_engine.inject_and_start(
        scenario="database_failure",
        incident_id="TEST-INC-DB-01"
    )
    assert incident.id == "TEST-INC-DB-01"
    assert incident.scenario_type == "database_failure"
    assert incident.severity == "CRITICAL"

    telem = simulator.get_telemetry()
    assert telem["db_connections"] == 99
    assert telem["api_error_rate"] == 62.4
    assert telem["system_status"] == "CRITICAL"


@pytest.mark.asyncio
async def test_full_investigation_and_approval_cycle():
    """
    Test complete lifecycle from injection through all agents,
    pausing at approval gate, granting approval, execution, and verification.
    """
    incident = workflow_engine.inject_and_start(
        scenario="database_failure",
        incident_id="TEST-INC-LIFECYCLE-01"
    )

    # Run investigation pipeline asynchronously
    await workflow_engine.run_investigation_pipeline_async(incident.id)

    db = SessionLocal()
    try:
        # Check Evidence collected
        evidence = db.query(Evidence).filter(Evidence.incident_id == incident.id).all()
        assert len(evidence) >= 4

        # Check at least 3 competing hypotheses generated
        hypotheses = db.query(Hypothesis).filter(Hypothesis.incident_id == incident.id).all()
        assert len(hypotheses) >= 3
        # Top hypothesis should be connection pool exhaustion with 95% confidence
        top_h = next(h for h in hypotheses if h.selected)
        assert "Connection Pool" in top_h.title
        assert top_h.confidence >= 0.90

        # Check Root Cause determined
        rc = db.query(RootCause).filter(RootCause.incident_id == incident.id).first()
        assert rc is not None
        assert "CONNECTION POOL" in rc.title
        assert len(rc.alternatives_considered) >= 2

        # Check Recovery Plan formulated and paused for Human Approval
        plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).first()
        assert plan is not None
        assert plan.proposed_action == "restart_database"
        assert plan.risk_level == "HIGH"
        assert plan.required_approval is True

        inc_refreshed = db.query(Incident).filter(Incident.id == incident.id).first()
        assert inc_refreshed.status == "APPROVAL_PENDING"

    finally:
        db.close()

    # Now Grant Human Approval and Resume
    approval_res = await workflow_engine.approve_and_resume_async(
        incident_id=incident.id,
        approved_by="Hackathon Judge"
    )
    assert approval_res["status"] == "APPROVED"

    # Wait for execution and verification to complete
    await asyncio.sleep(1.0)

    db = SessionLocal()
    try:
        # Check simulator state recovered
        telem = simulator.get_telemetry()
        assert telem["db_connections"] <= 35
        assert telem["api_error_rate"] <= 1.0
        assert telem["system_status"] == "HEALTHY"

        # Check Verification passed
        verif = db.query(Verification).filter(Verification.incident_id == incident.id).first()
        assert verif is not None
        assert verif.recovery_satisfied is True

        # Check Postmortem generated
        pm = db.query(Postmortem).filter(Postmortem.incident_id == incident.id).first()
        assert pm is not None
        assert pm.remediation_executed == "restart_database"
        assert len(pm.lessons_learned) >= 3

        # Check Incident status is RESOLVED
        inc_resolved = db.query(Incident).filter(Incident.id == incident.id).first()
        assert inc_resolved.status == "RESOLVED"

    finally:
        db.close()


@pytest.mark.asyncio
async def test_verification_failure_triggers_replanning():
    """
    Test Section 21: When verification fails, ARES does not assume success.
    Instead, it transitions to REPLANNING, formulates a new plan, and prompts approval.
    """
    incident = workflow_engine.inject_and_start(
        scenario="database_failure",
        incident_id="TEST-INC-REPLAN-01",
        simulate_verification_failure=True
    )

    # Run investigation
    await workflow_engine.run_investigation_pipeline_async(incident.id)

    # Approve initial plan
    await workflow_engine.approve_and_resume_async(
        incident_id=incident.id,
        approved_by="SRE Tester"
    )

    # Wait for execution and failed verification
    await asyncio.sleep(1.0)

    db = SessionLocal()
    try:
        # Verification should have recorded failure
        verif = db.query(Verification).filter(Verification.incident_id == incident.id).first()
        assert verif is not None
        assert verif.recovery_satisfied is False

        # Incident should have triggered replanning
        inc = db.query(Incident).filter(Incident.id == incident.id).first()
        assert inc.replan_count == 1
        assert inc.status == "APPROVAL_PENDING"

        # A revised plan was created
        plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).first()
        assert plan is not None
        assert plan.proposed_action == "restart_database"

    finally:
        db.close()
