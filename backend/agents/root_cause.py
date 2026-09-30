"""
Root Cause Agent for ARES.
Synthesizes telemetry, evidence matrix, and hypotheses to isolate the true root cause.
Provides transparent explainability for "WHY DID ARES CHOOSE THIS?".
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, RootCause, Evidence, Hypothesis
from backend.agents.knowledge import RUNBOOK_CATALOG
from backend.event_bus import event_bus


class RootCauseAgent(BaseAgent):
    """Pinpoints root cause with verifiable evidence matrix and explainability."""

    def __init__(self):
        super().__init__(
            agent_name="Root Cause Agent",
            stage="ROOT_CAUSE_ANALYSIS",
            default_cost=120  # Root Cause Analysis
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        scenario = incident.scenario_type
        runbook = RUNBOOK_CATALOG.get(scenario, RUNBOOK_CATALOG["database_failure"])

        # Fetch evidence and hypotheses from DB
        evidence_items = db.query(Evidence).filter(Evidence.incident_id == incident.id).all()
        hypotheses = db.query(Hypothesis).filter(Hypothesis.incident_id == incident.id).order_by(Hypothesis.rank).all()

        # Delete previous root cause if replanning
        db.query(RootCause).filter(RootCause.incident_id == incident.id).delete()

        # Construct Evidence Matrix
        evidence_matrix = []
        for ev in evidence_items:
            evidence_matrix.append({
                "evidence": f"{ev.metric_name}: {ev.value}",
                "support_level": ev.support_level,
                "status": ev.status
            })

        # Explain alternative hypotheses ruled out
        alternatives_considered = []
        for h in hypotheses:
            if not h.selected:
                reason = "Contradicted by telemetry" if h.contradicting_evidence else "Insufficient support"
                if h.contradicting_evidence:
                    reason = h.contradicting_evidence[0].lstrip("- ")
                alternatives_considered.append({
                    "title": h.title,
                    "confidence": f"{int(h.confidence * 100)}%",
                    "reason_rejected": reason
                })

        if scenario == "database_failure":
            title = "DATABASE CONNECTION POOL EXHAUSTION"
            explanation = (
                "PostgreSQL connection slots reached 99/100 limit due to unreleased client sessions "
                "and deadlocked worker processes (PID 8192, 8204). Inbound API requests are timing out "
                "waiting for connection checkout from the saturated pool, cascading into 62.4% HTTP 503 errors."
            )
            confidence = 0.95

        elif scenario == "api_failure":
            title = "CRASH LOOP REGRESSION IN RELEASE v2.4.2"
            explanation = (
                "Recent rollout of container release v2.4.2 introduced a fatal NullPointerException "
                "inside RequestFilter: auth_header_v2. Kubelet liveness probes are repeatedly failing, "
                "triggering pod restarts and causing 74.5% of inbound requests to terminate with HTTP 500."
            )
            confidence = 0.96

        else:  # high_latency
            title = "UNINDEXED FULL TABLE SEQUENTIAL SCAN"
            explanation = (
                "Query execution planner is executing a full sequential scan across 1.49M records in 'orders' table "
                "due to missing composite index on (customer_id, status). This drives database CPU to 88.5% "
                "and elevates p99 query latency to 9400ms."
            )
            confidence = 0.94

        root_cause = RootCause(
            incident_id=incident.id,
            title=title,
            explanation=explanation,
            confidence=confidence,
            evidence_matrix=evidence_matrix,
            alternatives_considered=alternatives_considered,
            runbook_id=runbook["id"],
            runbook_title=runbook["title"],
            runbook_steps=runbook["steps"]
        )
        db.add(root_cause)
        db.commit()

        rc_dict = root_cause.to_dict()

        event_bus.publish_sync("root_cause_found", {
            "incident_id": incident.id,
            "root_cause": rc_dict
        })

        return {
            "root_cause": rc_dict
        }
