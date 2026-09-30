"""
Knowledge Agent for ARES.
Searches the internal SRE Runbook Catalog for verified remediation procedures
matching the active incident signatures.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident
from backend.event_bus import event_bus


# Curated verified SRE Runbooks
RUNBOOK_CATALOG = {
    "database_failure": {
        "id": "DB-POOL-003",
        "title": "PostgreSQL Connection Pool Saturation & Deadlock Remediation",
        "description": "Standard operating procedure for handling client checkout timeouts, deadlock cycles, and connection slot exhaustion.",
        "search_query": "connection pool exhaustion deadlock postgresql",
        "steps": [
            "1. Confirm pool saturation metrics (>90% utilization)",
            "2. Inspect active transactions and identify deadlocked process PIDs",
            "3. Assess safety of draining vs cycling database service",
            "4. Recycle database service if authorized (restart_database)",
            "5. Verify connection recovery (<30 connections, error rate <1%)"
        ],
        "recommended_action": "restart_database",
        "risk_level": "HIGH"
    },
    "api_failure": {
        "id": "DEPLOY-ROLLBACK-002",
        "title": "Kubernetes API Deployment Rollback Procedure",
        "description": "Procedure for rapid automated regression mitigation following bad release rollouts.",
        "search_query": "kubernetes deployment crash loop rollback",
        "steps": [
            "1. Identify offending deployment release tag (v2.4.2)",
            "2. Validate previous stable release artifact integrity (v2.4.1)",
            "3. Execute atomic deployment rollback to stable version",
            "4. Monitor container readiness probes and error rate drop (<0.5%)"
        ],
        "recommended_action": "rollback_deployment",
        "risk_level": "HIGH"
    },
    "high_latency": {
        "id": "PERF-INDEX-001",
        "title": "Concurrent Index Optimization & Query Plan Invalidation",
        "description": "Non-blocking index creation procedure for resolving unindexed sequential scans causing CPU and latency spikes.",
        "search_query": "slow query unindexed seq scan postgresql concurrent index",
        "steps": [
            "1. Identify high-cost query signature via pg_stat_statements",
            "2. Confirm missing composite index on filter columns",
            "3. Execute non-blocking CONCURRENT index creation simulation",
            "4. Invalidate query execution plan and verify p99 latency recovery"
        ],
        "recommended_action": "optimize_query_simulation",
        "risk_level": "LOW"
    }
}


class KnowledgeAgent(BaseAgent):
    """Retrieves authoritative SRE runbooks for remediation."""

    def __init__(self):
        super().__init__(
            agent_name="Knowledge Agent",
            stage="RUNBOOK_SEARCH",
            default_cost=60  # Runbook Retrieval
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        scenario = incident.scenario_type
        runbook = RUNBOOK_CATALOG.get(scenario, RUNBOOK_CATALOG["database_failure"])

        event_bus.publish_sync("runbook_found", {
            "incident_id": incident.id,
            "runbook_id": runbook["id"],
            "title": runbook["title"],
            "steps": runbook["steps"],
            "recommended_action": runbook["recommended_action"]
        })

        return {
            "matched_runbook": runbook
        }
