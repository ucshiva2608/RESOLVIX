"""
Verification Agent for ARES.
Performs Before-vs-After metric differential analysis to objectively verify
if the system has recovered to its baseline SLAs.
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, Verification, AuditLog
from backend.simulator import simulator
from backend.event_bus import event_bus


class VerificationAgent(BaseAgent):
    """Verifies remediation efficacy against target SLAs."""

    def __init__(self):
        super().__init__(
            agent_name="Verification Agent",
            stage="POST_REMEDIATION_VERIFICATION",
            default_cost=100  # Verification
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        telemetry = simulator.get_telemetry()
        before_metrics = incident.before_metrics or {}

        after_metrics = {
            "db_connections": f"{telemetry['db_connections']}/{telemetry['max_db_connections']}",
            "api_error_rate": f"{telemetry['api_error_rate']}%",
            "response_time": f"{telemetry['response_time']}ms",
            "query_latency": f"{telemetry['query_latency']}ms",
            "cpu_utilization": f"{telemetry['cpu_utilization']}%"
        }
        incident.after_metrics = after_metrics

        # Verification rules
        checks: List[Dict[str, Any]] = []

        # 1. Error rate check (< 1.0%)
        error_rate = telemetry["api_error_rate"]
        error_satisfied = error_rate < 1.0
        checks.append({
            "check": "API Error Rate < 1.0%",
            "before": before_metrics.get("api_error_rate", "N/A"),
            "after": f"{error_rate}%",
            "satisfied": error_satisfied,
            "threshold": "< 1.0%"
        })

        # 2. Database connection check (< 40 connections)
        db_conn = telemetry["db_connections"]
        conn_satisfied = db_conn <= 35
        checks.append({
            "check": "DB Connections < 35/100",
            "before": before_metrics.get("db_connections", "N/A"),
            "after": f"{db_conn}/100",
            "satisfied": conn_satisfied,
            "threshold": "<= 35"
        })

        # 3. Response time check (< 300ms)
        resp_time = telemetry["response_time"]
        resp_satisfied = resp_time < 500.0
        checks.append({
            "check": "Response Time < 500ms",
            "before": before_metrics.get("response_time", "N/A"),
            "after": f"{resp_time}ms",
            "satisfied": resp_satisfied,
            "threshold": "< 500ms"
        })

        all_satisfied = error_satisfied and conn_satisfied and resp_satisfied
        attempt = (incident.replan_count or 0) + 1

        failure_reason = None
        if not all_satisfied:
            failed_checks = [c["check"] for c in checks if not c["satisfied"]]
            failure_reason = f"Verification failed on criteria: {', '.join(failed_checks)}. Error rate is {error_rate}% (expected < 1.0%)."

        verification = Verification(
            incident_id=incident.id,
            attempt_number=attempt,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            recovery_satisfied=all_satisfied,
            verification_checks=checks,
            failure_reason=failure_reason
        )
        db.add(verification)

        audit = AuditLog(
            incident_id=incident.id,
            actor="Verification Agent",
            action="VERIFY_REMEDIATION",
            risk_level="INFO",
            details={
                "attempt": attempt,
                "satisfied": all_satisfied,
                "checks": checks,
                "failure_reason": failure_reason
            }
        )
        db.add(audit)

        if all_satisfied:
            incident.status = "RESOLVED"
            incident.resolved_at = datetime.now(timezone.utc)
            event_bus.publish_sync("verification_completed", {
                "incident_id": incident.id,
                "status": "PASSED",
                "recovery_satisfied": True,
                "before": before_metrics,
                "after": after_metrics,
                "checks": checks
            })
            event_bus.publish_sync("incident_resolved", {
                "incident_id": incident.id,
                "status": "RESOLVED",
                "total_tokens": incident.tokens_consumed,
                "replans": incident.replan_count
            })
        else:
            incident.status = "VERIFICATION_FAILED"
            event_bus.publish_sync("verification_failed", {
                "incident_id": incident.id,
                "status": "FAILED",
                "recovery_satisfied": False,
                "reason": failure_reason,
                "before": before_metrics,
                "after": after_metrics,
                "checks": checks
            })

        db.commit()

        return {
            "recovery_satisfied": all_satisfied,
            "before_metrics": before_metrics,
            "after_metrics": after_metrics,
            "checks": checks,
            "failure_reason": failure_reason
        }
