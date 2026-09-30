# ARES — Autonomous Response Engineering System
> **Detect. Investigate. Decide. Act. Verify.**

A professional AI-powered autonomous incident investigation and safe remediation platform with real-time telemetry correlation, competing hypotheses, verified runbook execution, strict human approval policy gates, automated SLA verification, adaptive replanning, and full token computation accounting.

---

## 🚀 Quick Start

### 1. Launch ARES
To launch the backend API, real-time SSE stream, and SRE Mission Control dashboard:
```bash
python3 run_ares.py
```

### 2. Access the Application
- **SRE Mission Control Dashboard:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Real-Time Event Stream:** [http://127.0.0.1:8000/api/events](http://127.0.0.1:8000/api/events)

---

## 🌟 Core Architecture & Resolution Flow

```
                 🔴 INCIDENT DETECTED
                         ↓
               🔍 COLLECT EVIDENCE (Observability Agent)
                         ↓
               💡 COMPETING HYPOTHESES (Investigation Agent)
                         ↓
               📚 RUNBOOK SEARCH (Knowledge Agent)
                         ↓
               🎯 ROOT CAUSE ANALYSIS (Root Cause Agent)
                         ↓
               🛠 RECOVERY PLAN & RISK (Planner Agent)
                         ↓
               ⏸ HUMAN APPROVAL GATE (Safety Policy Enforced)
                         ↓
               ⚙ REMEDIATION EXECUTION (Execution Agent)
                         ↓
               🔎 POST-REMEDIATION VERIFICATION (Verification Agent)
                      /     \
             [Passed] /       \ [Failed]
                     ↓         ↓
       🟢 RECOVERY VERIFIED   🔄 AUTONOMOUS REPLANNING (Max 3 Attempts)
                     ↓         │
        📋 POSTMORTEM REPORT   └───→ NEW PLAN → APPROVAL → FIX
                     ↓
             🏁 INCIDENT CLOSED
```

---

## ⚡ Token Accounting & Computation Budget

ARES enforces a real computational/AI operation token budget:
- **Initial Session Budget:** `10,000` tokens
- **Low Budget Warning:** `< 500` tokens
- **Budget Exhaustion Guard:** Blocks remediation execution if tokens are insufficient

### Configurable Operation Costs:
| Operation | Agent | Token Cost |
| :--- | :--- | :--- |
| **Incident Detection** | System Monitor | 20 tokens |
| **Telemetry Collection** | Observability Agent | 50 tokens |
| **Log Analysis** | Observability Agent | 80 tokens |
| **Metric Analysis** | Observability Agent | 70 tokens |
| **Hypothesis Generation** | Investigation Agent | 100 tokens |
| **Runbook Retrieval** | Knowledge Agent | 60 tokens |
| **Root Cause Analysis** | Root Cause Agent | 120 tokens |
| **Recovery Planning** | Planner Agent | 100 tokens |
| **Risk Assessment** | Planner Agent | 60 tokens |
| **Remediation Execution** | Execution Agent | 150 tokens |
| **Post-Remediation Verification**| Verification Agent | 100 tokens |
| **Postmortem Generation** | Postmortem Agent | 100 tokens |
| **Total Standard Cycle** | — | **1,010 tokens** |

Every transaction is recorded in the immutable `TokenTransaction` ledger with timestamp, remaining balance, and execution metadata.

---

## 🛡️ Safety & Execution Sandboxing

ARES strictly enforces zero-trust execution policies:
1. **No Arbitrary Shell/Bash Execution:** Agents have zero access to raw terminals, bash, kubectl, or root database credentials.
2. **Predefined Safe Simulation Tools (Strict Allowlist):**
   - `restart_database()`
   - `rollback_deployment(target_version)`
   - `optimize_query_simulation()`
   - `clear_connection_pool_simulation()`
   - `restart_service(service_name)`
   - `reset_simulator()`
3. **Mandatory Human-in-the-Loop Approval:** HIGH-risk actions (`restart_database`, `rollback_deployment`) are paused at the policy gate until explicit human authorization is granted.
4. **Audit Trail:** Every approval, execution, risk score, and policy intervention is recorded in `AuditLog`.

---

## 🧪 Automated Test Suite

ARES includes a complete unit and integration test suite:
```bash
python3 -m pytest -v
```

### Coverage:
- `test_tokens.py`: Initial balance, transaction ledger, reservation, exhaustion blocking, and deposit.
- `test_safety.py`: Critical safety test proving unapproved HIGH-risk operations and unlisted tools are blocked.
- `test_workflow.py`: End-to-end multi-agent execution, SLA verification, adaptive replanning loop, and postmortem generation.
- `test_api.py`: REST endpoint schema validation and cluster state inspection.

---

## 🎮 Demo Scenarios

### Scenario A — Primary Demo: Database Connection Pool Exhaustion
- **Injection:** 99/100 DB connections, 62.4% API 503 error rate, 7800ms query latency.
- **Root Cause:** Deadlocked backend workers and connection slot starvation (Confidence: 95%).
- **Runbook:** `DB-POOL-003`.
- **Action:** `restart_database` (Risk: HIGH → Pauses at Human Approval Gate).
- **Result:** Connections drop to 24/100, error rate recovers to 0.4%, response time drops to 190ms.

### Scenario B — Bad Deployment Rollback
- **Injection:** Release v2.4.2 rollout causing NullPointerException crash loops (HTTP 500 error rate: 74.5%).
- **Root Cause:** Unhandled exception in authentication header filter.
- **Runbook:** `DEPLOY-ROLLBACK-002`.
- **Action:** `rollback_deployment` to stable `v2.4.1`.
- **Result:** Error rate recovers to 0.1%.

### Scenario C — Slow Query Optimization
- **Injection:** Missing composite index on `orders` table (p99 query latency 9400ms, DB CPU 88.5%).
- **Root Cause:** Sequential table scan across 1.49M records.
- **Runbook:** `PERF-INDEX-001`.
- **Action:** `optimize_query_simulation` (Risk: LOW → Non-blocking concurrent index build).
- **Result:** Latency drops from 9400ms to 120ms (98.7% reduction).

### Scenario D — Verification Failure & Replanning Loop
- **Toggle:** Check "Demo Replan Loop" in the UI.
- **Workflow:** Initial partial remediation fails SLA check (error rate stays at 28.1%). Verification Agent triggers replanning (Attempt 1/3), generates a revised escalation plan, pauses for new approval, and achieves full recovery on the second pass.
