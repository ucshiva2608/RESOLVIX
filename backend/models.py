"""
SQLAlchemy ORM models for ARES (Autonomous Response Engineering System).
Implements all 15 required entities per architecture specification.
"""

from datetime import datetime, timezone
import json
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from backend.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, default="sre-operator")
    email = Column(String(200), default="sre@ares.system")
    role = Column(String(50), default="Senior SRE")
    created_at = Column(DateTime, default=utcnow)

    token_account = relationship("TokenAccount", back_populates="user", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String(50), primary_key=True, index=True)  # e.g., INC-2026-001
    scenario_type = Column(String(50), nullable=False)  # database_failure, api_failure, high_latency
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="ACTIVE")  # HEALTHY, ACTIVE, INVESTIGATING, APPROVAL_PENDING, REMEDIATING, VERIFYING, RESOLVED, FAILED, ESCALATED
    severity = Column(String(20), default="CRITICAL")  # CRITICAL, HIGH, MEDIUM, LOW
    current_stage = Column(String(50), default="DETECTION")
    replan_count = Column(Integer, default=0)
    initial_symptoms = Column(JSON, default=dict)
    before_metrics = Column(JSON, default=dict)
    after_metrics = Column(JSON, default=dict)
    tokens_consumed = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    events = relationship("IncidentEvent", back_populates="incident", cascade="all, delete-orphan", order_by="IncidentEvent.timestamp")
    agent_executions = relationship("AgentExecution", back_populates="incident", cascade="all, delete-orphan")
    hypotheses = relationship("Hypothesis", back_populates="incident", cascade="all, delete-orphan")
    evidence_items = relationship("Evidence", back_populates="incident", cascade="all, delete-orphan")
    root_cause = relationship("RootCause", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    recovery_plan = relationship("RecoveryPlan", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="incident", cascade="all, delete-orphan")
    tool_calls = relationship("ToolCall", back_populates="incident", cascade="all, delete-orphan")
    verifications = relationship("Verification", back_populates="incident", cascade="all, delete-orphan")
    postmortem = relationship("Postmortem", back_populates="incident", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "scenario_type": self.scenario_type,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "severity": self.severity,
            "current_stage": self.current_stage,
            "replan_count": self.replan_count,
            "initial_symptoms": self.initial_symptoms or {},
            "before_metrics": self.before_metrics or {},
            "after_metrics": self.after_metrics or {},
            "tokens_consumed": self.tokens_consumed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=utcnow)
    stage = Column(String(50), nullable=False)
    agent_name = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="COMPLETED")  # PENDING, RUNNING, COMPLETED, FAILED, WARNING
    metadata_json = Column(JSON, default=dict)

    incident = relationship("Incident", back_populates="events")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "stage": self.stage,
            "agent_name": self.agent_name,
            "title": self.title,
            "message": self.message,
            "status": self.status,
            "metadata": self.metadata_json or {}
        }


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    stage = Column(String(50), nullable=False)
    status = Column(String(50), default="RUNNING")  # RUNNING, COMPLETED, FAILED, PAUSED
    tokens_cost = Column(Integer, default=0)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    incident = relationship("Incident", back_populates="agent_executions")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "agent_name": self.agent_name,
            "stage": self.stage,
            "status": self.status,
            "tokens_cost": self.tokens_cost,
            "input_data": self.input_data or {},
            "output_data": self.output_data or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    rank = Column(Integer, default=1)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    supporting_evidence = Column(JSON, default=list)
    contradicting_evidence = Column(JSON, default=list)
    confidence = Column(Float, default=0.0)  # 0.0 - 1.0 (e.g. 0.95 = 95%)
    selected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="hypotheses")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "rank": self.rank,
            "title": self.title,
            "description": self.description,
            "supporting_evidence": self.supporting_evidence or [],
            "contradicting_evidence": self.contradicting_evidence or [],
            "confidence": self.confidence,
            "confidence_percent": int(self.confidence * 100),
            "selected": self.selected,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    value = Column(String(100), nullable=False)
    baseline_value = Column(String(100), nullable=True)
    unit = Column(String(50), default="")
    status = Column(String(50), default="ANOMALOUS")  # ANOMALOUS, NORMAL, WARNING
    support_level = Column(String(20), default="HIGH")  # HIGH, MEDIUM, LOW
    source = Column(String(100), default="Observability Agent")
    details = Column(Text, nullable=True)
    collected_at = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="evidence_items")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "baseline_value": self.baseline_value,
            "unit": self.unit,
            "status": self.status,
            "support_level": self.support_level,
            "source": self.source,
            "details": self.details,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None
        }


class RootCause(Base):
    __tablename__ = "root_causes"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    explanation = Column(Text, nullable=False)
    confidence = Column(Float, default=0.95)
    evidence_matrix = Column(JSON, default=list)  # list of {evidence, support_level}
    alternatives_considered = Column(JSON, default=list)  # list of {hypothesis, reason_rejected}
    runbook_id = Column(String(50), nullable=True)
    runbook_title = Column(String(255), nullable=True)
    runbook_steps = Column(JSON, default=list)
    determined_at = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="root_cause")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "title": self.title,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "confidence_percent": int(self.confidence * 100),
            "evidence_matrix": self.evidence_matrix or [],
            "alternatives_considered": self.alternatives_considered or [],
            "runbook_id": self.runbook_id,
            "runbook_title": self.runbook_title,
            "runbook_steps": self.runbook_steps or [],
            "determined_at": self.determined_at.isoformat() if self.determined_at else None
        }


class RecoveryPlan(Base):
    __tablename__ = "recovery_plans"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, unique=True)
    proposed_action = Column(String(100), nullable=False)  # safe tool function name
    action_parameters = Column(JSON, default=dict)
    risk_level = Column(String(20), default="HIGH")  # LOW, MEDIUM, HIGH
    risk_reason = Column(Text, nullable=False)
    expected_recovery = Column(JSON, default=dict)
    verification_sla_seconds = Column(Integer, default=60)
    required_approval = Column(Boolean, default=True)
    status = Column(String(50), default="PENDING_APPROVAL")  # PENDING_APPROVAL, APPROVED, REJECTED, EXECUTED
    created_at = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="recovery_plan")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "proposed_action": self.proposed_action,
            "action_parameters": self.action_parameters or {},
            "risk_level": self.risk_level,
            "risk_reason": self.risk_reason,
            "expected_recovery": self.expected_recovery or {},
            "verification_sla_seconds": self.verification_sla_seconds,
            "required_approval": self.required_approval,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    approved_action = Column(String(100), nullable=False)
    risk_level = Column(String(20), nullable=False)
    approved_by = Column(String(100), default="SRE Commander (Human-in-the-Loop)")
    decision = Column(String(50), default="APPROVED")  # APPROVED, REJECTED
    rejection_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="approvals")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "approved_action": self.approved_action,
            "risk_level": self.risk_level,
            "approved_by": self.approved_by,
            "decision": self.decision,
            "rejection_reason": self.rejection_reason,
            "notes": self.notes,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    parameters = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    is_allowed = Column(Boolean, default=True)
    status = Column(String(50), default="SUCCESS")  # SUCCESS, BLOCKED, FAILED
    progress_percent = Column(Integer, default=100)
    executed_by = Column(String(100), default="Execution Agent")
    timestamp = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="tool_calls")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters or {},
            "result": self.result or {},
            "is_allowed": self.is_allowed,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "executed_by": self.executed_by,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, index=True)
    attempt_number = Column(Integer, default=1)
    before_metrics = Column(JSON, default=dict)
    after_metrics = Column(JSON, default=dict)
    recovery_satisfied = Column(Boolean, default=True)
    verification_checks = Column(JSON, default=list)  # list of {check_name, satisfied, details}
    failure_reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="verifications")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "attempt_number": self.attempt_number,
            "before_metrics": self.before_metrics or {},
            "after_metrics": self.after_metrics or {},
            "recovery_satisfied": self.recovery_satisfied,
            "verification_checks": self.verification_checks or [],
            "failure_reason": self.failure_reason,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class TokenAccount(Base):
    __tablename__ = "token_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    balance = Column(Integer, default=10000)
    total_used = Column(Integer, default=0)
    initial_balance = Column(Integer, default=10000)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="token_account")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "balance": self.balance,
            "total_used": self.total_used,
            "initial_balance": self.initial_balance,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class TokenTransaction(Base):
    __tablename__ = "token_transactions"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), nullable=True, index=True)
    agent_name = Column(String(100), nullable=False)
    operation = Column(String(100), nullable=False)
    tokens_used = Column(Integer, nullable=False)
    tokens_remaining = Column(Integer, nullable=False)
    status = Column(String(50), default="COMPLETED")  # COMPLETED, RESERVED, REJECTED, REFUNDED
    metadata_json = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "agent_name": self.agent_name,
            "operation": self.operation,
            "tokens_used": self.tokens_used,
            "tokens_remaining": self.tokens_remaining,
            "status": self.status,
            "metadata": self.metadata_json or {},
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), nullable=True, index=True)
    actor = Column(String(100), nullable=False)  # ARES Agent, Human SRE, System Policy Gate
    action = Column(String(100), nullable=False)
    details = Column(JSON, default=dict)
    risk_level = Column(String(20), default="INFO")  # INFO, LOW, MEDIUM, HIGH, CRITICAL
    timestamp = Column(DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "actor": self.actor,
            "action": self.action,
            "details": self.details or {},
            "risk_level": self.risk_level,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class Postmortem(Base):
    __tablename__ = "postmortems"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(50), ForeignKey("incidents.id"), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    severity = Column(String(20), default="CRITICAL")
    initial_symptoms = Column(JSON, default=dict)
    collected_evidence = Column(JSON, default=list)
    competing_hypotheses = Column(JSON, default=list)
    root_cause = Column(String(255), nullable=False)
    root_cause_details = Column(Text, nullable=False)
    confidence = Column(Float, default=0.95)
    runbook_used = Column(String(100), nullable=True)
    recovery_plan = Column(Text, nullable=False)
    risk_assessment = Column(String(50), default="HIGH")
    human_approval = Column(JSON, default=dict)
    remediation_executed = Column(String(100), nullable=False)
    before_metrics = Column(JSON, default=dict)
    after_metrics = Column(JSON, default=dict)
    verification_result = Column(String(50), default="PASSED")
    tokens_consumed = Column(Integer, default=0)
    replan_count = Column(Integer, default=0)
    timeline_data = Column(JSON, default=list)
    audit_trail = Column(JSON, default=list)
    lessons_learned = Column(JSON, default=list)
    final_status = Column(String(50), default="RESOLVED")
    generated_at = Column(DateTime, default=utcnow)

    incident = relationship("Incident", back_populates="postmortem")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "initial_symptoms": self.initial_symptoms or {},
            "collected_evidence": self.collected_evidence or [],
            "competing_hypotheses": self.competing_hypotheses or [],
            "root_cause": self.root_cause,
            "root_cause_details": self.root_cause_details,
            "confidence": self.confidence,
            "confidence_percent": int(self.confidence * 100),
            "runbook_used": self.runbook_used,
            "recovery_plan": self.recovery_plan,
            "risk_assessment": self.risk_assessment,
            "human_approval": self.human_approval or {},
            "remediation_executed": self.remediation_executed,
            "before_metrics": self.before_metrics or {},
            "after_metrics": self.after_metrics or {},
            "verification_result": self.verification_result,
            "tokens_consumed": self.tokens_consumed,
            "replan_count": self.replan_count,
            "timeline_data": self.timeline_data or [],
            "audit_trail": self.audit_trail or [],
            "lessons_learned": self.lessons_learned or [],
            "final_status": self.final_status,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None
        }
