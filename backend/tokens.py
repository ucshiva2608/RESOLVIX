"""
Token accounting and credit ledger system for ARES.
Enforces real AI computation budgeting, transaction recording,
low-token warning thresholds, and execution blocking when budget is exhausted.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.models import TokenAccount, TokenTransaction, User


# Configurable operation token costs per Section 5 of specification
TOKEN_COSTS = {
    "Incident Detection": 20,
    "Telemetry Collection": 50,
    "Log Analysis": 80,
    "Metric Analysis": 70,
    "Hypothesis Generation": 100,
    "Runbook Retrieval": 60,
    "Root Cause Analysis": 120,
    "Recovery Planning": 100,
    "Risk Assessment": 60,
    "Remediation Execution": 150,
    "Verification": 100,
    "Postmortem Generation": 100,
    "Replanning Investigation": 110,
}

INITIAL_BALANCE = 10000
LOW_TOKEN_THRESHOLD = 500


class InsufficientTokensError(Exception):
    """Raised when token balance is insufficient for the requested agent operation."""
    def __init__(self, required: int, available: int, operation: str):
        super().__init__(
            f"Token budget exhausted for '{operation}'. Required: {required}, Available: {available}"
        )
        self.required = required
        self.available = available
        self.operation = operation


class TokenService:
    """Manages token transactions, reservations, and budget guardrails."""

    @staticmethod
    def get_or_create_account(db: Session, user_id: int = 1) -> TokenAccount:
        """Fetch or initialize the operator token account."""
        account = db.query(TokenAccount).filter(TokenAccount.user_id == user_id).first()
        if not account:
            # Ensure user exists
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id, username="sre-operator", email="sre@ares.system", role="Lead SRE")
                db.add(user)
                db.commit()

            account = TokenAccount(
                user_id=user_id,
                balance=INITIAL_BALANCE,
                total_used=0,
                initial_balance=INITIAL_BALANCE
            )
            db.add(account)
            db.commit()
            db.refresh(account)
        return account

    @staticmethod
    def get_balance(db: Session, user_id: int = 1) -> Dict[str, Any]:
        """Return current token balance, total used, and low-token status."""
        account = TokenService.get_or_create_account(db, user_id)
        is_low = account.balance < LOW_TOKEN_THRESHOLD
        is_exhausted = account.balance <= 0

        # Calculate agent-by-agent token consumption
        txs = db.query(TokenTransaction).filter(TokenTransaction.status == "COMPLETED").all()
        agent_usage: Dict[str, int] = {}
        for tx in txs:
            agent = tx.agent_name or "System"
            agent_usage[agent] = agent_usage.get(agent, 0) + tx.tokens_used

        return {
            "balance": account.balance,
            "total_used": account.total_used,
            "initial_balance": account.initial_balance,
            "is_low": is_low,
            "is_exhausted": is_exhausted,
            "low_threshold": LOW_TOKEN_THRESHOLD,
            "agent_usage": agent_usage,
            "token_costs": TOKEN_COSTS
        }

    @staticmethod
    def check_and_reserve(db: Session, operation: str, agent_name: str, incident_id: Optional[str] = None, user_id: int = 1) -> int:
        """
        Check if sufficient tokens are available for an operation.
        Raises InsufficientTokensError if not enough tokens remain.
        """
        cost = TOKEN_COSTS.get(operation, 50)
        account = TokenService.get_or_create_account(db, user_id)

        if account.balance < cost:
            # Record failed transaction attempt
            failed_tx = TokenTransaction(
                incident_id=incident_id,
                agent_name=agent_name,
                operation=operation,
                tokens_used=cost,
                tokens_remaining=account.balance,
                status="REJECTED",
                metadata_json={"error": "Insufficient token budget", "required": cost, "available": account.balance}
            )
            db.add(failed_tx)
            db.commit()
            raise InsufficientTokensError(cost, account.balance, operation)

        return cost

    @staticmethod
    def record_usage(
        db: Session,
        agent_name: str,
        operation: str,
        incident_id: Optional[str] = None,
        custom_cost: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: int = 1
    ) -> TokenTransaction:
        """
        Deduct tokens from balance, update total used, and record in immutable ledger.
        """
        cost = custom_cost if custom_cost is not None else TOKEN_COSTS.get(operation, 50)
        account = TokenService.get_or_create_account(db, user_id)

        if account.balance < cost:
            raise InsufficientTokensError(cost, account.balance, operation)

        account.balance -= cost
        account.total_used += cost
        account.updated_at = datetime.now(timezone.utc)

        tx = TokenTransaction(
            incident_id=incident_id,
            agent_name=agent_name,
            operation=operation,
            tokens_used=cost,
            tokens_remaining=account.balance,
            status="COMPLETED",
            metadata_json=metadata or {}
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx

    @staticmethod
    def add_tokens(db: Session, amount: int = 5000, user_id: int = 1) -> Dict[str, Any]:
        """Replenish the operator token budget."""
        account = TokenService.get_or_create_account(db, user_id)
        account.balance += amount
        account.updated_at = datetime.now(timezone.utc)

        tx = TokenTransaction(
            incident_id=None,
            agent_name="Token Authority",
            operation="Deposit Tokens",
            tokens_used=-amount,
            tokens_remaining=account.balance,
            status="COMPLETED",
            metadata_json={"action": "add_tokens", "amount": amount}
        )
        db.add(tx)
        db.commit()
        return TokenService.get_balance(db, user_id)

    @staticmethod
    def reset_tokens(db: Session, user_id: int = 1) -> Dict[str, Any]:
        """Reset token balance back to initial 10,000."""
        account = TokenService.get_or_create_account(db, user_id)
        account.balance = INITIAL_BALANCE
        account.total_used = 0
        account.updated_at = datetime.now(timezone.utc)

        tx = TokenTransaction(
            incident_id=None,
            agent_name="Token Authority",
            operation="Reset Budget",
            tokens_used=0,
            tokens_remaining=INITIAL_BALANCE,
            status="COMPLETED",
            metadata_json={"action": "reset_budget", "balance": INITIAL_BALANCE}
        )
        db.add(tx)
        db.commit()
        return TokenService.get_balance(db, user_id)

    @staticmethod
    def get_transactions(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent token transaction ledger entries."""
        txs = db.query(TokenTransaction).order_by(TokenTransaction.timestamp.desc()).limit(limit).all()
        return [t.to_dict() for t in txs]
