"""
Base Agent Class for ARES.
Enforces the mandatory Token + Agent flow (Section 37 of specification):
START -> CHECK TOKEN BALANCE -> RESERVE TOKENS -> EXECUTE AGENT ->
RECORD TOKEN USAGE -> STORE RESULT -> LOG AUDIT -> MOVE TO NEXT STAGE.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.models import AgentExecution, IncidentEvent, Incident, AuditLog
from backend.tokens import TokenService, InsufficientTokensError
from backend.event_bus import event_bus


class BaseAgent:
    """Base class for all ARES autonomous response agents."""

    def __init__(self, agent_name: str, stage: str, default_cost: int = 50):
        self.agent_name = agent_name
        self.stage = stage
        self.default_cost = default_cost

    def execute(self, db: Session, incident: Incident, input_data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """
        Execute the agent with token budget checks, database recording,
        audit logging, and real-time SSE event publishing.
        """
        input_data = input_data or {}
        operation_name = kwargs.get("operation", self.agent_name)
        cost = kwargs.get("cost", self.default_cost)

        # 1. CHECK TOKEN BALANCE & RESERVE
        try:
            TokenService.check_and_reserve(
                db=db,
                operation=operation_name,
                agent_name=self.agent_name,
                incident_id=incident.id
            )
        except InsufficientTokensError as e:
            # Emit token budget exhausted event
            event_bus.publish_sync("token_exhausted", {
                "incident_id": incident.id,
                "agent_name": self.agent_name,
                "operation": operation_name,
                "required": e.required,
                "available": e.available,
                "message": f"Token budget exhausted for {self.agent_name}. ARES cannot safely continue."
            })
            # Log audit entry
            audit = AuditLog(
                incident_id=incident.id,
                actor="Safety Gate",
                action="BLOCK_EXECUTION_LOW_TOKENS",
                risk_level="CRITICAL",
                details={"required": e.required, "available": e.available, "agent": self.agent_name}
            )
            db.add(audit)
            db.commit()
            raise

        # 2. RECORD EXECUTION START
        execution = AgentExecution(
            incident_id=incident.id,
            agent_name=self.agent_name,
            stage=self.stage,
            status="RUNNING",
            tokens_cost=cost,
            input_data=input_data,
            started_at=datetime.now(timezone.utc)
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        # Broadcast Agent Started
        event_bus.publish_sync("agent_started", {
            "incident_id": incident.id,
            "agent_name": self.agent_name,
            "stage": self.stage,
            "operation": operation_name,
            "status": "RUNNING",
            "tokens_cost": cost
        })

        try:
            # 3. EXECUTE AGENT SPECIFIC LOGIC
            result = self.run(db=db, incident=incident, input_data=input_data, **kwargs)

            # 4. RECORD TOKEN USAGE (DEDUCTION)
            tx = TokenService.record_usage(
                db=db,
                agent_name=self.agent_name,
                operation=operation_name,
                incident_id=incident.id,
                custom_cost=cost,
                metadata={"execution_id": execution.id, "stage": self.stage}
            )

            # Update incident token counter
            incident.tokens_consumed = (incident.tokens_consumed or 0) + cost
            incident.current_stage = self.stage

            # 5. COMPLETE EXECUTION RECORD
            execution.status = "COMPLETED"
            execution.output_data = result
            execution.completed_at = datetime.now(timezone.utc)

            # 6. RECORD INCIDENT TIMELINE EVENT
            event = IncidentEvent(
                incident_id=incident.id,
                stage=self.stage,
                agent_name=self.agent_name,
                title=kwargs.get("event_title", f"{self.agent_name} completed"),
                message=kwargs.get("event_message", f"Successfully completed {operation_name}."),
                status="COMPLETED",
                metadata_json=result
            )
            db.add(event)
            db.commit()

            # 7. BROADCAST AGENT COMPLETED EVENT
            event_bus.publish_sync("agent_completed", {
                "incident_id": incident.id,
                "agent_name": self.agent_name,
                "stage": self.stage,
                "operation": operation_name,
                "tokens_used": cost,
                "tokens_remaining": tx.tokens_remaining,
                "total_tokens_consumed": incident.tokens_consumed,
                "output": result
            })

            return result

        except Exception as e:
            execution.status = "FAILED"
            execution.output_data = {"error": str(e)}
            execution.completed_at = datetime.now(timezone.utc)
            db.commit()

            event_bus.publish_sync("agent_failed", {
                "incident_id": incident.id,
                "agent_name": self.agent_name,
                "stage": self.stage,
                "error": str(e)
            })
            raise

    def run(self, db: Session, incident: Incident, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Subclasses must implement agent-specific logic."""
        raise NotImplementedError
