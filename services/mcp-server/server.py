"""
MCP Tool Server - Governed Data Analyst Agent
Provides tools for SQL execution, document search, metric lookup, and chart generation
with full policy enforcement via OPA and audit logging.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

import asyncpg
import httpx
import structlog
import vl_convert as vlc
from fastapi import FastAPI, HTTPException
from mcp.server import Server
from mcp.server.fastapi import create_mcp_router
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analyst:analyst_secret@localhost:5432/analyst_db")
OPA_URL = os.getenv("OPA_URL", "http://localhost:8181")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None


# =============================================================================
# Pydantic Models
# =============================================================================

class ToolContext(BaseModel):
    """Context for tool execution including user info and request tracking."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    slack_user_id: str
    role: str
    region: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PolicyInput(BaseModel):
    """Input for OPA policy evaluation."""
    user_id: str
    role: str
    region: Optional[str] = None
    tool: str
    tables: list[dict] = []
    columns: list[str] = []
    query_type: Optional[str] = None
    row_count: Optional[int] = None
    has_limit: bool = True
    metadata: dict = {}


class PolicyDecision(BaseModel):
    """Result from OPA policy evaluation."""
    decision: str  # ALLOW, DENY, REQUIRE_APPROVAL
    rule_ids: list[str] = []
    reason: Optional[str] = None
    constraints: dict = {}  # e.g., {"masked_columns": ["email"], "max_rows": 100}


class SQLResult(BaseModel):
    """Result from SQL execution."""
    success: bool
    data: list[dict] = []
    columns: list[str] = []
    row_count: int = 0
    query_id: str = ""
    latency_ms: int = 0
    query_preview: Optional[str] = None
    error: Optional[str] = None


class DocResult(BaseModel):
    """Result from document search."""
    doc_id: str
    title: str
    snippet: str
    score: float
    section: Optional[str] = None
    metadata: dict = {}


class MetricDefinition(BaseModel):
    """Metric definition from registry."""
    name: str
    display_name: str
    description: str
    owner: Optional[str] = None
    formula: Optional[str] = None
    sql_template: Optional[str] = None
    dimensions: list[str] = []
    tags: list[str] = []


class ChartSpec(BaseModel):
    """Chart specification."""
    chart_type: str
    title: str
    vega_lite_spec: dict
    data_hash: str
    artifact_url: Optional[str] = None


# =============================================================================
# Database Functions
# =============================================================================

async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool."""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return db_pool


async def close_db_pool():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


# =============================================================================
# Policy Client
# =============================================================================

class PolicyClient:
    """Client for OPA policy evaluation."""
    
    def __init__(self, opa_url: str):
        self.opa_url = opa_url
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def evaluate(self, input_data: PolicyInput) -> PolicyDecision:
        """Evaluate policy and return decision."""
        try:
            # Query OPA
            response = await self.client.post(
                f"{self.opa_url}/v1/data/analyst/main",
                json={"input": input_data.model_dump()}
            )
            response.raise_for_status()
            
            result = response.json().get("result", {})
            
            return PolicyDecision(
                decision=result.get("decision", "DENY"),
                rule_ids=result.get("rule_ids", []),
                reason=result.get("reason"),
                constraints=result.get("constraints", {})
            )
        except httpx.HTTPError as e:
            logger.error("OPA request failed", error=str(e))
            # Fail closed - deny on error
            return PolicyDecision(
                decision="DENY",
                rule_ids=["error.opa_unavailable"],
                reason="Policy service unavailable"
            )
    
    async def close(self):
        await self.client.aclose()


policy_client: Optional[PolicyClient] = None


# =============================================================================
# Audit Logger
# =============================================================================

class AuditLogger:
    """Audit logging for tool calls."""
    
    # Patterns for PII redaction
    PII_PATTERNS = [
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL_REDACTED]'),
        (re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'), '[PHONE_REDACTED]'),
        (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD_REDACTED]'),
    ]
    
    @classmethod
    def redact(cls, text: str) -> str:
        """Redact PII from text."""
        if not text:
            return text
        result = text
        for pattern, replacement in cls.PII_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    
    @classmethod
    def redact_dict(cls, data: dict) -> dict:
        """Redact PII from dictionary values."""
        if not data:
            return data
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = cls.redact(value)
            elif isinstance(value, dict):
                result[key] = cls.redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    cls.redact_dict(v) if isinstance(v, dict) 
                    else cls.redact(v) if isinstance(v, str) 
                    else v 
                    for v in value
                ]
            else:
                result[key] = value
        return result
    
    @classmethod
    async def log(
        cls,
        ctx: ToolContext,
        tool_name: str,
        tool_inputs: dict,
        tool_outputs: dict,
        decision: PolicyDecision,
        latency_ms: int,
        row_count: int = 0,
        error: Optional[str] = None
    ):
        """Log tool call to database and structured log."""
        pool = await get_db_pool()
        
        # Redact sensitive data
        inputs_redacted = cls.redact_dict(tool_inputs)
        outputs_redacted = cls.redact_dict(tool_outputs)
        
        try:
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO internal.audit_logs (
                        request_id, slack_user_id, user_role, tool_name,
                        tool_inputs, tool_inputs_redacted,
                        tool_outputs, tool_outputs_redacted,
                        policy_decision, policy_rule_ids, policy_constraints,
                        latency_ms, row_count, error_message
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                    uuid.UUID(ctx.request_id),
                    ctx.slack_user_id,
                    ctx.role,
                    tool_name,
                    json.dumps(tool_inputs),
                    json.dumps(inputs_redacted),
                    json.dumps(tool_outputs),
                    json.dumps(outputs_redacted),
                    decision.decision,
                    decision.rule_ids,
                    json.dumps(decision.constraints),
                    latency_ms,
                    row_count,
                    error
                )
        except Exception as e:
            logger.error("Failed to write audit log", error=str(e))
        
        # Also emit structured log
        logger.info(
            "tool_call",
            request_id=ctx.request_id,
            user_id=ctx.slack_user_id,
            role=ctx.role,
            tool=tool_name,
            decision=decision.decision,
            rule_ids=decision.rule_ids,
            latency_ms=latency_ms,
            row_count=row_count,
            error=error
        )


# =============================================================================
# SQL Query Analyzer
# =============================================================================

class QueryAnalyzer:
    """Analyze SQL queries for governance checks."""
    
    # Dangerous patterns
    DDL_PATTERNS = re.compile(
        r'\b(CREATE|ALTER|DROP|TRUNCATE|RENAME)\b',
        re.IGNORECASE
    )
    DML_PATTERNS = re.compile(
        r'\b(INSERT|UPDATE|DELETE|MERGE)\b',
        re.IGNORECASE
    )
    
    # Table extraction pattern
    TABLE_PATTERN = re.compile(
        r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)'
        r'|\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)',
        re.IGNORECASE
    )
    
    # Column extraction (simplified)
    SELECT_STAR_PATTERN = re.compile(r'\bSELECT\s+\*', re.IGNORECASE)
    
    # Limit check
    LIMIT_PATTERN = re.compile(r'\bLIMIT\s+\d+', re.IGNORECASE)
    AGGREGATE_PATTERN = re.compile(
        r'\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b',
        re.IGNORECASE
    )
    
    @classmethod
    def analyze(cls, query: str) -> dict:
        """Analyze SQL query and extract metadata."""
        result = {
            "is_ddl": bool(cls.DDL_PATTERNS.search(query)),
            "is_dml": bool(cls.DML_PATTERNS.search(query)),
            "has_select_star": bool(cls.SELECT_STAR_PATTERN.search(query)),
            "has_limit": bool(cls.LIMIT_PATTERN.search(query)),
            "is_aggregate": bool(cls.AGGREGATE_PATTERN.search(query)),
            "tables": [],
            "query_type": "SELECT"
        }
        
        # Determine query type
        if result["is_ddl"]:
            result["query_type"] = "DDL"
        elif result["is_dml"]:
            result["query_type"] = "DML"
        
        # Extract tables
        for match in cls.TABLE_PATTERN.finditer(query):
            table = match.group(1) or match.group(2)
            if table:
                parts = table.split(".")
                if len(parts) == 2:
                    result["tables"].append({"schema": parts[0], "table": parts[1]})
                else:
                    result["tables"].append({"schema": "public", "table": parts[0]})
        
        return result


# =============================================================================
# Tool Implementations
# =============================================================================

async def execute_run_sql(
    query: str,
    ctx: ToolContext,
    max_rows: int = 100
) -> SQLResult:
    """Execute SQL query with full governance."""
    start_time = time.time()
    query_id = str(uuid.uuid4())[:8]
    
    # Analyze query
    analysis = QueryAnalyzer.analyze(query)
    
    # Build policy input
    policy_input = PolicyInput(
        user_id=ctx.user_id,
        role=ctx.role,
        region=ctx.region,
        tool="run_sql",
        tables=analysis["tables"],
        query_type=analysis["query_type"],
        has_limit=analysis["has_limit"] or analysis["is_aggregate"]
    )
    
    # Evaluate policy
    decision = await policy_client.evaluate(policy_input)
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    if decision.decision == "DENY":
        result = SQLResult(
            success=False,
            query_id=query_id,
            latency_ms=latency_ms,
            error=f"Access denied: {decision.reason}"
        )
        await AuditLogger.log(
            ctx, "run_sql",
            {"query": query[:500]},
            {"error": decision.reason},
            decision, latency_ms, error=decision.reason
        )
        return result
    
    if decision.decision == "REQUIRE_APPROVAL":
        result = SQLResult(
            success=False,
            query_id=query_id,
            latency_ms=latency_ms,
            error=f"Approval required: {decision.reason}"
        )
        await AuditLogger.log(
            ctx, "run_sql",
            {"query": query[:500]},
            {"requires_approval": True, "reason": decision.reason},
            decision, latency_ms
        )
        return result
    
    # Execute query
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Set user context for RLS
            await conn.execute(
                "SELECT internal.set_user_context($1, $2)",
                ctx.role, ctx.region
            )
            
            # Add LIMIT if not present and not aggregate
            exec_query = query
            if not analysis["has_limit"] and not analysis["is_aggregate"]:
                exec_query = f"{query.rstrip().rstrip(';')} LIMIT {max_rows}"
            
            # Execute
            rows = await conn.fetch(exec_query)
            
            data = [dict(r) for r in rows]
            columns = list(rows[0].keys()) if rows else []
            
            # Apply column masking from constraints
            masked_cols = decision.constraints.get("masked_columns", [])
            if masked_cols:
                for row in data:
                    for col in masked_cols:
                        if col in row:
                            row[col] = "[MASKED]"
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            result = SQLResult(
                success=True,
                data=data,
                columns=columns,
                row_count=len(data),
                query_id=query_id,
                latency_ms=latency_ms,
                query_preview=query[:200] if ctx.role in ["data_analyst", "admin"] else None
            )
            
            await AuditLogger.log(
                ctx, "run_sql",
                {"query": query[:500]},
                {"row_count": len(data), "columns": columns},
                decision, latency_ms, row_count=len(data)
            )
            
            return result
            
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        
        result = SQLResult(
            success=False,
            query_id=query_id,
            latency_ms=latency_ms,
            error=error_msg
        )
        
        await AuditLogger.log(
            ctx, "run_sql",
            {"query": query[:500]},
            {"error": error_msg},
            decision, latency_ms, error=error_msg
        )
        
        return result


async def execute_search_docs(
    query: str,
    ctx: ToolContext,
    top_k: int = 5
) -> list[DocResult]:
    """Search documents with ACL filtering."""
    start_time = time.time()
    
    # Evaluate policy
    policy_input = PolicyInput(
        user_id=ctx.user_id,
        role=ctx.role,
        tool="search_docs"
    )
    decision = await policy_client.evaluate(policy_input)
    
    if decision.decision == "DENY":
        await AuditLogger.log(
            ctx, "search_docs",
            {"query": query},
            {"error": decision.reason},
            decision, int((time.time() - start_time) * 1000)
        )
        return []
    
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # For now, use simple text search (in production, use embeddings)
            # ACL filtering based on role
            acl_filter = "ARRAY['public']"
            if ctx.role in ["data_analyst", "admin"]:
                acl_filter = "ARRAY['public', 'finance_only', 'internal']"
            elif ctx.role == "marketing":
                acl_filter = "ARRAY['public', 'marketing_only']"
            
            rows = await conn.fetch(f"""
                SELECT 
                    d.doc_id::text,
                    d.title,
                    dc.content as snippet,
                    similarity(dc.content, $1) as score,
                    d.doc_type as section,
                    d.metadata
                FROM internal.doc_chunks dc
                JOIN internal.documents d ON dc.doc_id = d.doc_id
                WHERE dc.content ILIKE '%' || $1 || '%'
                  AND d.acl_tags && {acl_filter}::text[]
                ORDER BY similarity(dc.content, $1) DESC
                LIMIT $2
            """, query, top_k)
            
            results = [
                DocResult(
                    doc_id=str(r["doc_id"]),
                    title=r["title"],
                    snippet=r["snippet"][:500],
                    score=float(r["score"]) if r["score"] else 0.5,
                    section=r["section"],
                    metadata=r["metadata"] or {}
                )
                for r in rows
            ]
            
            latency_ms = int((time.time() - start_time) * 1000)
            await AuditLogger.log(
                ctx, "search_docs",
                {"query": query, "top_k": top_k},
                {"result_count": len(results)},
                decision, latency_ms
            )
            
            return results
            
    except Exception as e:
        logger.error("search_docs failed", error=str(e))
        return []


async def execute_explain_metric(
    metric_name: str,
    ctx: ToolContext
) -> Optional[MetricDefinition]:
    """Look up metric definition from registry."""
    start_time = time.time()
    
    # Evaluate policy
    policy_input = PolicyInput(
        user_id=ctx.user_id,
        role=ctx.role,
        tool="explain_metric"
    )
    decision = await policy_client.evaluate(policy_input)
    
    if decision.decision == "DENY":
        await AuditLogger.log(
            ctx, "explain_metric",
            {"metric_name": metric_name},
            {"error": decision.reason},
            decision, int((time.time() - start_time) * 1000)
        )
        return None
    
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT name, display_name, description, owner, formula,
                       sql_template, dimensions, tags
                FROM internal.metrics
                WHERE LOWER(name) = LOWER($1)
                   OR LOWER(display_name) ILIKE '%' || LOWER($1) || '%'
                LIMIT 1
            """, metric_name)
            
            if not row:
                return None
            
            result = MetricDefinition(
                name=row["name"],
                display_name=row["display_name"],
                description=row["description"],
                owner=row["owner"],
                formula=row["formula"],
                sql_template=row["sql_template"],
                dimensions=row["dimensions"] or [],
                tags=row["tags"] or []
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            await AuditLogger.log(
                ctx, "explain_metric",
                {"metric_name": metric_name},
                {"found": True, "metric": result.name},
                decision, latency_ms
            )
            
            return result
            
    except Exception as e:
        logger.error("explain_metric failed", error=str(e))
        return None


async def execute_generate_chart(
    chart_type: str,
    data: list[dict],
    title: str,
    x_field: str,
    y_field: str,
    color_field: Optional[str],
    ctx: ToolContext,
    render_image: bool = True
) -> ChartSpec:
    """Generate Vega-Lite chart specification and optionally render to PNG."""
    start_time = time.time()
    
    # Evaluate policy
    policy_input = PolicyInput(
        user_id=ctx.user_id,
        role=ctx.role,
        tool="generate_chart"
    )
    decision = await policy_client.evaluate(policy_input)
    
    if decision.decision == "DENY":
        await AuditLogger.log(
            ctx, "generate_chart",
            {"chart_type": chart_type, "title": title},
            {"error": decision.reason},
            decision, int((time.time() - start_time) * 1000)
        )
        raise HTTPException(status_code=403, detail=decision.reason)
    
    # Infer x-axis type (temporal for date fields, nominal otherwise)
    x_type = "nominal"
    if data and len(data) > 0:
        sample_value = data[0].get(x_field)
        if isinstance(sample_value, str) and (
            "-" in str(sample_value) or "/" in str(sample_value)
        ):
            # Likely a date string
            x_type = "temporal"
    
    # Build Vega-Lite spec with better styling
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": {
            "text": title,
            "fontSize": 16,
            "fontWeight": "bold"
        },
        "width": 600,
        "height": 400,
        "data": {"values": data},
        "mark": {
            "type": chart_type,
            "tooltip": True
        },
        "encoding": {
            "x": {
                "field": x_field, 
                "type": x_type,
                "axis": {"labelAngle": -45}
            },
            "y": {
                "field": y_field, 
                "type": "quantitative",
                "axis": {"format": "~s"}
            }
        },
        "config": {
            "background": "#ffffff",
            "view": {"stroke": "transparent"}
        }
    }
    
    if color_field:
        spec["encoding"]["color"] = {"field": color_field, "type": "nominal"}
    
    # Create data hash for replay/caching
    data_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    
    # Render to PNG if requested
    artifact_url = None
    if render_image:
        try:
            # Create charts directory if not exists
            charts_dir = os.path.join(os.path.dirname(__file__), "charts")
            os.makedirs(charts_dir, exist_ok=True)
            
            # Generate unique filename
            chart_filename = f"chart_{ctx.request_id[:8]}_{data_hash}.png"
            chart_path = os.path.join(charts_dir, chart_filename)
            
            # Render Vega-Lite to PNG using vl-convert
            png_data = vlc.vegalite_to_png(
                vl_spec=json.dumps(spec),
                scale=2  # 2x resolution for clarity
            )
            
            # Write to file
            with open(chart_path, "wb") as f:
                f.write(png_data)
            
            artifact_url = chart_path
            logger.info("Chart rendered", path=chart_path, size=len(png_data))
            
        except Exception as e:
            logger.error("Chart rendering failed", error=str(e))
            # Continue without image - spec is still valid
    
    result = ChartSpec(
        chart_type=chart_type,
        title=title,
        vega_lite_spec=spec,
        data_hash=data_hash,
        artifact_url=artifact_url
    )
    
    latency_ms = int((time.time() - start_time) * 1000)
    await AuditLogger.log(
        ctx, "generate_chart",
        {"chart_type": chart_type, "title": title, "data_points": len(data)},
        {"data_hash": data_hash, "rendered": artifact_url is not None},
        decision, latency_ms
    )
    
    return result


# =============================================================================
# MCP Server Setup
# =============================================================================

mcp_server = Server("analyst-mcp-server")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="run_sql",
            description="Execute SQL query on the data warehouse with governance checks. "
                       "Only SELECT queries on allowed schemas based on user role.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute"
                    },
                    "user_id": {"type": "string"},
                    "slack_user_id": {"type": "string"},
                    "role": {"type": "string"},
                    "region": {"type": "string"},
                    "request_id": {"type": "string"}
                },
                "required": ["query", "user_id", "slack_user_id", "role"]
            }
        ),
        Tool(
            name="search_docs",
            description="Search internal documentation including metric definitions, "
                       "data dictionary, and business glossary.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5
                    },
                    "user_id": {"type": "string"},
                    "slack_user_id": {"type": "string"},
                    "role": {"type": "string"},
                    "request_id": {"type": "string"}
                },
                "required": ["query", "user_id", "slack_user_id", "role"]
            }
        ),
        Tool(
            name="explain_metric",
            description="Get the definition, formula, and SQL template for a business metric.",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "Name of the metric (e.g., 'cac', 'churn_rate', 'mrr')"
                    },
                    "user_id": {"type": "string"},
                    "slack_user_id": {"type": "string"},
                    "role": {"type": "string"},
                    "request_id": {"type": "string"}
                },
                "required": ["metric_name", "user_id", "slack_user_id", "role"]
            }
        ),
        Tool(
            name="generate_chart",
            description="Generate a Vega-Lite chart specification from data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "point", "area"],
                        "description": "Type of chart"
                    },
                    "data": {
                        "type": "array",
                        "description": "Data points for the chart"
                    },
                    "title": {"type": "string"},
                    "x_field": {"type": "string"},
                    "y_field": {"type": "string"},
                    "color_field": {"type": "string"},
                    "user_id": {"type": "string"},
                    "slack_user_id": {"type": "string"},
                    "role": {"type": "string"},
                    "request_id": {"type": "string"}
                },
                "required": ["chart_type", "data", "title", "x_field", "y_field", 
                            "user_id", "slack_user_id", "role"]
            }
        )
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    # Build context
    ctx = ToolContext(
        request_id=arguments.get("request_id", str(uuid.uuid4())),
        user_id=arguments.get("user_id", "unknown"),
        slack_user_id=arguments.get("slack_user_id", "unknown"),
        role=arguments.get("role", "intern"),
        region=arguments.get("region")
    )
    
    if name == "run_sql":
        result = await execute_run_sql(arguments["query"], ctx)
        return [TextContent(type="text", text=result.model_dump_json())]
    
    elif name == "search_docs":
        results = await execute_search_docs(
            arguments["query"], ctx, 
            arguments.get("top_k", 5)
        )
        return [TextContent(type="text", text=json.dumps([r.model_dump() for r in results]))]
    
    elif name == "explain_metric":
        result = await execute_explain_metric(arguments["metric_name"], ctx)
        if result:
            return [TextContent(type="text", text=result.model_dump_json())]
        return [TextContent(type="text", text=json.dumps({"error": "Metric not found"}))]
    
    elif name == "generate_chart":
        result = await execute_generate_chart(
            arguments["chart_type"],
            arguments["data"],
            arguments["title"],
            arguments["x_field"],
            arguments["y_field"],
            arguments.get("color_field"),
            ctx
        )
        return [TextContent(type="text", text=result.model_dump_json())]
    
    else:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# =============================================================================
# FastAPI App
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global policy_client
    
    # Startup
    logger.info("Starting MCP Tool Server")
    await get_db_pool()
    policy_client = PolicyClient(OPA_URL)
    
    yield
    
    # Shutdown
    logger.info("Shutting down MCP Tool Server")
    await close_db_pool()
    if policy_client:
        await policy_client.close()


app = FastAPI(
    title="MCP Tool Server",
    description="Governed tool server for data analyst agent",
    version="1.0.0",
    lifespan=lifespan
)

# Mount MCP router
mcp_router = create_mcp_router(mcp_server)
app.include_router(mcp_router, prefix="/mcp")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mcp-server"}


@app.get("/tools")
async def get_tools():
    """List available tools."""
    tools = await list_tools()
    return {"tools": [t.model_dump() for t in tools]}


# Direct REST endpoints for easier testing
@app.post("/api/run_sql")
async def api_run_sql(
    query: str,
    user_id: str,
    slack_user_id: str,
    role: str,
    region: Optional[str] = None,
    request_id: Optional[str] = None
):
    """REST endpoint for SQL execution."""
    ctx = ToolContext(
        request_id=request_id or str(uuid.uuid4()),
        user_id=user_id,
        slack_user_id=slack_user_id,
        role=role,
        region=region
    )
    return await execute_run_sql(query, ctx)


@app.post("/api/search_docs")
async def api_search_docs(
    query: str,
    user_id: str,
    slack_user_id: str,
    role: str,
    top_k: int = 5,
    request_id: Optional[str] = None
):
    """REST endpoint for document search."""
    ctx = ToolContext(
        request_id=request_id or str(uuid.uuid4()),
        user_id=user_id,
        slack_user_id=slack_user_id,
        role=role
    )
    return await execute_search_docs(query, ctx, top_k)


@app.post("/api/explain_metric")
async def api_explain_metric(
    metric_name: str,
    user_id: str,
    slack_user_id: str,
    role: str,
    request_id: Optional[str] = None
):
    """REST endpoint for metric lookup."""
    ctx = ToolContext(
        request_id=request_id or str(uuid.uuid4()),
        user_id=user_id,
        slack_user_id=slack_user_id,
        role=role
    )
    return await execute_explain_metric(metric_name, ctx)


class ChartRequest(BaseModel):
    """Request body for chart generation."""
    chart_type: str
    data: list[dict]
    title: str
    x_field: str
    y_field: str
    color_field: Optional[str] = None
    user_id: str
    slack_user_id: str
    role: str
    region: Optional[str] = None
    request_id: Optional[str] = None


@app.post("/api/generate_chart")
async def api_generate_chart(request: ChartRequest):
    """REST endpoint for chart generation with image rendering."""
    ctx = ToolContext(
        request_id=request.request_id or str(uuid.uuid4()),
        user_id=request.user_id,
        slack_user_id=request.slack_user_id,
        role=request.role,
        region=request.region
    )
    return await execute_generate_chart(
        chart_type=request.chart_type,
        data=request.data,
        title=request.title,
        x_field=request.x_field,
        y_field=request.y_field,
        color_field=request.color_field,
        ctx=ctx,
        render_image=True
    )


@app.get("/charts/{filename}")
async def get_chart_image(filename: str):
    """Serve rendered chart images."""
    from fastapi.responses import FileResponse
    charts_dir = os.path.join(os.path.dirname(__file__), "charts")
    chart_path = os.path.join(charts_dir, filename)
    
    if not os.path.exists(chart_path):
        raise HTTPException(status_code=404, detail="Chart not found")
    
    return FileResponse(chart_path, media_type="image/png")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

