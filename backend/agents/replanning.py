"""
Replanning Agent for ARES.
Activated when post-remediation verification fails.
Re-evaluates contradictory signals, generates updated recovery plans,
and enforces escalation limits (maximum 3 replanning attempts).
"""

from typing import Dict, Any
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, RecoveryPlan, AuditLog
from backend.simulator import simulator
from backend.event_bus import event_bus

MAX_REPLAN_ATTEMPTS = 3


class ReplanningAgent(BaseAgent):
    """Executes dynamic replanning when remediation fails to restore SLA."""

    def __init__(self):
        super().__init__(
            agent_name="Replanning Agent",
            stage="REPLANNING",
            default_cost=110  # Replanning Investigation
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        incident.replan_count = (incident.replan_count or 0) + 1
        simulator.state["replanning_iteration"] = incident.replan_count

        event_bus.publish_sync("replanning_started", {
            "incident_id": incident.id,
            "attempt": incident.replan_count,
            "max_attempts": MAX_REPLAN_ATTEMPTS,
            "reason": input_data.get("failure_reason", "Post-remediation SLA verification failed.")
        })

        if incident.replan_count > MAX_REPLAN_ATTEMPTS:
            # Escalation path
            incident.status = "ESCALATED"
            incident.current_stage = "ESCALATION_REQUIRED"
            db.commit()

            audit = AuditLog(
                incident_id=incident.id,
                actor="Safety Gate",
                action="ESCALATE_TO_HUMAN_ENGINEERS",
                risk_level="CRITICAL",
                details={
                    "replan_attempts": incident.replan_count,
                    "reason": "Exceeded maximum autonomous replanning attempts (3). Paging Tier-3 Incident Commander."
                }
            )
            db.add(audit)
            db.commit()

            event_bus.publish_sync("incident_escalated", {
                "incident_id": incident.id,
                "message": "Maximum replanning attempts reached (3). Incident escalated to human SRE commander."
            })
            return {
                "escalated": True,
                "replan_count": incident.replan_count,
                "status": "ESCALATED"
            }

        # Dynamic Revised Strategy
        # If partial tool was clear_connection_pool_simulation, escalate to full restart_database
        previous_plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).first()
        new_action = "restart_database"
        risk_level = "HIGH"
        risk_reason = "Escalated recovery: Forced database restart to eliminate 28 zombie backend processes that resisted pool flushing."

        # Create revised recovery plan
        db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).delete()
        revised_plan = RecoveryPlan(
            incident_id=incident.id,
            proposed_action=new_action,
            action_parameters={"action": new_action, "escalation_pass": incident.replan_count},
            risk_level=risk_level,
            risk_reason=risk_reason,
            expected_recovery={
                "db_connections": "72/100 → 24/100",
                "api_error_rate": "28.1% → 0.4%",
                "response_time": "2400ms → 190ms"
            },
            verification_sla_seconds=60,
            required_approval=True,
            status="PENDING_APPROVAL"
        )
        db.add(revised_plan)

        incident.status = "APPROVAL_PENDING"
        incident.current_stage = "HUMAN_APPROVAL"
        db.commit()

        audit = AuditLog(
            incident_id=incident.id,
            actor="Replanning Agent",
            action="GENERATE_REVISED_PLAN",
            risk_level="HIGH",
            details={
                "replan_attempt": incident.replan_count,
                "new_action": new_action,
                "risk_reason": risk_reason
            }
        )
        db.add(audit)
        db.commit()

        event_bus.publish_sync("approval_required", {
            "incident_id": incident.id,
            "problem": f"REPLAN ATTEMPT {incident.replan_count}: Lingering backend process deadlocks",
            "proposed_action": new_action,
            "risk_level": risk_level,
            "risk_reason": risk_reason,
            "expected_recovery": revised_plan.expected_recovery
        })

        return {
            "escalated": False,
            "replan_count": incident.replan_count,
            "revised_plan": revised_plan.to_dict()
        }
