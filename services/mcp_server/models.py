from datetime import datetime
from typing import Optional, Any
import uuid
from pydantic import BaseModel, Field

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
