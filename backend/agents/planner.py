"""
Planner Agent & Risk Engine for ARES.
Formulates structured recovery plans, assesses blast radius and risk levels,
and enforces the Human Approval Gate for high-impact remediations.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, RecoveryPlan
from backend.agents.knowledge import RUNBOOK_CATALOG
from backend.event_bus import event_bus


class PlannerAgent(BaseAgent):
    """Generates remediation plan and enforces safety risk classification."""

    def __init__(self):
        super().__init__(
            agent_name="Planner Agent",
            stage="RECOVERY_PLANNING",
            default_cost=160  # Recovery Planning (100) + Risk Assessment (60)
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        scenario = incident.scenario_type
        runbook = RUNBOOK_CATALOG.get(scenario, RUNBOOK_CATALOG["database_failure"])

        # Delete previous plan if replanning
        db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).delete()

        if scenario == "database_failure":
            # If replanning iteration > 0, we might adjust or reinforce
            proposed_action = "restart_database"
            risk_level = "HIGH"
            risk_reason = "Restarting the database terminates active client transactions and temporarily interrupts dependent microservices during reboot cycle."
            expected_recovery = {
                "db_connections": "99/100 → 24/100",
                "api_error_rate": "62.4% → below 1.0%",
                "response_time": "7800ms → ~190ms",
                "query_latency": "7600ms → ~180ms"
            }
            required_approval = True

        elif scenario == "api_failure":
            proposed_action = "rollback_deployment"
            risk_level = "HIGH"
            risk_reason = "Rolling back active deployment reverts running container images and can cause brief traffic diversion during pod teardown."
            expected_recovery = {
                "deployment_version": "v2.4.2 → v2.4.1",
                "api_error_rate": "74.5% → below 0.5%",
                "pod_restarts": "4 → 0 restarts",
                "response_time": "4200ms → ~180ms"
            }
            required_approval = True

        else:  # high_latency
            proposed_action = "optimize_query_simulation"
            risk_level = "LOW"
            risk_reason = "Non-blocking CONCURRENT index creation executes without acquiring exclusive write locks on the table."
            expected_recovery = {
                "query_latency": "9400ms → ~120ms",
                "cpu_utilization": "88.5% → below 25%",
                "api_error_rate": "14.8% → below 0.2%"
            }
            required_approval = False

        plan = RecoveryPlan(
            incident_id=incident.id,
            proposed_action=proposed_action,
            action_parameters={"scenario": scenario, "action": proposed_action},
            risk_level=risk_level,
            risk_reason=risk_reason,
            expected_recovery=expected_recovery,
            verification_sla_seconds=60,
            required_approval=required_approval,
            status="PENDING_APPROVAL" if required_approval else "APPROVED"
        )
        db.add(plan)

        if required_approval:
            incident.status = "APPROVAL_PENDING"
            incident.current_stage = "HUMAN_APPROVAL"
        else:
            incident.status = "REMEDIATING"
            incident.current_stage = "REMEDIATION"

        db.commit()

        plan_dict = plan.to_dict()

        event_bus.publish_sync("plan_created", {
            "incident_id": incident.id,
            "plan": plan_dict
        })

        if required_approval:
            event_bus.publish_sync("approval_required", {
                "incident_id": incident.id,
                "problem": incident.title,
                "proposed_action": proposed_action,
                "risk_level": risk_level,
                "risk_reason": risk_reason,
                "expected_recovery": expected_recovery
            })

        return {
            "recovery_plan": plan_dict,
            "required_approval": required_approval
        }
