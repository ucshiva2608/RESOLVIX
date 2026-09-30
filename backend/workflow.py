"""
ARES Resolution Workflow Engine.
Coordinates the multi-agent incident resolution lifecycle:
Detection → Observability → Investigation → Knowledge → Root Cause →
Planner → Risk Assessment → Human Approval Gate → Execution → Verification →
(Success → Postmortem → Resolved) OR (Failure → Replanning → New Plan).
Supports asynchronous execution, pauses at approval gates, and emits live SSE events.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Incident, Approval, AuditLog, IncidentEvent
from backend.simulator import simulator
from backend.tokens import TokenService, InsufficientTokensError
from backend.event_bus import event_bus
from backend.agents import (
    ObservabilityAgent,
    InvestigationAgent,
    KnowledgeAgent,
    RootCauseAgent,
    PlannerAgent,
    ExecutionAgent,
    VerificationAgent,
    ReplanningAgent,
    PostmortemAgent,
    SecurityViolationError
)


class ARESWorkflowEngine:
    """Orchestrates end-to-end autonomous incident response workflow."""

    def __init__(self):
        self.observability_agent = ObservabilityAgent()
        self.investigation_agent = InvestigationAgent()
        self.knowledge_agent = KnowledgeAgent()
        self.root_cause_agent = RootCauseAgent()
        self.planner_agent = PlannerAgent()
        self.execution_agent = ExecutionAgent()
        self.verification_agent = VerificationAgent()
        self.replanning_agent = ReplanningAgent()
        self.postmortem_agent = PostmortemAgent()
        self.step_delay = float(os.getenv("ARES_STEP_DELAY", "0.4"))

    def inject_and_start(
        self,
        scenario: str = "database_failure",
        incident_id: Optional[str] = None,
        simulate_verification_failure: bool = False
    ) -> Incident:
        """
        Inject a failure scenario into the simulator and launch investigation stage.
        """
        db = SessionLocal()
        try:
            # Generate incident ID if not provided
            if not incident_id:
                now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                incident_id = f"INC-{now_str}"

            # Deduct Incident Detection token cost (20 tokens)
            try:
                TokenService.check_and_reserve(db, "Incident Detection", "System Monitor", incident_id)
                TokenService.record_usage(db, "System Monitor", "Incident Detection", incident_id, 20)
            except InsufficientTokensError as e:
                event_bus.publish_sync("token_exhausted", {
                    "incident_id": incident_id,
                    "agent_name": "System Monitor",
                    "operation": "Incident Detection",
                    "required": e.required,
                    "available": e.available
                })
                raise

            # Inject failure into cluster simulator
            telemetry = None
            title = ""
            description = ""
            severity = "CRITICAL"

            if scenario == "database_failure":
                telemetry = simulator.inject_database_failure(incident_id, simulate_fail_once=simulate_verification_failure)
                title = "Database Connection Pool Exhaustion & Cascading API Timeouts"
                description = "PostgreSQL primary pool reached 99/100 connections. API 503 error rate spiked to 62.4%."
            elif scenario == "api_failure":
                telemetry = simulator.inject_api_failure(incident_id, simulate_fail_once=simulate_verification_failure)
                title = "API Ingress Crash Loop Following Release v2.4.2"
                description = "NullPointerException in authentication filter causing container crash loops. 74.5% HTTP 500 error rate."
            else:  # high_latency
                telemetry = simulator.inject_latency_failure(incident_id, simulate_fail_once=simulate_verification_failure)
                title = "Critical Latency Spike on Order Query (p99 9400ms)"
                description = "Missing composite index causing full sequential table scans and 88.5% database CPU utilization."
                severity = "HIGH"

            # Delete existing incident with same ID if present (e.g. re-run or test)
            existing = db.query(Incident).filter(Incident.id == incident_id).first()
            if existing:
                db.delete(existing)
                db.commit()

            # Create Incident in DB
            incident = Incident(
                id=incident_id,
                scenario_type=scenario,
                title=title,
                description=description,
                status="ACTIVE",
                severity=severity,
                current_stage="DETECTION",
                replan_count=0,
                tokens_consumed=20,
                initial_symptoms={
                    "db_connections": f"{telemetry['db_connections']}/{telemetry['max_db_connections']}",
                    "api_error_rate": f"{telemetry['api_error_rate']}%",
                    "response_time": f"{telemetry['response_time']}ms",
                    "query_latency": f"{telemetry['query_latency']}ms",
                },
                before_metrics={
                    "db_connections": f"{telemetry['db_connections']}/{telemetry['max_db_connections']}",
                    "api_error_rate": f"{telemetry['api_error_rate']}%",
                    "response_time": f"{telemetry['response_time']}ms",
                    "query_latency": f"{telemetry['query_latency']}ms",
                }
            )
            db.add(incident)

            # Record initial timeline event
            event = IncidentEvent(
                incident_id=incident_id,
                stage="DETECTION",
                agent_name="System Monitor",
                title="Incident Detected",
                message=f"Anomaly detected: {title}. Initiating ARES autonomous investigation pipeline.",
                status="COMPLETED",
                metadata_json=incident.initial_symptoms
            )
            db.add(event)

            # Record audit log
            audit = AuditLog(
                incident_id=incident_id,
                actor="System Monitor",
                action="INJECT_FAILURE",
                risk_level="CRITICAL",
                details={"scenario": scenario, "telemetry": telemetry}
            )
            db.add(audit)
            db.commit()
            db.refresh(incident)

            event_bus.publish_sync("incident_detected", {
                "incident_id": incident.id,
                "title": incident.title,
                "severity": incident.severity,
                "scenario": scenario,
                "initial_symptoms": incident.initial_symptoms,
                "tokens_consumed": incident.tokens_consumed
            })

            return incident
        finally:
            db.close()

    async def run_investigation_pipeline_async(self, incident_id: str):
        """
        Run the asynchronous investigation stages:
        Observability → Investigation → Knowledge → Root Cause → Planner.
        Pauses automatically if Human Approval is required.
        """
        db = SessionLocal()
        try:
            incident = db.query(Incident).filter(Incident.id == incident_id).first()
            if not incident:
                return

            incident.status = "INVESTIGATING"
            db.commit()

            # Small delay between agent stages to allow rich visual animations on frontend
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 2: Observability Agent
            self.observability_agent.execute(
                db, incident,
                event_title="Observability Telemetry Collected",
                event_message="Metrics, container logs, and deployment states gathered."
            )
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 3: Investigation Agent (Hypotheses)
            self.investigation_agent.execute(
                db, incident,
                event_title="Competing Hypotheses Generated",
                event_message="Generated 3 competing hypotheses with evidence weighting."
            )
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 4: Knowledge Agent (Runbook)
            self.knowledge_agent.execute(
                db, incident,
                event_title="SRE Runbook Retrieved",
                event_message="Matched verified operational procedure from Knowledge Base."
            )
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 5: Root Cause Agent
            self.root_cause_agent.execute(
                db, incident,
                event_title="Root Cause Determined",
                event_message="Evidence matrix analyzed and root cause confirmed."
            )
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 6: Planner Agent & Risk Engine
            plan_res = self.planner_agent.execute(
                db, incident,
                event_title="Recovery Plan Formulated",
                event_message="Structured remediation procedure and blast radius assessed."
            )

            # If approval is NOT required (LOW risk like query optimization), proceed directly
            if not plan_res.get("required_approval", True):
                # Auto-approve low risk with audit
                approval = Approval(
                    incident_id=incident.id,
                    approved_action=plan_res["recovery_plan"]["proposed_action"],
                    risk_level="LOW",
                    approved_by="ARES Autonomous Policy Gate (Auto-Approved LOW Risk)",
                    decision="APPROVED",
                    notes="Autonomous execution authorized by system safety policy for non-blocking operations."
                )
                db.add(approval)
                db.commit()

                await asyncio.sleep(0.4)
                await self.resume_execution_async(incident.id)

        except InsufficientTokensError:
            # Token exhaustion handled in BaseAgent
            pass
        except Exception as e:
            event_bus.publish_sync("pipeline_error", {
                "incident_id": incident_id,
                "error": str(e)
            })
        finally:
            db.close()

    async def approve_and_resume_async(self, incident_id: str, approved_by: str = "SRE Commander") -> Dict[str, Any]:
        """
        Record human approval and resume workflow into Execution and Verification.
        """
        db = SessionLocal()
        try:
            incident = db.query(Incident).filter(Incident.id == incident_id).first()
            if not incident:
                raise ValueError(f"Incident {incident_id} not found")

            from backend.models import RecoveryPlan
            plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).first()
            if not plan:
                raise ValueError(f"No recovery plan found for incident {incident_id}")

            approval = Approval(
                incident_id=incident.id,
                approved_action=plan.proposed_action,
                risk_level=plan.risk_level,
                approved_by=approved_by,
                decision="APPROVED",
                notes=f"Human authorization granted by {approved_by}."
            )
            db.add(approval)

            audit = AuditLog(
                incident_id=incident.id,
                actor=approved_by,
                action="GRANT_HUMAN_APPROVAL",
                risk_level=plan.risk_level,
                details={
                    "approved_action": plan.proposed_action,
                    "risk_level": plan.risk_level
                }
            )
            db.add(audit)

            incident.status = "REMEDIATING"
            incident.current_stage = "REMEDIATION"
            db.commit()

            event_bus.publish_sync("approval_received", {
                "incident_id": incident.id,
                "approved_action": plan.proposed_action,
                "approved_by": approved_by,
                "risk_level": plan.risk_level
            })

            # Resume execution in background
            asyncio.create_task(self.resume_execution_async(incident.id))

            return {
                "status": "APPROVED",
                "incident_id": incident.id,
                "approved_action": plan.proposed_action
            }
        finally:
            db.close()

    async def reject_plan_async(self, incident_id: str, reason: str = "Operator manual override") -> Dict[str, Any]:
        """
        Operator rejects proposed remediation plan. Pauses execution and prompts manual review.
        """
        db = SessionLocal()
        try:
            incident = db.query(Incident).filter(Incident.id == incident_id).first()
            if not incident:
                raise ValueError(f"Incident {incident_id} not found")

            from backend.models import RecoveryPlan
            plan = db.query(RecoveryPlan).filter(RecoveryPlan.incident_id == incident.id).first()

            approval = Approval(
                incident_id=incident.id,
                approved_action=plan.proposed_action if plan else "Unknown",
                risk_level=plan.risk_level if plan else "HIGH",
                approved_by="SRE Commander",
                decision="REJECTED",
                rejection_reason=reason
            )
            db.add(approval)

            incident.status = "REMEDIATION_REJECTED"
            db.commit()

            audit = AuditLog(
                incident_id=incident.id,
                actor="SRE Commander",
                action="REJECT_REMEDIATION",
                risk_level="HIGH",
                details={"reason": reason}
            )
            db.add(audit)
            db.commit()

            event_bus.publish_sync("approval_rejected", {
                "incident_id": incident.id,
                "reason": reason
            })

            return {"status": "REJECTED", "incident_id": incident.id, "reason": reason}
        finally:
            db.close()

    async def resume_execution_async(self, incident_id: str):
        """
        Execute remediation, perform post-remediation verification, and either
        generate postmortem (if passed) or trigger replanning (if failed).
        """
        db = SessionLocal()
        try:
            incident = db.query(Incident).filter(Incident.id == incident_id).first()
            if not incident:
                return

            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 7: Execution Agent
            self.execution_agent.execute(
                db, incident,
                event_title="Remediation Executed",
                event_message="Remediation simulation completed safely."
            )
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            # Stage 8: Verification Agent
            verif_res = self.verification_agent.execute(
                db, incident,
                event_title="Post-Remediation Verification",
                event_message="Before vs After differential comparison evaluated."
            )
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)

            if verif_res.get("recovery_satisfied", False):
                # SUCCESS PATH: Generate Postmortem Report
                self.postmortem_agent.execute(
                    db, incident,
                    event_title="Postmortem Generated",
                    event_message="Comprehensive SRE incident retrospective generated."
                )
            else:
                # FAILURE PATH: Trigger Replanning Loop!
                self.replanning_agent.execute(
                    db, incident,
                    input_data={"failure_reason": verif_res.get("failure_reason")},
                    event_title="Verification Failed - Replanning",
                    event_message="SLA not recovered. ARES initiated dynamic replanning."
                )

        except InsufficientTokensError:
            pass
        except SecurityViolationError as e:
            event_bus.publish_sync("security_violation", {
                "incident_id": incident_id,
                "message": str(e)
            })
        except Exception as e:
            event_bus.publish_sync("execution_error", {
                "incident_id": incident_id,
                "error": str(e)
            })
        finally:
            db.close()

    def reset_system(self) -> Dict[str, Any]:
        """
        Reset system per Section 38:
        - Clear active incident
        - Reset simulator to HEALTHY
        - Reset token balance to 10,000
        - Clear pending approvals
        - Return dashboard to healthy state
        """
        db = SessionLocal()
        try:
            # Reset simulator
            telemetry = simulator.reset()

            # Reset tokens to 10,000
            token_balance = TokenService.reset_tokens(db)

            # Mark any active incident as CLOSED/RESET
            active_incidents = db.query(Incident).filter(Incident.status.in_(["ACTIVE", "INVESTIGATING", "APPROVAL_PENDING", "REMEDIATING", "VERIFYING", "VERIFICATION_FAILED"])).all()
            for inc in active_incidents:
                inc.status = "RESET"
            db.commit()

            # Record Audit Log
            audit = AuditLog(
                incident_id=None,
                actor="System Operator",
                action="RESET_SYSTEM",
                risk_level="INFO",
                details={"action": "System reset to baseline HEALTHY state."}
            )
            db.add(audit)
            db.commit()

            event_bus.publish_sync("system_reset", {
                "telemetry": telemetry,
                "tokens": token_balance
            })

            return {
                "status": "RESET_SUCCESSFUL",
                "telemetry": telemetry,
                "tokens": token_balance
            }
        finally:
            db.close()


# Global workflow engine singleton
workflow_engine = ARESWorkflowEngine()
