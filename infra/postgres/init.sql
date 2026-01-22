-- Governed Data Analyst Agent - Database Initialization
-- This script sets up the database schema, extensions, and RLS policies

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS internal;

-- ============================================================================
-- INTERNAL SCHEMA: Users, Roles, Audit
-- ============================================================================

-- Users table
CREATE TABLE internal.users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slack_user_id VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255),
    display_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'intern',
    region VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_role CHECK (role IN ('intern', 'marketing', 'sales', 'data_analyst', 'admin'))
);

-- Audit log table
CREATE TABLE internal.audit_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    slack_user_id VARCHAR(50) NOT NULL,
    user_role VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    tool_inputs JSONB,
    tool_inputs_redacted JSONB,
    tool_outputs JSONB,
    tool_outputs_redacted JSONB,
    policy_decision VARCHAR(50) NOT NULL,
    policy_rule_ids TEXT[],
    policy_constraints JSONB,
    latency_ms INTEGER,
    row_count INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_decision CHECK (policy_decision IN ('ALLOW', 'DENY', 'REQUIRE_APPROVAL'))
);

-- Create index for audit log queries
CREATE INDEX idx_audit_logs_request_id ON internal.audit_logs(request_id);
CREATE INDEX idx_audit_logs_slack_user ON internal.audit_logs(slack_user_id);
CREATE INDEX idx_audit_logs_created_at ON internal.audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_tool_name ON internal.audit_logs(tool_name);
CREATE INDEX idx_audit_logs_decision ON internal.audit_logs(policy_decision);

-- Approval requests table
CREATE TABLE internal.approval_requests (
    approval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    slack_user_id VARCHAR(50) NOT NULL,
    user_role VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    tool_inputs JSONB NOT NULL,
    reason TEXT NOT NULL,
    policy_rule_ids TEXT[],
    status VARCHAR(50) DEFAULT 'pending',
    approver_slack_id VARCHAR(50),
    approver_decision VARCHAR(50),
    approver_reason TEXT,
    approval_token TEXT,
    token_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    CONSTRAINT valid_approver_decision CHECK (approver_decision IS NULL OR approver_decision IN ('approve', 'deny'))
);

CREATE INDEX idx_approval_requests_status ON internal.approval_requests(status);
CREATE INDEX idx_approval_requests_request_id ON internal.approval_requests(request_id);

-- ============================================================================
-- REPORTING SCHEMA: Safe analytics tables
-- ============================================================================

-- Daily KPIs table
CREATE TABLE reporting.daily_kpis (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    channel VARCHAR(50),
    revenue DECIMAL(15, 2),
    marketing_spend DECIMAL(15, 2),
    new_customers INTEGER,
    churned_customers INTEGER,
    active_users INTEGER,
    cac DECIMAL(10, 2),
    churn_rate DECIMAL(5, 4),
    mrr DECIMAL(15, 2),
    arr DECIMAL(15, 2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_daily_kpis_date ON reporting.daily_kpis(date);
CREATE INDEX idx_daily_kpis_region ON reporting.daily_kpis(region);
CREATE INDEX idx_daily_kpis_date_region ON reporting.daily_kpis(date, region);

-- Customers table (non-PII version)
CREATE TABLE reporting.customers (
    customer_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region VARCHAR(50) NOT NULL,
    industry VARCHAR(100),
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    mrr DECIMAL(10, 2),
    arr DECIMAL(12, 2),
    signup_date DATE,
    last_active_date DATE,
    employee_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('active', 'churned', 'trial', 'suspended'))
);

CREATE INDEX idx_customers_region ON reporting.customers(region);
CREATE INDEX idx_customers_status ON reporting.customers(status);
CREATE INDEX idx_customers_industry ON reporting.customers(industry);

-- ============================================================================
-- RAW SCHEMA: Sensitive/PII data (restricted access)
-- ============================================================================

-- Raw customers with PII
CREATE TABLE raw.customers (
    customer_id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    company_name VARCHAR(255),
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    contact_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (customer_id) REFERENCES reporting.customers(customer_id)
);

-- Raw payments
CREATE TABLE raw.payments (
    payment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payment_method VARCHAR(50),
    card_last_four VARCHAR(4),
    status VARCHAR(50) NOT NULL,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (customer_id) REFERENCES reporting.customers(customer_id),
    CONSTRAINT valid_payment_status CHECK (status IN ('pending', 'completed', 'failed', 'refunded'))
);

CREATE INDEX idx_payments_customer ON raw.payments(customer_id);
CREATE INDEX idx_payments_status ON raw.payments(status);

-- ============================================================================
-- INTERNAL SCHEMA: Document store for RAG
-- ============================================================================

-- Documents table
CREATE TABLE internal.documents (
    doc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    doc_type VARCHAR(100) NOT NULL,
    acl_tags TEXT[] DEFAULT ARRAY['public'],
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document chunks with embeddings
CREATE TABLE internal.doc_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id UUID NOT NULL REFERENCES internal.documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI ada-002 dimension, adjust for Ollama
    token_count INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_doc_chunks_doc_id ON internal.doc_chunks(doc_id);
CREATE INDEX idx_doc_chunks_embedding ON internal.doc_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Metrics registry
CREATE TABLE internal.metrics (
    metric_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    owner VARCHAR(100),
    formula TEXT,
    sql_template TEXT,
    dimensions TEXT[],
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable RLS on customers table
ALTER TABLE reporting.customers ENABLE ROW LEVEL SECURITY;

-- Policy: Sales users can only see their region
-- This is enforced via application-level RLS using session variables
CREATE POLICY sales_region_policy ON reporting.customers
    FOR SELECT
    USING (
        current_setting('app.user_role', true) != 'sales'
        OR region = current_setting('app.user_region', true)
    );

-- Enable RLS on daily_kpis
ALTER TABLE reporting.daily_kpis ENABLE ROW LEVEL SECURITY;

CREATE POLICY sales_region_kpis_policy ON reporting.daily_kpis
    FOR SELECT
    USING (
        current_setting('app.user_role', true) != 'sales'
        OR region = current_setting('app.user_region', true)
    );

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Monthly KPIs aggregation
CREATE VIEW reporting.monthly_kpis AS
SELECT 
    DATE_TRUNC('month', date)::DATE as month,
    region,
    SUM(revenue) as total_revenue,
    SUM(marketing_spend) as total_marketing_spend,
    SUM(new_customers) as total_new_customers,
    SUM(churned_customers) as total_churned,
    AVG(active_users)::INTEGER as avg_active_users,
    CASE 
        WHEN SUM(new_customers) > 0 
        THEN SUM(marketing_spend) / SUM(new_customers) 
        ELSE NULL 
    END as cac,
    CASE 
        WHEN SUM(active_users) > 0 
        THEN SUM(churned_customers)::DECIMAL / SUM(active_users) 
        ELSE NULL 
    END as churn_rate
FROM reporting.daily_kpis
GROUP BY DATE_TRUNC('month', date), region;

-- Customer summary by region
CREATE VIEW reporting.customer_summary AS
SELECT 
    region,
    industry,
    COUNT(*) as customer_count,
    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_count,
    SUM(CASE WHEN status = 'churned' THEN 1 ELSE 0 END) as churned_count,
    SUM(mrr) as total_mrr,
    SUM(arr) as total_arr,
    AVG(mrr) as avg_mrr
FROM reporting.customers
GROUP BY region, industry;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to set user context for RLS
CREATE OR REPLACE FUNCTION internal.set_user_context(p_role TEXT, p_region TEXT DEFAULT NULL)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.user_role', p_role, false);
    IF p_region IS NOT NULL THEN
        PERFORM set_config('app.user_region', p_region, false);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to log audit entry
CREATE OR REPLACE FUNCTION internal.log_audit(
    p_request_id UUID,
    p_slack_user_id VARCHAR(50),
    p_user_role VARCHAR(50),
    p_tool_name VARCHAR(100),
    p_tool_inputs JSONB,
    p_tool_outputs JSONB,
    p_policy_decision VARCHAR(50),
    p_policy_rule_ids TEXT[],
    p_latency_ms INTEGER DEFAULT NULL,
    p_row_count INTEGER DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_log_id UUID;
BEGIN
    INSERT INTO internal.audit_logs (
        request_id, slack_user_id, user_role, tool_name,
        tool_inputs, tool_outputs,
        policy_decision, policy_rule_ids,
        latency_ms, row_count, error_message
    ) VALUES (
        p_request_id, p_slack_user_id, p_user_role, p_tool_name,
        p_tool_inputs, p_tool_outputs,
        p_policy_decision, p_policy_rule_ids,
        p_latency_ms, p_row_count, p_error_message
    ) RETURNING log_id INTO v_log_id;
    
    RETURN v_log_id;
END;
$$ LANGUAGE plpgsql;

GRANT USAGE ON SCHEMA reporting TO PUBLIC;
GRANT USAGE ON SCHEMA internal TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO PUBLIC;
GRANT SELECT, INSERT ON internal.audit_logs TO PUBLIC;
GRANT SELECT, INSERT, UPDATE ON internal.approval_requests TO PUBLIC;
GRANT SELECT ON internal.documents TO PUBLIC;
GRANT SELECT ON internal.doc_chunks TO PUBLIC;
GRANT SELECT ON internal.metrics TO PUBLIC;
GRANT SELECT ON internal.users TO PUBLIC;
