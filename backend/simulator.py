"""
Isolated Simulated Production Environment for ARES.
Maintains live cluster state, metrics, simulated telemetry logs,
failure injectors, and safe remediation tools.
Strictly adheres to safety rules: NO shell, bash, or terminal execution.
"""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class ProductionSimulator:
    """Simulated production cluster environment."""

    SAFE_TOOLS = {
        "rollback_deployment",
        "restart_service",
        "restart_database",
        "optimize_query_simulation",
        "clear_connection_pool_simulation",
        "reset_simulator",
    }

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset the cluster to baseline HEALTHY state."""
        self.state = {
            "system_status": "HEALTHY",
            "api_status": "ONLINE",
            "database_status": "ONLINE",
            "db_connections": 24,
            "max_db_connections": 100,
            "api_error_rate": 0.2,  # percentage (0.2%)
            "response_time": 185.0,  # ms
            "query_latency": 180.0,  # ms
            "cpu_utilization": 18.5,  # percentage
            "memory_utilization": 34.2,  # percentage
            "deployment_version": "v2.4.1",
            "active_incident_id": None,
            "active_scenario": None,
            "remediation_in_progress": False,
            "simulate_verification_failure": False,
            "replanning_iteration": 0,
            "services": {
                "api-gateway": {"status": "HEALTHY", "instances": 4, "error_rate": 0.2},
                "auth-service": {"status": "HEALTHY", "instances": 2, "error_rate": 0.0},
                "order-service": {"status": "HEALTHY", "instances": 3, "error_rate": 0.1},
                "postgresql-primary": {"status": "HEALTHY", "connections": "24/100", "iops": 420},
            },
            "recent_logs": [
                f"[{utcnow()}] [INFO] [api-gateway] Health check status 200 OK across 4 pods",
                f"[{utcnow()}] [INFO] [postgresql-primary] Active connections: 24/100 (idle: 18, active: 6)",
                f"[{utcnow()}] [INFO] [order-service] Processed 142 tx/sec with p95 latency 182ms",
            ]
        }
        return self.get_telemetry()

    def get_telemetry(self) -> Dict[str, Any]:
        """Return a snapshot of current telemetry and metrics."""
        return {
            "timestamp": utcnow(),
            "system_status": self.state["system_status"],
            "api_status": self.state["api_status"],
            "database_status": self.state["database_status"],
            "db_connections": self.state["db_connections"],
            "max_db_connections": self.state["max_db_connections"],
            "api_error_rate": round(self.state["api_error_rate"], 2),
            "response_time": round(self.state["response_time"], 1),
            "query_latency": round(self.state["query_latency"], 1),
            "cpu_utilization": round(self.state["cpu_utilization"], 1),
            "memory_utilization": round(self.state["memory_utilization"], 1),
            "deployment_version": self.state["deployment_version"],
            "active_incident_id": self.state["active_incident_id"],
            "active_scenario": self.state["active_scenario"],
            "simulate_verification_failure": self.state["simulate_verification_failure"],
            "replanning_iteration": self.state["replanning_iteration"],
            "services": self.state["services"],
            "recent_logs": self.state["recent_logs"][-15:],
        }

    # =========================================================================
    # FAILURE INJECTORS
    # =========================================================================

    def inject_database_failure(self, incident_id: str, simulate_fail_once: bool = False) -> Dict[str, Any]:
        """Scenario A: Connection pool exhaustion causing cascading API timeouts."""
        self.state["system_status"] = "CRITICAL"
        self.state["api_status"] = "DEGRADED"
        self.state["database_status"] = "SATURATED"
        self.state["db_connections"] = 99
        self.state["api_error_rate"] = 62.4
        self.state["response_time"] = 7800.0
        self.state["query_latency"] = 7600.0
        self.state["cpu_utilization"] = 82.0
        self.state["active_incident_id"] = incident_id
        self.state["active_scenario"] = "database_failure"
        self.state["simulate_verification_failure"] = simulate_fail_once
        self.state["replanning_iteration"] = 0

        self.state["services"]["postgresql-primary"]["status"] = "CRITICAL"
        self.state["services"]["postgresql-primary"]["connections"] = "99/100"
        self.state["services"]["api-gateway"]["status"] = "DEGRADED"
        self.state["services"]["api-gateway"]["error_rate"] = 62.4

        self.state["recent_logs"].extend([
            f"[{utcnow()}] [CRITICAL] [postgresql-primary] FATAL: remaining connection slots are reserved for non-replication superuser connections (99/100 in use)",
            f"[{utcnow()}] [ERROR] [order-service] PoolAcquireTimeoutError: Timeout 5000ms exceeded waiting for connection checkout from pool",
            f"[{utcnow()}] [ERROR] [api-gateway] HTTP 503 Service Unavailable: upstream connection pool exhausted on /api/v1/orders",
            f"[{utcnow()}] [WARN] [postgresql-primary] Deadlock detected between process 8192 and process 8204 on lock relation 'orders'",
        ])
        return self.get_telemetry()

    def inject_api_failure(self, incident_id: str, simulate_fail_once: bool = False) -> Dict[str, Any]:
        """Scenario B: Bad deployment v2.4.2 causing HTTP 500 crash loops."""
        self.state["system_status"] = "CRITICAL"
        self.state["api_status"] = "CRITICAL"
        self.state["deployment_version"] = "v2.4.2"
        self.state["api_error_rate"] = 74.5
        self.state["response_time"] = 4200.0
        self.state["memory_utilization"] = 91.5
        self.state["active_incident_id"] = incident_id
        self.state["active_scenario"] = "api_failure"
        self.state["simulate_verification_failure"] = simulate_fail_once
        self.state["replanning_iteration"] = 0

        self.state["services"]["api-gateway"]["status"] = "CRITICAL"
        self.state["services"]["api-gateway"]["error_rate"] = 74.5

        self.state["recent_logs"].extend([
            f"[{utcnow()}] [CRITICAL] [api-gateway] Release v2.4.2 deployed 4 minutes ago",
            f"[{utcnow()}] [ERROR] [api-gateway] NullPointerException in RequestFilter: auth_header_v2 not initialized",
            f"[{utcnow()}] [ERROR] [api-gateway] Kubelet: Liveness probe failed for container api-gateway on pod-7c89f5d: HTTP 500",
            f"[{utcnow()}] [CRITICAL] [api-gateway] Pod restart loop detected: 4 restarts in past 180 seconds",
        ])
        return self.get_telemetry()

    def inject_latency_failure(self, incident_id: str, simulate_fail_once: bool = False) -> Dict[str, Any]:
        """Scenario C: Unindexed query / high latency full table scan."""
        self.state["system_status"] = "DEGRADED"
        self.state["api_status"] = "DEGRADED"
        self.state["query_latency"] = 9400.0
        self.state["response_time"] = 9650.0
        self.state["cpu_utilization"] = 88.5
        self.state["api_error_rate"] = 14.8
        self.state["active_incident_id"] = incident_id
        self.state["active_scenario"] = "high_latency"
        self.state["simulate_verification_failure"] = simulate_fail_once
        self.state["replanning_iteration"] = 0

        self.state["services"]["order-service"]["status"] = "DEGRADED"

        self.state["recent_logs"].extend([
            f"[{utcnow()}] [WARN] [postgresql-primary] Slow Query (9400ms): SELECT * FROM orders WHERE customer_id = $1 AND status = $2",
            f"[{utcnow()}] [WARN] [postgresql-primary] EXPLAIN ANALYZE: Seq Scan on orders (cost=0.00..98412.30 rows=1492000 width=384)",
            f"[{utcnow()}] [WARN] [api-gateway] HTTP 504 Gateway Timeout: client requests timing out after 10000ms threshold",
        ])
        return self.get_telemetry()

    # =========================================================================
    # PREDEFINED SAFE REMEDIATION TOOLS (STRICT ALLOW-LIST)
    # =========================================================================

    def restart_database(self, graceful: bool = True) -> Dict[str, Any]:
        """Recycles database service, flushes connection pools, and recovers DB connectivity."""
        if self.state["simulate_verification_failure"] and self.state["replanning_iteration"] == 0:
            # Simulated partial recovery for verification failure demo
            self.state["db_connections"] = 72
            self.state["api_error_rate"] = 28.1
            self.state["response_time"] = 2400.0
            self.state["query_latency"] = 2200.0
            self.state["database_status"] = "DEGRADED"
            self.state["system_status"] = "DEGRADED"
            self.state["recent_logs"].append(
                f"[{utcnow()}] [WARN] [postgresql-primary] Partial recycle completed: 28 lingering locks remained un-terminated"
            )
            return {
                "success": True,
                "action": "restart_database",
                "message": "Database restarted, but lingering lock contention detected.",
                "telemetry": self.get_telemetry()
            }

        # Full successful recovery
        self.state["db_connections"] = 24
        self.state["api_error_rate"] = 0.4
        self.state["response_time"] = 190.0
        self.state["query_latency"] = 180.0
        self.state["cpu_utilization"] = 21.0
        self.state["database_status"] = "ONLINE"
        self.state["api_status"] = "ONLINE"
        self.state["system_status"] = "HEALTHY"
        self.state["services"]["postgresql-primary"]["status"] = "HEALTHY"
        self.state["services"]["postgresql-primary"]["connections"] = "24/100"
        self.state["services"]["api-gateway"]["status"] = "HEALTHY"
        self.state["services"]["api-gateway"]["error_rate"] = 0.4

        self.state["recent_logs"].extend([
            f"[{utcnow()}] [INFO] [postgresql-primary] Service restart initiated gracefully",
            f"[{utcnow()}] [INFO] [postgresql-primary] All deadlocked transactions terminated. Connection pool recycled.",
            f"[{utcnow()}] [INFO] [postgresql-primary] Ready to accept client connections. Active: 24/100",
            f"[{utcnow()}] [INFO] [api-gateway] Upstream connection pool recovered. Error rate dropped to 0.4%",
        ])
        return {
            "success": True,
            "action": "restart_database",
            "message": "Database service successfully recycled. Connection pool restored to 24/100.",
            "telemetry": self.get_telemetry()
        }

    def rollback_deployment(self, target_version: str = "v2.4.1") -> Dict[str, Any]:
        """Rolls back the API gateway to stable release version."""
        self.state["deployment_version"] = target_version
        self.state["api_error_rate"] = 0.1
        self.state["response_time"] = 180.0
        self.state["memory_utilization"] = 35.0
        self.state["api_status"] = "ONLINE"
        self.state["system_status"] = "HEALTHY"
        self.state["services"]["api-gateway"]["status"] = "HEALTHY"
        self.state["services"]["api-gateway"]["error_rate"] = 0.1

        self.state["recent_logs"].extend([
            f"[{utcnow()}] [INFO] [api-gateway] Rolling back deployment to {target_version}",
            f"[{utcnow()}] [INFO] [api-gateway] Pods with {target_version} successfully passed readiness and liveness probes",
            f"[{utcnow()}] [INFO] [api-gateway] Traffic shifted to stable pods. Error rate dropped to 0.1%",
        ])
        return {
            "success": True,
            "action": "rollback_deployment",
            "target_version": target_version,
            "message": f"Deployment successfully rolled back to {target_version}.",
            "telemetry": self.get_telemetry()
        }

    def optimize_query_simulation(self, query_id: str = "idx_orders_customer_status") -> Dict[str, Any]:
        """Creates missing composite index concurrently and refreshes query planner statistics."""
        self.state["query_latency"] = 120.0
        self.state["response_time"] = 145.0
        self.state["cpu_utilization"] = 17.5
        self.state["api_error_rate"] = 0.1
        self.state["api_status"] = "ONLINE"
        self.state["system_status"] = "HEALTHY"
        self.state["services"]["order-service"]["status"] = "HEALTHY"

        self.state["recent_logs"].extend([
            f"[{utcnow()}] [INFO] [postgresql-primary] CREATE INDEX CONCURRENTLY idx_orders_customer_status ON orders(customer_id, status)",
            f"[{utcnow()}] [INFO] [postgresql-primary] ANALYZE orders: Index built in 1420ms. Index Scan replacing Seq Scan",
            f"[{utcnow()}] [INFO] [order-service] Query latency dropped from 9400ms to 120ms (98.7% reduction)",
        ])
        return {
            "success": True,
            "action": "optimize_query_simulation",
            "index_created": query_id,
            "message": "Concurrent composite index created. Query execution plan switched to Index Scan.",
            "telemetry": self.get_telemetry()
        }

    def clear_connection_pool_simulation(self, force: bool = False) -> Dict[str, Any]:
        """Flushes idle connections in client-side connection pools."""
        if self.state["simulate_verification_failure"]:
            # Intentionally simulate verification failure: pool clear didn't fix backend deadlocks!
            self.state["db_connections"] = 72
            self.state["api_error_rate"] = 28.1
            self.state["response_time"] = 2600.0
            return {
                "success": False,
                "action": "clear_connection_pool_simulation",
                "message": "Client pools cleared, but database server still holds 72 deadlocked backend sessions.",
                "telemetry": self.get_telemetry()
            }
        self.state["db_connections"] = 28
        self.state["api_error_rate"] = 0.5
        self.state["response_time"] = 195.0
        return {
            "success": True,
            "action": "clear_connection_pool_simulation",
            "message": "Connection pools flushed. 28 connections remaining.",
            "telemetry": self.get_telemetry()
        }

    def restart_service(self, service_name: str = "api-gateway") -> Dict[str, Any]:
        """Restarts a non-database stateless microservice."""
        if service_name in self.state["services"]:
            self.state["services"][service_name]["status"] = "HEALTHY"
        self.state["recent_logs"].append(
            f"[{utcnow()}] [INFO] [{service_name}] Service pod bounced and restarted with fresh process state"
        )
        return {
            "success": True,
            "action": "restart_service",
            "service": service_name,
            "message": f"Service {service_name} restarted successfully.",
            "telemetry": self.get_telemetry()
        }


# Global singleton instance of production simulator
simulator = ProductionSimulator()
