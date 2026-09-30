"""
Observability Agent for ARES.
Reads real-time metrics, telemetry streams, container logs, and deployment history
from the simulated cluster. Populates evidence records in the database.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, Evidence
from backend.simulator import simulator
from backend.event_bus import event_bus


class ObservabilityAgent(BaseAgent):
    """Gathers and correlates telemetry, logs, and service health signals."""

    def __init__(self):
        super().__init__(
            agent_name="Observability Agent",
            stage="TELEMETRY_COLLECTION",
            default_cost=200  # Telemetry (50) + Log Analysis (80) + Metric Analysis (70)
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        telemetry = simulator.get_telemetry()
        scenario = incident.scenario_type

        # Clear existing evidence if replanning
        db.query(Evidence).filter(Evidence.incident_id == incident.id).delete()

        evidence_items: List[Evidence] = []

        if scenario == "database_failure":
            evidence_items = [
                Evidence(
                    incident_id=incident.id,
                    metric_name="Database Connection Saturation",
                    value=f"{telemetry['db_connections']}/{telemetry['max_db_connections']}",
                    baseline_value="24/100",
                    unit="connections",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="PostgreSQL Telemetry Collector",
                    details="Connection pool reached 99% capacity. Active client checkout queuing with 5000ms acquire timeout."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="API Gateway 503 Timeout Rate",
                    value=f"{telemetry['api_error_rate']}%",
                    baseline_value="0.2%",
                    unit="percent",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="Envoy Proxy Ingress",
                    details="62.4% of inbound requests returning HTTP 503 Service Unavailable due to upstream pool exhaustion."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="Query Execution Latency",
                    value=f"{telemetry['query_latency']} ms",
                    baseline_value="180 ms",
                    unit="ms",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="Database Query Performance Monitor",
                    details="Severe query queuing observed; transaction deadlocks detected between worker pid 8192 and 8204."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="Recent Deployment History",
                    value="None (Last deployment: v2.4.1 48h ago)",
                    baseline_value="Stable",
                    unit="version",
                    status="NORMAL",
                    support_level="LOW",
                    source="CI/CD Deployment Audit",
                    details="No deployment or configuration drift occurred in the past 24 hours."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="Database Process Status",
                    value="SATURATED",
                    baseline_value="ONLINE",
                    unit="state",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="Kubernetes Pod Health Check",
                    details="PostgreSQL container process is running but all available connection slots are occupied."
                )
            ]

        elif scenario == "api_failure":
            evidence_items = [
                Evidence(
                    incident_id=incident.id,
                    metric_name="Recent Deployment Version",
                    value=telemetry["deployment_version"],
                    baseline_value="v2.4.1",
                    unit="release",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="ArgoCD Rollout Audit",
                    details="Release v2.4.2 deployed 4 minutes prior to incident detection."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="HTTP 500 Crash Rate",
                    value=f"{telemetry['api_error_rate']}%",
                    baseline_value="0.2%",
                    unit="percent",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="API Ingress Controller",
                    details="Crash rate spiked to 74.5% immediately following v2.4.2 rollout."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="Liveness Probe Failures",
                    value="4 container restart events",
                    baseline_value="0 restarts",
                    unit="restarts",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="Kubelet Daemon",
                    details="Crash loop backoff: NullPointerException thrown during header filter initialization."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="Database Health Status",
                    value="ONLINE (24/100 connections)",
                    baseline_value="24/100",
                    unit="connections",
                    status="NORMAL",
                    support_level="LOW",
                    source="Database Health Agent",
                    details="Database responds within normal 180ms bounds; underlying data tier is healthy."
                )
            ]

        else:  # high_latency / slow query
            evidence_items = [
                Evidence(
                    incident_id=incident.id,
                    metric_name="p99 Query Latency",
                    value=f"{telemetry['query_latency']} ms",
                    baseline_value="180 ms",
                    unit="ms",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="PostgreSQL pg_stat_statements",
                    details="Full sequential table scan on 'orders' table without composite index on (customer_id, status)."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="Database CPU Utilization",
                    value=f"{telemetry['cpu_utilization']}%",
                    baseline_value="18.5%",
                    unit="percent",
                    status="ANOMALOUS",
                    support_level="HIGH",
                    source="Node Exporter",
                    details="Database CPU elevated due to unindexed row filtration over 1.49M records."
                ),
                Evidence(
                    incident_id=incident.id,
                    metric_name="HTTP 504 Gateway Timeouts",
                    value=f"{telemetry['api_error_rate']}%",
                    baseline_value="0.2%",
                    unit="percent",
                    status="ANOMALOUS",
                    support_level="MEDIUM",
                    source="Ingress Router",
                    details="Client requests timing out after exceeding 10000ms SLA."
                )
            ]

        for item in evidence_items:
            db.add(item)
        db.commit()

        # Update incident before_metrics snapshot
        incident.before_metrics = {
            "db_connections": f"{telemetry['db_connections']}/{telemetry['max_db_connections']}",
            "api_error_rate": f"{telemetry['api_error_rate']}%",
            "response_time": f"{telemetry['response_time']}ms",
            "query_latency": f"{telemetry['query_latency']}ms",
            "cpu_utilization": f"{telemetry['cpu_utilization']}%"
        }
        db.commit()

        evidence_dicts = [e.to_dict() for e in evidence_items]

        event_bus.publish_sync("evidence_collected", {
            "incident_id": incident.id,
            "evidence_count": len(evidence_dicts),
            "evidence": evidence_dicts,
            "telemetry": telemetry
        })

        return {
            "evidence_count": len(evidence_items),
            "evidence": evidence_dicts,
            "telemetry": telemetry
        }
