"""
Unit tests for ARES Token Accounting and Budget Guardrails.
Verifies initial balance, deductions, ledger records, low-token threshold, and budget exhaustion.
"""

import pytest
from backend.database import SessionLocal, init_db
from backend.models import TokenAccount, TokenTransaction
from backend.tokens import TokenService, InsufficientTokensError, INITIAL_BALANCE, LOW_TOKEN_THRESHOLD


@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    db = SessionLocal()
    TokenService.reset_tokens(db)
    db.close()
    yield


def test_initial_token_balance():
    """Verify default demo session initializes with 10,000 tokens."""
    db = SessionLocal()
    account = TokenService.get_or_create_account(db)
    assert account.balance == INITIAL_BALANCE
    assert account.total_used == 0
    db.close()


def test_token_deduction_and_ledger():
    """Verify that operations deduct tokens and record immutable ledger transactions."""
    db = SessionLocal()
    tx = TokenService.record_usage(
        db=db,
        agent_name="Investigation Agent",
        operation="Hypothesis Generation",
        incident_id="TEST-INC-001",
        custom_cost=100
    )
    assert tx.tokens_used == 100
    assert tx.tokens_remaining == INITIAL_BALANCE - 100
    assert tx.status == "COMPLETED"

    bal = TokenService.get_balance(db)
    assert bal["balance"] == INITIAL_BALANCE - 100
    assert bal["total_used"] == 100
    db.close()


def test_low_token_warning_threshold():
    """Verify is_low flag triggers when balance falls below threshold."""
    db = SessionLocal()
    account = TokenService.get_or_create_account(db)
    account.balance = LOW_TOKEN_THRESHOLD - 50
    db.commit()

    bal = TokenService.get_balance(db)
    assert bal["is_low"] is True
    db.close()


def test_insufficient_tokens_exhaustion_blocks():
    """Verify InsufficientTokensError is raised and blocks agent when budget is exhausted."""
    db = SessionLocal()
    account = TokenService.get_or_create_account(db)
    account.balance = 40  # Less than Hypothesis Generation (100)
    db.commit()

    with pytest.raises(InsufficientTokensError) as exc_info:
        TokenService.check_and_reserve(db, "Hypothesis Generation", "Investigation Agent", "TEST-INC-002")

    assert exc_info.value.required == 100
    assert exc_info.value.available == 40

    # Ensure a REJECTED transaction was recorded
    failed_tx = db.query(TokenTransaction).filter(
        TokenTransaction.incident_id == "TEST-INC-002",
        TokenTransaction.status == "REJECTED"
    ).first()
    assert failed_tx is not None
    db.close()


def test_add_tokens_replenishes_balance():
    """Verify adding tokens increases balance and logs transaction."""
    db = SessionLocal()
    account = TokenService.get_or_create_account(db)
    account.balance = 200
    db.commit()

    updated = TokenService.add_tokens(db, amount=5000)
    assert updated["balance"] == 5200
    db.close()
