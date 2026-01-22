"""
Admin UI - Governed Data Analyst Agent
Simple FastAPI web interface for audit logs, replay, and policy viewing.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import asyncpg
import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analyst:analyst_secret@localhost:5432/analyst_db")

# Database pool
db_pool: Optional[asyncpg.Pool] = None

app = FastAPI(title="Admin UI", description="Governance Dashboard")

# Setup templates
templates = Jinja2Templates(directory="templates")


# =============================================================================
# Database
# =============================================================================

async def get_db_pool() -> asyncpg.Pool:
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return db_pool


@app.on_event("startup")
async def startup():
    await get_db_pool()
    logger.info("Admin UI started")


@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/api/audit-logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    user_id: Optional[str] = None,
    tool: Optional[str] = None,
    decision: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get paginated audit logs with filters."""
    pool = await get_db_pool()
    
    # Build query
    conditions = []
    params = []
    param_idx = 1
    
    if user_id:
        conditions.append(f"slack_user_id = ${param_idx}")
        params.append(user_id)
        param_idx += 1
    
    if tool:
        conditions.append(f"tool_name = ${param_idx}")
        params.append(tool)
        param_idx += 1
    
    if decision:
        conditions.append(f"policy_decision = ${param_idx}")
        params.append(decision)
        param_idx += 1
    
    if start_date:
        conditions.append(f"created_at >= ${param_idx}")
        params.append(datetime.fromisoformat(start_date))
        param_idx += 1
    
    if end_date:
        conditions.append(f"created_at <= ${param_idx}")
        params.append(datetime.fromisoformat(end_date))
        param_idx += 1
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    offset = (page - 1) * page_size
    
    async with pool.acquire() as conn:
        # Get total count
        count_query = f"SELECT COUNT(*) FROM internal.audit_logs WHERE {where_clause}"
        total = await conn.fetchval(count_query, *params)
        
        # Get logs
        query = f"""
            SELECT 
                log_id::text,
                request_id::text,
                slack_user_id,
                user_role,
                tool_name,
                tool_inputs_redacted,
                tool_outputs_redacted,
                policy_decision,
                policy_rule_ids,
                latency_ms,
                row_count,
                error_message,
                created_at
            FROM internal.audit_logs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])
        
        rows = await conn.fetch(query, *params)
        
        logs = []
        for row in rows:
            logs.append({
                "log_id": row["log_id"],
                "request_id": row["request_id"],
                "user_id": row["slack_user_id"],
                "role": row["user_role"],
                "tool": row["tool_name"],
                "inputs": json.loads(row["tool_inputs_redacted"]) if row["tool_inputs_redacted"] else {},
                "outputs": json.loads(row["tool_outputs_redacted"]) if row["tool_outputs_redacted"] else {},
                "decision": row["policy_decision"],
                "rule_ids": row["policy_rule_ids"] or [],
                "latency_ms": row["latency_ms"],
                "row_count": row["row_count"],
                "error": row["error_message"],
                "timestamp": row["created_at"].isoformat()
            })
        
        return {
            "logs": logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }


@app.get("/api/replay/{request_id}")
async def get_replay(request_id: str):
    """Get replay timeline for a request."""
    pool = await get_db_pool()
    
    try:
        req_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                tool_name,
                tool_inputs_redacted,
                tool_outputs_redacted,
                policy_decision,
                policy_rule_ids,
                latency_ms,
                created_at
            FROM internal.audit_logs
            WHERE request_id = $1
            ORDER BY created_at
        """, req_uuid)
        
        if not rows:
            raise HTTPException(status_code=404, detail="Request not found")
        
        steps = []
        total_latency = 0
        
        for row in rows:
            steps.append({
                "tool": row["tool_name"],
                "inputs": json.loads(row["tool_inputs_redacted"]) if row["tool_inputs_redacted"] else {},
                "outputs": json.loads(row["tool_outputs_redacted"]) if row["tool_outputs_redacted"] else {},
                "decision": row["policy_decision"],
                "rule_ids": row["policy_rule_ids"] or [],
                "latency_ms": row["latency_ms"] or 0,
                "timestamp": row["created_at"].isoformat()
            })
            total_latency += row["latency_ms"] or 0
        
        return {
            "request_id": request_id,
            "steps": steps,
            "total_latency_ms": total_latency
        }


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        # Get counts by decision
        decision_counts = await conn.fetch("""
            SELECT policy_decision, COUNT(*) as count
            FROM internal.audit_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY policy_decision
        """)
        
        # Get counts by tool
        tool_counts = await conn.fetch("""
            SELECT tool_name, COUNT(*) as count
            FROM internal.audit_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY tool_name
            ORDER BY count DESC
            LIMIT 10
        """)
        
        # Get average latency
        avg_latency = await conn.fetchval("""
            SELECT AVG(latency_ms)
            FROM internal.audit_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
            AND latency_ms IS NOT NULL
        """)
        
        # Get recent denials
        recent_denials = await conn.fetch("""
            SELECT slack_user_id, tool_name, error_message, created_at
            FROM internal.audit_logs
            WHERE policy_decision = 'DENY'
            AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        return {
            "decisions": {row["policy_decision"]: row["count"] for row in decision_counts},
            "tools": {row["tool_name"]: row["count"] for row in tool_counts},
            "avg_latency_ms": round(avg_latency or 0, 2),
            "recent_denials": [
                {
                    "user": row["slack_user_id"],
                    "tool": row["tool_name"],
                    "error": row["error_message"],
                    "timestamp": row["created_at"].isoformat()
                }
                for row in recent_denials
            ]
        }


@app.get("/api/approvals")
async def get_approvals(status: str = "pending"):
    """Get approval requests."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                approval_id::text,
                request_id::text,
                slack_user_id,
                user_role,
                tool_name,
                tool_inputs,
                reason,
                status,
                approver_slack_id,
                approver_decision,
                approver_reason,
                created_at,
                decided_at
            FROM internal.approval_requests
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT 50
        """, status)
        
        return {
            "approvals": [
                {
                    "id": row["approval_id"],
                    "request_id": row["request_id"],
                    "user_id": row["slack_user_id"],
                    "role": row["user_role"],
                    "tool": row["tool_name"],
                    "inputs": json.loads(row["tool_inputs"]) if row["tool_inputs"] else {},
                    "reason": row["reason"],
                    "status": row["status"],
                    "approver": row["approver_slack_id"],
                    "approver_decision": row["approver_decision"],
                    "approver_reason": row["approver_reason"],
                    "created_at": row["created_at"].isoformat(),
                    "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None
                }
                for row in rows
            ]
        }


# =============================================================================
# HTML Pages
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    """Audit logs page."""
    return templates.TemplateResponse("audit.html", {"request": request})


@app.get("/replay/{request_id}", response_class=HTMLResponse)
async def replay_page(request: Request, request_id: str):
    """Replay timeline page."""
    return templates.TemplateResponse("replay.html", {"request": request, "request_id": request_id})


@app.get("/policies", response_class=HTMLResponse)
async def policies_page(request: Request):
    """Policies page."""
    return templates.TemplateResponse("policies.html", {"request": request})


@app.get("/approvals", response_class=HTMLResponse)
async def approvals_page(request: Request):
    """Approvals page."""
    return templates.TemplateResponse("approvals.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin-ui"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
