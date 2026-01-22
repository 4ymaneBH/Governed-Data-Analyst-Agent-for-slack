"""
Agent Service - Governed Data Analyst Agent
FastAPI service with LangGraph workflow for processing user questions.
Uses Ollama for local LLM inference.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Annotated, Optional, TypedDict

import asyncpg
import httpx
import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analyst:analyst_secret@localhost:5432/analyst_db")

# Database pool
db_pool: Optional[asyncpg.Pool] = None


# =============================================================================
# Pydantic Models
# =============================================================================

class QuestionType(str, Enum):
    METRIC = "metric"
    SQL_ANALYSIS = "sql_analysis"
    DOCUMENT = "document"
    CHART = "chart"
    UNKNOWN = "unknown"


class UserContext(BaseModel):
    """User context for the request."""
    user_id: str
    slack_user_id: str
    role: str
    region: Optional[str] = None
    channel_id: Optional[str] = None
    thread_ts: Optional[str] = None


class Question(BaseModel):
    """Input question from user."""
    text: str
    context: UserContext
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Evidence(BaseModel):
    """Evidence supporting the answer."""
    type: str  # metric, document, sql_result, chart
    source: str
    content: Any
    relevance: float = 1.0


class ToolCall(BaseModel):
    """Record of a tool call."""
    tool: str
    inputs: dict
    outputs: Any
    decision: str
    latency_ms: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Answer(BaseModel):
    """Complete answer with evidence."""
    request_id: str
    question: str
    answer_text: str
    evidence: list[Evidence] = []
    tool_calls: list[ToolCall] = []
    requires_approval: bool = False
    approval_reason: Optional[str] = None
    confidence: float = 0.0
    latency_ms: int = 0


class ReplayTimeline(BaseModel):
    """Timeline for replay/explainability."""
    request_id: str
    question: str
    steps: list[dict]
    final_answer: str
    total_latency_ms: int


# =============================================================================
# LangGraph State
# =============================================================================

class AgentState(TypedDict):
    """State for the agent workflow."""
    request_id: str
    question: str
    user_context: dict
    question_type: str
    
    # Retrieved context
    metrics: list
    documents: list
    
    # Query planning
    planned_query: str
    query_analysis: dict
    
    # Tool results
    sql_result: dict
    chart_spec: dict
    
    # Decision tracking
    policy_decision: str
    approval_required: bool
    approval_reason: str
    
    # Evidence and answer
    evidence: list
    tool_calls: list
    final_answer: str
    confidence: float
    error: str


# =============================================================================
# Ollama Client
# =============================================================================

class OllamaClient:
    """Client for Ollama LLM."""
    
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def generate(self, prompt: str, system: str = None) -> str:
        """Generate text completion."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
            if system:
                payload["system"] = system
            
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error("Ollama request failed", error=str(e))
            raise
    
    async def chat(self, messages: list[dict], system: str = None) -> str:
        """Chat completion."""
        try:
            all_messages = []
            if system:
                all_messages.append({"role": "system", "content": system})
            all_messages.extend(messages)
            
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": all_messages,
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except Exception as e:
            logger.error("Ollama chat failed", error=str(e))
            raise
    
    async def close(self):
        await self.client.aclose()


# =============================================================================
# MCP Client
# =============================================================================

class MCPClient:
    """Client for MCP Tool Server."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool."""
        try:
            response = await self.client.post(
                f"{self.base_url}/api/{tool_name}",
                params=arguments
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("MCP tool call failed", tool=tool_name, error=str(e))
            return {"error": str(e)}
    
    async def run_sql(self, query: str, ctx: dict) -> dict:
        """Execute SQL query."""
        return await self.call_tool("run_sql", {
            "query": query,
            **ctx
        })
    
    async def search_docs(self, query: str, ctx: dict, top_k: int = 5) -> list:
        """Search documents."""
        result = await self.call_tool("search_docs", {
            "query": query,
            "top_k": top_k,
            **ctx
        })
        return result if isinstance(result, list) else []
    
    async def explain_metric(self, metric_name: str, ctx: dict) -> dict:
        """Get metric definition."""
        return await self.call_tool("explain_metric", {
            "metric_name": metric_name,
            **ctx
        })
    
    async def close(self):
        await self.client.aclose()


# Global clients
ollama_client: Optional[OllamaClient] = None
mcp_client: Optional[MCPClient] = None


# =============================================================================
# LangGraph Nodes
# =============================================================================

SYSTEM_PROMPT = """You are a helpful data analyst assistant. You answer business questions 
by querying databases and explaining metrics. Always be clear and concise.
When analyzing data, explain your methodology and cite your sources."""

INTENT_PROMPT = """Classify this business question into one of these categories:
- metric: Questions about specific KPIs or metrics (e.g., "What is our CAC?")
- sql_analysis: Questions requiring data analysis (e.g., "Top 10 customers by revenue")
- document: Questions about definitions or documentation
- chart: Requests for visualizations

Question: {question}

Respond with just the category name (metric, sql_analysis, document, or chart):"""

SQL_GENERATION_PROMPT = """Generate a SQL query to answer this question.

Available tables:
- reporting.daily_kpis (date, region, channel, revenue, marketing_spend, new_customers, churned_customers, active_users, cac, churn_rate, mrr, arr)
- reporting.customers (customer_id, region, industry, plan, status, mrr, arr, signup_date, last_active_date, employee_count)
- reporting.monthly_kpis (view: month, region, aggregated metrics)
- reporting.customer_summary (view: by region and industry)

{context}

Question: {question}

Respond with ONLY the SQL query, no explanation:"""

ANSWER_PROMPT = """Based on the following evidence, provide a clear and helpful answer to the user's question.

Question: {question}

Evidence:
{evidence}

Provide a professional, data-driven answer. Include specific numbers and cite sources where relevant.
If the data shows trends, explain them. Keep your response focused and actionable."""


async def parse_intent(state: AgentState) -> AgentState:
    """Parse the question and determine intent."""
    question = state["question"]
    
    try:
        prompt = INTENT_PROMPT.format(question=question)
        response = await ollama_client.generate(prompt)
        
        # Parse response
        intent = response.strip().lower()
        if intent not in ["metric", "sql_analysis", "document", "chart"]:
            intent = "sql_analysis"  # Default
        
        state["question_type"] = intent
        logger.info("Intent classified", question=question[:50], intent=intent)
        
    except Exception as e:
        logger.error("Intent parsing failed", error=str(e))
        state["question_type"] = "sql_analysis"
        state["error"] = str(e)
    
    return state


async def retrieve_context(state: AgentState) -> AgentState:
    """Retrieve relevant metrics and documents."""
    question = state["question"]
    ctx = state["user_context"]
    
    tool_calls = state.get("tool_calls", [])
    evidence = state.get("evidence", [])
    
    try:
        # Search for relevant documents
        start = time.time()
        docs = await mcp_client.search_docs(question, ctx, top_k=3)
        latency = int((time.time() - start) * 1000)
        
        if docs and not isinstance(docs, dict):
            state["documents"] = docs
            tool_calls.append(ToolCall(
                tool="search_docs",
                inputs={"query": question},
                outputs={"count": len(docs)},
                decision="ALLOW",
                latency_ms=latency
            ).model_dump())
            
            for doc in docs[:2]:
                evidence.append(Evidence(
                    type="document",
                    source=doc.get("title", "Unknown"),
                    content=doc.get("snippet", "")[:300],
                    relevance=doc.get("score", 0.5)
                ).model_dump())
        
        # Try to find relevant metric definitions
        # Extract potential metric names from question
        metric_keywords = ["cac", "churn", "mrr", "arr", "revenue", "arpu", "ltv", "dau"]
        for keyword in metric_keywords:
            if keyword in question.lower():
                start = time.time()
                metric = await mcp_client.explain_metric(keyword, ctx)
                latency = int((time.time() - start) * 1000)
                
                if metric and not metric.get("error"):
                    state["metrics"] = state.get("metrics", []) + [metric]
                    tool_calls.append(ToolCall(
                        tool="explain_metric",
                        inputs={"metric_name": keyword},
                        outputs={"found": True},
                        decision="ALLOW",
                        latency_ms=latency
                    ).model_dump())
                    
                    evidence.append(Evidence(
                        type="metric",
                        source=metric.get("display_name", keyword),
                        content=f"{metric.get('description', '')} Formula: {metric.get('formula', 'N/A')}",
                        relevance=1.0
                    ).model_dump())
                break
        
        state["tool_calls"] = tool_calls
        state["evidence"] = evidence
        
    except Exception as e:
        logger.error("Context retrieval failed", error=str(e))
        state["error"] = str(e)
    
    return state


async def plan_query(state: AgentState) -> AgentState:
    """Plan the SQL query if needed."""
    if state["question_type"] not in ["sql_analysis", "metric", "chart"]:
        return state
    
    question = state["question"]
    
    # Build context from retrieved info
    context_parts = []
    for metric in state.get("metrics", []):
        if metric.get("sql_template"):
            context_parts.append(f"Metric {metric['name']}: {metric['sql_template']}")
    
    context = "\n".join(context_parts) if context_parts else ""
    
    try:
        prompt = SQL_GENERATION_PROMPT.format(
            question=question,
            context=context
        )
        
        response = await ollama_client.generate(prompt)
        
        # Clean up the SQL
        sql = response.strip()
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[1] if "\n" in sql else sql
        if sql.endswith("```"):
            sql = sql.rsplit("```", 1)[0]
        sql = sql.strip()
        
        state["planned_query"] = sql
        logger.info("Query planned", query=sql[:100])
        
    except Exception as e:
        logger.error("Query planning failed", error=str(e))
        state["error"] = str(e)
    
    return state


async def execute_tools(state: AgentState) -> AgentState:
    """Execute the planned SQL query."""
    if not state.get("planned_query"):
        return state
    
    query = state["planned_query"]
    ctx = state["user_context"]
    
    tool_calls = state.get("tool_calls", [])
    evidence = state.get("evidence", [])
    
    try:
        start = time.time()
        result = await mcp_client.run_sql(query, ctx)
        latency = int((time.time() - start) * 1000)
        
        # Check for errors or policy decisions
        if result.get("error"):
            if "Access denied" in result["error"]:
                state["policy_decision"] = "DENY"
                state["error"] = result["error"]
            elif "Approval required" in result["error"]:
                state["approval_required"] = True
                state["approval_reason"] = result["error"]
                state["policy_decision"] = "REQUIRE_APPROVAL"
            else:
                state["error"] = result["error"]
        else:
            state["sql_result"] = result
            state["policy_decision"] = "ALLOW"
            
            # Add to evidence
            if result.get("data"):
                evidence.append(Evidence(
                    type="sql_result",
                    source="Database Query",
                    content=result["data"][:10],  # First 10 rows
                    relevance=1.0
                ).model_dump())
        
        tool_calls.append(ToolCall(
            tool="run_sql",
            inputs={"query": query[:200]},
            outputs={"row_count": result.get("row_count", 0), "success": result.get("success", False)},
            decision=state.get("policy_decision", "UNKNOWN"),
            latency_ms=latency
        ).model_dump())
        
        state["tool_calls"] = tool_calls
        state["evidence"] = evidence
        
    except Exception as e:
        logger.error("Tool execution failed", error=str(e))
        state["error"] = str(e)
    
    return state


async def validate_results(state: AgentState) -> AgentState:
    """Validate results and check for weak evidence."""
    evidence = state.get("evidence", [])
    
    # Calculate confidence based on evidence
    if not evidence:
        state["confidence"] = 0.2
    elif state.get("sql_result", {}).get("success"):
        state["confidence"] = 0.9
    elif len(evidence) >= 2:
        state["confidence"] = 0.7
    else:
        state["confidence"] = 0.5
    
    return state


async def compose_answer(state: AgentState) -> AgentState:
    """Compose the final answer from evidence."""
    question = state["question"]
    evidence = state.get("evidence", [])
    
    # Handle denial
    if state.get("policy_decision") == "DENY":
        state["final_answer"] = f"I'm unable to answer this question. {state.get('error', 'Access denied.')}"
        return state
    
    # Handle approval required
    if state.get("approval_required"):
        state["final_answer"] = f"This request requires approval. {state.get('approval_reason', '')}"
        return state
    
    # Format evidence for prompt
    evidence_text = ""
    for i, e in enumerate(evidence, 1):
        evidence_text += f"\n{i}. [{e.get('type', 'unknown')}] {e.get('source', 'Unknown')}:\n{e.get('content', '')}\n"
    
    if not evidence_text:
        evidence_text = "No specific data found."
    
    try:
        prompt = ANSWER_PROMPT.format(
            question=question,
            evidence=evidence_text
        )
        
        response = await ollama_client.chat(
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT
        )
        
        state["final_answer"] = response.strip()
        
    except Exception as e:
        logger.error("Answer composition failed", error=str(e))
        state["final_answer"] = f"I encountered an error while processing your question: {str(e)}"
    
    return state


def should_continue(state: AgentState) -> str:
    """Determine which node to go to next."""
    if state.get("error") and "Access denied" in str(state.get("error", "")):
        return "compose"
    if state.get("approval_required"):
        return "compose"
    return "continue"


# =============================================================================
# Build LangGraph Workflow
# =============================================================================

def build_agent_graph() -> StateGraph:
    """Build the agent workflow graph."""
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("parse_intent", parse_intent)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("plan_query", plan_query)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("validate_results", validate_results)
    workflow.add_node("compose_answer", compose_answer)
    
    # Define edges
    workflow.set_entry_point("parse_intent")
    workflow.add_edge("parse_intent", "retrieve_context")
    workflow.add_edge("retrieve_context", "plan_query")
    workflow.add_edge("plan_query", "execute_tools")
    
    # Conditional edge after tool execution
    workflow.add_conditional_edges(
        "execute_tools",
        should_continue,
        {
            "continue": "validate_results",
            "compose": "compose_answer"
        }
    )
    
    workflow.add_edge("validate_results", "compose_answer")
    workflow.add_edge("compose_answer", END)
    
    return workflow.compile()


# Build the graph
agent_graph = None


# =============================================================================
# Database Functions
# =============================================================================

async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool."""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return db_pool


async def save_request_trace(request_id: str, question: str, answer: str, tool_calls: list):
    """Save request trace for replay."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO internal.audit_logs (
                    request_id, slack_user_id, user_role, tool_name,
                    tool_inputs, tool_outputs, policy_decision, policy_rule_ids
                ) VALUES ($1, 'system', 'system', 'agent_trace', $2, $3, 'ALLOW', ARRAY['trace'])
            """, uuid.UUID(request_id), json.dumps({"question": question}), 
                json.dumps({"answer": answer[:500], "tool_count": len(tool_calls)}))
    except Exception as e:
        logger.error("Failed to save trace", error=str(e))


# =============================================================================
# FastAPI Application
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global ollama_client, mcp_client, agent_graph
    
    # Startup
    logger.info("Starting Agent Service")
    ollama_client = OllamaClient(OLLAMA_BASE_URL, OLLAMA_MODEL)
    mcp_client = MCPClient(MCP_SERVER_URL)
    agent_graph = build_agent_graph()
    await get_db_pool()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Agent Service")
    if ollama_client:
        await ollama_client.close()
    if mcp_client:
        await mcp_client.close()
    if db_pool:
        await db_pool.close()


app = FastAPI(
    title="Agent Service",
    description="LangGraph-powered agent for governed data analysis",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "agent"}


@app.post("/ask", response_model=Answer)
async def ask_question(question: Question, background_tasks: BackgroundTasks):
    """Process a user question."""
    start_time = time.time()
    
    logger.info(
        "Processing question",
        request_id=question.request_id,
        question=question.text[:100],
        role=question.context.role
    )
    
    # Build initial state
    initial_state: AgentState = {
        "request_id": question.request_id,
        "question": question.text,
        "user_context": {
            "user_id": question.context.user_id,
            "slack_user_id": question.context.slack_user_id,
            "role": question.context.role,
            "region": question.context.region,
            "request_id": question.request_id
        },
        "question_type": "",
        "metrics": [],
        "documents": [],
        "planned_query": "",
        "query_analysis": {},
        "sql_result": {},
        "chart_spec": {},
        "policy_decision": "",
        "approval_required": False,
        "approval_reason": "",
        "evidence": [],
        "tool_calls": [],
        "final_answer": "",
        "confidence": 0.0,
        "error": ""
    }
    
    # Run the agent graph
    try:
        result = await agent_graph.ainvoke(initial_state)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        answer = Answer(
            request_id=question.request_id,
            question=question.text,
            answer_text=result.get("final_answer", "Unable to generate answer"),
            evidence=[Evidence(**e) for e in result.get("evidence", [])],
            tool_calls=[ToolCall(**tc) for tc in result.get("tool_calls", [])],
            requires_approval=result.get("approval_required", False),
            approval_reason=result.get("approval_reason"),
            confidence=result.get("confidence", 0.0),
            latency_ms=latency_ms
        )
        
        # Save trace in background
        background_tasks.add_task(
            save_request_trace,
            question.request_id,
            question.text,
            answer.answer_text,
            result.get("tool_calls", [])
        )
        
        logger.info(
            "Question processed",
            request_id=question.request_id,
            latency_ms=latency_ms,
            confidence=answer.confidence
        )
        
        return answer
        
    except Exception as e:
        logger.error("Agent execution failed", error=str(e), request_id=question.request_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/replay/{request_id}", response_model=ReplayTimeline)
async def get_replay(request_id: str):
    """Get the replay timeline for a request."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tool_name, tool_inputs, tool_outputs, policy_decision,
                       policy_rule_ids, latency_ms, created_at
                FROM internal.audit_logs
                WHERE request_id = $1
                ORDER BY created_at
            """, uuid.UUID(request_id))
            
            if not rows:
                raise HTTPException(status_code=404, detail="Request not found")
            
            steps = []
            question = ""
            final_answer = ""
            total_latency = 0
            
            for row in rows:
                inputs = json.loads(row["tool_inputs"]) if row["tool_inputs"] else {}
                outputs = json.loads(row["tool_outputs"]) if row["tool_outputs"] else {}
                
                if row["tool_name"] == "agent_trace":
                    question = inputs.get("question", "")
                    final_answer = outputs.get("answer", "")
                else:
                    steps.append({
                        "tool": row["tool_name"],
                        "decision": row["policy_decision"],
                        "rule_ids": row["policy_rule_ids"],
                        "latency_ms": row["latency_ms"],
                        "timestamp": row["created_at"].isoformat()
                    })
                
                total_latency += row["latency_ms"] or 0
            
            return ReplayTimeline(
                request_id=request_id,
                question=question,
                steps=steps,
                final_answer=final_answer,
                total_latency_ms=total_latency
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Replay retrieval failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approval/callback")
async def approval_callback(
    request_id: str,
    approved: bool,
    approver_id: str,
    reason: Optional[str] = None
):
    """Handle approval callback from Slack."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE internal.approval_requests
                SET status = $1,
                    approver_slack_id = $2,
                    approver_decision = $3,
                    approver_reason = $4,
                    decided_at = NOW()
                WHERE request_id = $5
            """, 
                "approved" if approved else "denied",
                approver_id,
                "approve" if approved else "deny",
                reason,
                uuid.UUID(request_id)
            )
        
        return {"status": "ok", "approved": approved}
        
    except Exception as e:
        logger.error("Approval callback failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
