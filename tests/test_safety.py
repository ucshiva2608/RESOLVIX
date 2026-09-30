"""
Safety and Policy Gate Tests for ARES.
CRITICAL SAFETY REQUIREMENT (Section 41):
1. An unapproved HIGH-risk remediation must ALWAYS be blocked.
2. Unlisted/arbitrary shell execution attempts must ALWAYS be rejected.
3. Every safety violation must be logged to the immutable audit trail.
"""

import pytest
from backend.database import SessionLocal, init_db
from backend.models import Incident, RecoveryPlan, Approval, AuditLog
from backend.agents.execution import ExecutionAgent, SecurityViolationError
from backend.simulator import simulator


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    simulator.reset()
    db = SessionLocal()
    try:
        incidents = db.query(Incident).filter(Incident.id.like("SAFETY-INC-%")).all()
        for inc in incidents:
            db.delete(inc)
        db.commit()
    finally:
        db.close()
    yield


def test_unapproved_high_risk_remediation_is_blocked():
    """
    CRITICAL SAFETY TEST:
    An unapproved HIGH-risk remediation must ALWAYS be blocked by ExecutionAgent.
    """
    db = SessionLocal()
    try:
        incident = Incident(
            id="SAFETY-INC-001",
            scenario_type="database_failure",
            title="Database Saturation Test",
            status="APPROVAL_PENDING",
            severity="CRITICAL",
            current_stage="HUMAN_APPROVAL"
        )
        db.add(incident)

        plan = RecoveryPlan(
            incident_id=incident.id,
            proposed_action="restart_database",
            risk_level="HIGH",
            risk_reason="Database restart drops active connections.",
            required_approval=True,
            status="PENDING_APPROVAL"
        )
        db.add(plan)
        db.commit()

        # Attempt to execute WITHOUT Human Approval
        exec_agent = ExecutionAgent()
        with pytest.raises(SecurityViolationError) as exc_info:
            exec_agent.execute(db, incident)

        assert "requires explicit human approval" in str(exc_info.value)

        # Verify audit log caught the block
        audit = db.query(AuditLog).filter(
            AuditLog.incident_id == incident.id,
            AuditLog.action == "BLOCK_UNAUTHORIZED_EXECUTION"
        ).first()
        assert audit is not None
        assert audit.risk_level == "CRITICAL"

    finally:
        db.close()


def test_approved_high_risk_remediation_succeeds():
    """
    Verify that once explicit Human Approval is granted,
    the HIGH-risk remediation is permitted to execute.
    """
    db = SessionLocal()
    try:
        incident = Incident(
            id="SAFETY-INC-002",
            scenario_type="database_failure",
            title="Database Saturation Test",
            status="APPROVAL_PENDING",
            severity="CRITICAL",
            current_stage="HUMAN_APPROVAL"
        )
        db.add(incident)

        plan = RecoveryPlan(
            incident_id=incident.id,
            proposed_action="restart_database",
            risk_level="HIGH",
            risk_reason="Database restart drops active connections.",
            required_approval=True,
            status="PENDING_APPROVAL"
        )
        db.add(plan)

        # Operator provides approval
        approval = Approval(
            incident_id=incident.id,
            approved_action="restart_database",
            risk_level="HIGH",
            approved_by="Lead SRE Judge",
            decision="APPROVED"
        )
        db.add(approval)
        db.commit()

        exec_agent = ExecutionAgent()
        result = exec_agent.execute(db, incident)

        assert result["status"] == "COMPLETED"
        assert result["action"] == "restart_database"

        # Verify successful audit log
        audit = db.query(AuditLog).filter(
            AuditLog.incident_id == incident.id,
            AuditLog.action == "EXECUTE_RESTART_DATABASE"
        ).first()
        assert audit is not None

    finally:
        db.close()


def test_unlisted_tool_is_blocked():
    """Verify that any action not in simulator.SAFE_TOOLS is strictly blocked."""
    db = SessionLocal()
    try:
        incident = Incident(
            id="SAFETY-INC-003",
            scenario_type="database_failure",
            title="Injection Test",
            status="REMEDIATING",
            severity="CRITICAL"
        )
        db.add(incident)

        plan = RecoveryPlan(
            incident_id=incident.id,
            proposed_action="rm -rf /var/lib/postgresql",  # Malicious/unauthorized tool
            risk_level="LOW",
            risk_reason="Unsafe action",
            required_approval=False,
            status="APPROVED"
        )
        db.add(plan)
        db.commit()

        exec_agent = ExecutionAgent()
        with pytest.raises(SecurityViolationError) as exc_info:
            exec_agent.execute(db, incident)

        assert "not in the safe-tool allowlist" in str(exc_info.value)

    finally:
        db.close()
