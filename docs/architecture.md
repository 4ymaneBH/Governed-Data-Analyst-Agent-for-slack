# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SLACK WORKSPACE                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │ Business    │  │  Analyst    │  │   Admin     │                         │
│  │ User        │  │  User       │  │             │                         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
│         │                │                │                                 │
│         └────────────────┼────────────────┘                                 │
│                          │ /askdata                                         │
└──────────────────────────┼──────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────────┐
│                         SLACK APP SERVICE (Port 3000)                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Slack Bolt (Socket Mode)                                          │   │
│  │  • /askdata command handler                                          │   │
│  │  • Block Kit response templates                                      │   │
│  │  • Interactive button handlers                                       │   │
│  │  • Approval workflow UI                                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────────────────┐
│                         AGENT SERVICE (Port 8002)                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI + LangGraph Workflow                                        │   │
│  │                                                                      │   │
│  │  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌────────┐│   │
│  │  │ Parse   │──▶│Retrieve │──▶│ Plan    │──▶│Execute  │──▶│Compose ││   │
│  │  │ Intent  │   │ Context │   │ Query   │   │ Tools   │   │ Answer ││   │
│  │  └─────────┘   └─────────┘   └─────────┘   └────┬────┘   └────────┘│   │
│  │                                                  │                   │   │
│  │                                          ┌──────▼──────┐            │   │
│  │                                          │  Validate   │            │   │
│  │                                          │  Results    │            │   │
│  │                                          └─────────────┘            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Endpoints:                                                                  │
│  • POST /ask - Process user questions                                       │
│  • GET /replay/{id} - Get execution timeline                                │
│  • POST /approval/callback - Handle approval decisions                      │
└─────────────────────────┬────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
┌─────────▼─────┐ ┌───────▼──────┐ ┌──────▼──────┐
│   OLLAMA      │ │  MCP SERVER  │ │  ADMIN UI   │
│  (Port 11434) │ │  (Port 8001) │ │ (Port 8080) │
│               │ │              │ │             │
│ Local LLM:    │ │ Tools:       │ │ Pages:      │
│ • llama3.2    │ │ • run_sql    │ │ • Dashboard │
│ • mistral     │ │ • search_docs│ │ • Audit Log │
│               │ │ • explain_   │ │ • Replay    │
│               │ │   metric     │ │ • Policies  │
│               │ │ • generate_  │ │ • Approvals │
│               │ │   chart      │ │             │
└───────────────┘ └───────┬──────┘ └──────┬──────┘
                          │               │
                          │               │
┌─────────────────────────▼───────────────▼───────────────────────────────────┐
│                         OPA POLICY ENGINE (Port 8181)                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Rego Policies:                                                      │   │
│  │  • main.rego - Decision aggregator                                   │   │
│  │  • rbac.rego - Role → Tool permissions                               │   │
│  │  • tables.rego - Schema access control                               │   │
│  │  • columns.rego - PII masking/blocking                               │   │
│  │  • rows.rego - Region-based RLS                                      │   │
│  │  • approval.rego - Approval triggers                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────────────┐
│                         POSTGRESQL + PGVECTOR (Port 5432)                    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                 │
│  │   reporting    │  │      raw       │  │    internal    │                 │
│  │                │  │                │  │                │                 │
│  │ • daily_kpis   │  │ • customers    │  │ • audit_logs   │                 │
│  │ • customers    │  │   (with PII)   │  │ • approvals    │                 │
│  │ • monthly_kpis │  │ • payments     │  │ • documents    │                 │
│  │   (view)       │  │                │  │ • doc_chunks   │                 │
│  │ • customer_    │  │                │  │ • metrics      │                 │
│  │   summary      │  │                │  │ • users        │                 │
│  └────────────────┘  └────────────────┘  └────────────────┘                 │
│                                                                              │
│  Features:                                                                   │
│  • pgvector for document embeddings                                         │
│  • Row-Level Security (RLS) policies                                        │
│  • Audit logging functions                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Question Processing

```
User Question → Slack App → Agent Service → LangGraph Workflow
                                              ↓
                                        Parse Intent
                                              ↓
                                     Retrieve Context
                                    (docs + metrics)
                                              ↓
                                       Plan Query
                                              ↓
                                     Execute Tools ←→ OPA Policy Check
                                              ↓
                                    ┌─────────────────┐
                                    │                 │
                              ALLOW │    Policy    │ DENY
                                    │   Decision   │
                                    │                 │
                                    └────────┬────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ↓              ↓              ↓
                         Continue      Require          Refuse
                                      Approval
```

### 2. Policy Evaluation

```
Tool Call → MCP Server → Build Policy Input
                              ↓
                         OPA Query
                              ↓
                    Evaluate Policies (in order):
                    1. RBAC (role → tool)
                    2. Tables (schema access)
                    3. Columns (PII check)
                    4. Rows (region RLS)
                    5. Approval (sensitive actions)
                              ↓
                         Decision
                    ┌───────┴───────┐
                    ↓       ↓       ↓
                 ALLOW    DENY  REQUIRE_APPROVAL
```

### 3. Audit Flow

```
Tool Call → Execute → Log Audit Entry
                          ↓
                    ┌─────────────────────────┐
                    │ Audit Log Entry         │
                    │                         │
                    │ • request_id            │
                    │ • user_id, role         │
                    │ • tool_name             │
                    │ • inputs (redacted)     │
                    │ • outputs (redacted)    │
                    │ • policy_decision       │
                    │ • policy_rule_ids       │
                    │ • latency_ms            │
                    │ • timestamp             │
                    └─────────────────────────┘
```

## Security Model

### Defense in Depth

1. **Slack Authentication** - User identity from Slack
2. **Role Mapping** - User → Role assignment
3. **OPA Policy** - Tool-level authorization
4. **Database RLS** - Row-level filtering
5. **Audit Logging** - Full traceability

### Trust Boundaries

```
┌─────────────────────────────────────────┐
│          UNTRUSTED (User Input)         │
│  • Slack messages                       │
│  • Question text                        │
│  • Interactive selections               │
└────────────────────┬────────────────────┘
                     │
                     ▼ VALIDATION
┌─────────────────────────────────────────┐
│          SEMI-TRUSTED (Services)        │
│  • Agent service (validates input)      │
│  • LLM outputs (not executed directly)  │
└────────────────────┬────────────────────┘
                     │
                     ▼ POLICY CHECK
┌─────────────────────────────────────────┐
│          TRUSTED (Governed)             │
│  • MCP tools (policy enforced)          │
│  • Database (RLS enforced)              │
│  • Audit logs (immutable)               │
└─────────────────────────────────────────┘
```

## Scalability

### Current Design (Single Node)

- All services in Docker Compose
- Single PostgreSQL instance
- Ollama for local LLM

### Production Scaling

| Component | Scale Strategy |
|-----------|----------------|
| Agent Service | Horizontal (stateless) |
| MCP Server | Horizontal (stateless) |
| OPA | Horizontal (stateless) |
| PostgreSQL | Read replicas, connection pooling |
| Ollama | GPU cluster, model serving |
