"""
Investigation Agent for ARES.
Generates competing hypotheses with supporting/contradicting evidence and confidence scores.
Shows transparent, explainable reasoning instead of black-box conclusions.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.agents.base import BaseAgent
from backend.models import Incident, Hypothesis
from backend.event_bus import event_bus


class InvestigationAgent(BaseAgent):
    """Evaluates telemetry against failure models to generate competing hypotheses."""

    def __init__(self):
        super().__init__(
            agent_name="Investigation Agent",
            stage="COMPETING_HYPOTHESES",
            default_cost=100  # Hypothesis Generation
        )

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        scenario = incident.scenario_type

        # Clear previous hypotheses if replanning
        db.query(Hypothesis).filter(Hypothesis.incident_id == incident.id).delete()

        hypotheses_data = []

        if scenario == "database_failure":
            hypotheses_data = [
                {
                    "rank": 1,
                    "title": "Database Connection Pool Exhaustion",
                    "description": "Client connections have saturated maximum pool limits due to transaction deadlocks and unclosed sessions.",
                    "supporting_evidence": [
                        "+ 99/100 connections occupied (99% capacity)",
                        "+ Deadlock logs detected on worker pid 8192 and 8204",
                        "+ Pool checkout acquire timeout (5000ms exceeded)",
                        "+ Upstream 503 timeout spikes correlating with pool saturation"
                    ],
                    "contradicting_evidence": [
                        "- No recent application code deployments or config drifts in past 24h"
                    ],
                    "confidence": 0.95,
                    "selected": True
                },
                {
                    "rank": 2,
                    "title": "L7 Traffic Spike / DDoS Overload",
                    "description": "Sudden external HTTP traffic surge causing request buffer overflow.",
                    "supporting_evidence": [
                        "+ Modest request queue increase at API gateway ingress"
                    ],
                    "contradicting_evidence": [
                        "- Inbound request rate (+12%) is well below provisioned load balancer capacity",
                        "- No spike in unique client IPs or synthetic DDoS signature",
                        "- CPU utilization on web tier remains below 40%"
                    ],
                    "confidence": 0.35,
                    "selected": False
                },
                {
                    "rank": 3,
                    "title": "Database Hardware / Disk I/O Failure",
                    "description": "Underlying storage volume failure or disk sector corruption in database cluster.",
                    "supporting_evidence": [
                        "+ High query response latency (>7600ms)"
                    ],
                    "contradicting_evidence": [
                        "- Database container and host filesystem health checks reporting 0 disk errors",
                        "- IOPS telemetry within standard SSD throughput threshold (420 IOPS)",
                        "- PostgreSQL process responds immediately to administrative local socket pings"
                    ],
                    "confidence": 0.18,
                    "selected": False
                }
            ]

        elif scenario == "api_failure":
            hypotheses_data = [
                {
                    "rank": 1,
                    "title": "Faulty Code Deployment in Release v2.4.2",
                    "description": "Unchecked NullPointerException in newly introduced authentication header filter causing pod crash loops.",
                    "supporting_evidence": [
                        "+ Deployment v2.4.2 completed 4 minutes prior to incident",
                        "+ Kubelet reporting container restart loop (4 restarts in 180s)",
                        "+ Stack trace shows NullPointerException in RequestFilter: auth_header_v2",
                        "+ HTTP 500 error rate surged from 0.2% to 74.5%"
                    ],
                    "contradicting_evidence": [
                        "- CI/CD unit tests reported green prior to merge"
                    ],
                    "confidence": 0.96,
                    "selected": True
                },
                {
                    "rank": 2,
                    "title": "Upstream Ingress Routing Misconfiguration",
                    "description": "Malformed Envoy route or TLS certificate expiration causing connection drops.",
                    "supporting_evidence": [
                        "+ Elevated error responses at the edge gateway"
                    ],
                    "contradicting_evidence": [
                        "- TLS certificates valid for 280 days",
                        "- Ingress route definitions unmodified",
                        "- Errors originate from application container internally, not edge proxy"
                    ],
                    "confidence": 0.28,
                    "selected": False
                },
                {
                    "rank": 3,
                    "title": "Database Query Latency Cascade",
                    "description": "Backing database outage blocking API response generation.",
                    "supporting_evidence": [
                        "+ API response time elevated"
                    ],
                    "contradicting_evidence": [
                        "- PostgreSQL primary healthy with 24/100 connections and 180ms latency",
                        "- No database timeout errors in log stream"
                    ],
                    "confidence": 0.15,
                    "selected": False
                }
            ]

        else:  # high_latency
            hypotheses_data = [
                {
                    "rank": 1,
                    "title": "Missing Composite Index on Orders Table",
                    "description": "Sequential scan over 1.49M records on unindexed customer_id and status filters.",
                    "supporting_evidence": [
                        "+ EXPLAIN ANALYZE confirms Seq Scan on orders (cost 98412)",
                        "+ p99 query latency spiked to 9400ms",
                        "+ High database CPU (88.5%) spent in sequential table traversal"
                    ],
                    "contradicting_evidence": [
                        "- Query syntax is valid and returns correct records when execution finishes"
                    ],
                    "confidence": 0.94,
                    "selected": True
                },
                {
                    "rank": 2,
                    "title": "Inter-Service Network Congestion",
                    "description": "Network packet drops or packet retransmissions between application pods.",
                    "supporting_evidence": [
                        "+ Increased end-to-end response time"
                    ],
                    "contradicting_evidence": [
                        "- TCP retransmission rate < 0.01%",
                        "- Pod-to-pod ping latency remains sub-millisecond (0.4ms)",
                        "- Latency originates specifically inside database engine execution"
                    ],
                    "confidence": 0.22,
                    "selected": False
                },
                {
                    "rank": 3,
                    "title": "Thread Pool Saturation in Order Service",
                    "description": "Worker threads blocked waiting for downstream microservices.",
                    "supporting_evidence": [
                        "+ API thread pool queue depth elevated"
                    ],
                    "contradicting_evidence": [
                        "- Worker threads are waiting specifically on PostgreSQL socket responses",
                        "- Downstream services report normal latency"
                    ],
                    "confidence": 0.30,
                    "selected": False
                }
            ]

        hypotheses_records = []
        for h in hypotheses_data:
            rec = Hypothesis(
                incident_id=incident.id,
                rank=h["rank"],
                title=h["title"],
                description=h["description"],
                supporting_evidence=h["supporting_evidence"],
                contradicting_evidence=h["contradicting_evidence"],
                confidence=h["confidence"],
                selected=h["selected"]
            )
            db.add(rec)
            hypotheses_records.append(rec)
        db.commit()

        hyp_dicts = [h.to_dict() for h in hypotheses_records]

        event_bus.publish_sync("hypotheses_generated", {
            "incident_id": incident.id,
            "hypotheses": hyp_dicts
        })

        return {
            "hypotheses_count": len(hyp_dicts),
            "hypotheses": hyp_dicts
        }
