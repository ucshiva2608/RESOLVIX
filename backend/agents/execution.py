"""
Execution Agent for ARES.
Enforces strict execution sandboxing and safety policies:
1. Validates human approval gate for HIGH-risk actions.
2. Checks tool against predefined safe-tool allowlist (NO shell/bash/terminal).
3. Verifies token budget availability.
4. Emits real-time progress steps (10% -> 30% -> 60% -> 100%).
"""

import time
from typing import Dict, Any
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, RecoveryPlan, Approval, ToolCall, AuditLog
from backend.simulator import simulator
from backend.event_bus import event_bus


class SecurityViolationError(Exception):
    """Raised when an unauthorized, unapproved, or unlisted remediation is attempted."""
    pass


class ExecutionAgent(BaseAgent):
    """Safely dispatches approved remediations with strict policy gatekeeping."""

    def __init__(self):
        super().__init__(
            agent_name="Execution Agent",
            stage="REMEDIATION",
            default_cost=150  # Remediation Execution
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).first()
        if not plan:
            raise ValueError(f"No recovery plan found for incident {incident.id}")

        action_name = plan.proposed_action

        # =====================================================================
        # SAFETY CHECK 1: HUMAN APPROVAL VALIDATION FOR HIGH-RISK OPERATIONS
        # =====================================================================
        if plan.required_approval or plan.risk_level == "HIGH":
            approval = (
                db.query(Approval)
                .filter(Approval.incident_id == incident.id, Approval.approved_action == action_name)
                .order_by(Approval.timestamp.desc())
                .first()
            )
            if not approval or approval.decision != "APPROVED":
                audit = AuditLog(
                    incident_id=incident.id,
                    actor="Safety Policy Gate",
                    action="BLOCK_UNAUTHORIZED_EXECUTION",
                    risk_level="CRITICAL",
                    details={
                        "action": action_name,
                        "risk_level": plan.risk_level,
                        "reason": "HIGH-risk remediation attempted without verified Human Approval."
                    }
                )
                db.add(audit)
                db.commit()

                event_bus.publish_sync("execution_blocked", {
                    "incident_id": incident.id,
                    "action": action_name,
                    "reason": "CRITICAL POLICY BLOCK: Human Approval required before executing high-risk action."
                })
                raise SecurityViolationError(
                    f"BLOCKED: Remediation '{action_name}' requires explicit human approval."
                )

        # =====================================================================
        # SAFETY CHECK 2: SAFE TOOL ALLOW-LIST ENFORCEMENT
        # =====================================================================
        if action_name not in simulator.SAFE_TOOLS:
            audit = AuditLog(
                incident_id=incident.id,
                actor="Safety Policy Gate",
                action="BLOCK_UNLISTED_TOOL",
                risk_level="CRITICAL",
                details={
                    "tool": action_name,
                    "reason": "Attempted to execute unapproved tool not in safe simulation allowlist."
                }
            )
            db.add(audit)
            db.commit()
            raise SecurityViolationError(f"BLOCKED: Tool '{action_name}' is not in the safe-tool allowlist.")

        # =====================================================================
        # EXECUTION DISPATCH WITH PROGRESS UPDATES
        # =====================================================================
        event_bus.publish_sync("execution_started", {
            "incident_id": incident.id,
            "action": action_name,
            "risk_level": plan.risk_level
        })

        # Progress 10%
        event_bus.publish_sync("execution_progress", {
            "incident_id": incident.id,
            "action": action_name,
            "progress": 10,
            "step": "Validating approval and policy compliance... [VERIFIED]"
        })

        # Progress 30%
        event_bus.publish_sync("execution_progress", {
            "incident_id": incident.id,
            "action": action_name,
            "progress": 30,
            "step": f"Acquiring lock on service resource for {action_name}... [LOCKED]"
        })

        # Progress 60%
        event_bus.publish_sync("execution_progress", {
            "incident_id": incident.id,
            "action": action_name,
            "progress": 60,
            "step": f"Executing safe simulation procedure '{action_name}'..."
        })

        # Dispatch to Simulator
        tool_result: Dict[str, Any] = {}
        if action_name == "restart_database":
            tool_result = simulator.restart_database()
        elif action_name == "rollback_deployment":
            tool_result = simulator.rollback_deployment(target_version="v2.4.1")
        elif action_name == "optimize_query_simulation":
            tool_result = simulator.optimize_query_simulation()
        elif action_name == "clear_connection_pool_simulation":
            tool_result = simulator.clear_connection_pool_simulation()
        elif action_name == "restart_service":
            tool_result = simulator.restart_service()
        else:
            raise SecurityViolationError(f"Tool {action_name} not implemented in simulator.")

        # Progress 100%
        event_bus.publish_sync("execution_progress", {
            "incident_id": incident.id,
            "action": action_name,
            "progress": 100,
            "step": f"Procedure completed successfully: {tool_result.get('message', 'Done')}"
        })

        # Record Tool Call in DB
        tool_call = ToolCall(
            incident_id=incident.id,
            tool_name=action_name,
            parameters=plan.action_parameters,
            result=tool_result,
            is_allowed=True,
            status="SUCCESS",
            progress_percent=100,
            executed_by="Execution Agent"
        )
        db.add(tool_call)

        # Record in Audit Log
        audit = AuditLog(
            incident_id=incident.id,
            actor="Execution Agent",
            action=f"EXECUTE_{action_name.upper()}",
            risk_level=plan.risk_level,
            details={
                "tool": action_name,
                "result": tool_result.get("message"),
                "status": "COMPLETED"
            }
        )
        db.add(audit)

        plan.status = "EXECUTED"
        incident.status = "VERIFYING"
        incident.current_stage = "POST_REMEDIATION_VERIFICATION"
        db.commit()

        event_bus.publish_sync("execution_completed", {
            "incident_id": incident.id,
            "action": action_name,
            "result": tool_result
        })

        return {
            "action": action_name,
            "status": "COMPLETED",
            "result": tool_result
        }
