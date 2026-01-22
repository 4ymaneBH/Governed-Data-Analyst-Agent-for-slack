-- Governed Data Analyst Agent - Seed Data
-- Demo data for testing and development

-- ============================================================================
-- USERS
-- ============================================================================

INSERT INTO internal.users (slack_user_id, email, display_name, role, region) VALUES
('U001INTERN', 'intern@company.com', 'Alex Intern', 'intern', NULL),
('U002MARKETING', 'marketing@company.com', 'Jordan Marketing', 'marketing', NULL),
('U003SALES_NA', 'sales.na@company.com', 'Taylor Sales NA', 'sales', 'NA'),
('U004SALES_EMEA', 'sales.emea@company.com', 'Morgan Sales EMEA', 'sales', 'EMEA'),
('U005SALES_APAC', 'sales.apac@company.com', 'Casey Sales APAC', 'sales', 'APAC'),
('U006ANALYST', 'analyst@company.com', 'Riley Analyst', 'data_analyst', NULL),
('U007ADMIN', 'admin@company.com', 'Sam Admin', 'admin', NULL);

-- ============================================================================
-- DAILY KPIS (365 days of data)
-- ============================================================================

-- Generate KPI data for the last 365 days
INSERT INTO reporting.daily_kpis (date, region, channel, revenue, marketing_spend, new_customers, churned_customers, active_users, cac, churn_rate, mrr, arr)
SELECT 
    d::date as date,
    region,
    channel,
    -- Revenue: base + seasonal variation + growth trend + random
    ROUND((
        CASE region 
            WHEN 'NA' THEN 50000 
            WHEN 'EMEA' THEN 35000 
            WHEN 'APAC' THEN 25000 
            WHEN 'LATAM' THEN 15000 
        END
        * (1 + 0.002 * (d - '2025-01-01'::date))  -- 0.2% daily growth
        * (1 + 0.1 * SIN(2 * PI() * EXTRACT(DOY FROM d) / 365))  -- Seasonal
        * (0.9 + 0.2 * RANDOM())  -- Random variation
    )::NUMERIC, 2) as revenue,
    
    -- Marketing spend
    ROUND((
        CASE region 
            WHEN 'NA' THEN 8000 
            WHEN 'EMEA' THEN 6000 
            WHEN 'APAC' THEN 4000 
            WHEN 'LATAM' THEN 2500 
        END
        * (0.85 + 0.3 * RANDOM())
    )::NUMERIC, 2) as marketing_spend,
    
    -- New customers
    GREATEST(1, ROUND((
        CASE region 
            WHEN 'NA' THEN 12 
            WHEN 'EMEA' THEN 8 
            WHEN 'APAC' THEN 6 
            WHEN 'LATAM' THEN 4 
        END
        * (0.7 + 0.6 * RANDOM())
    ))::INTEGER) as new_customers,
    
    -- Churned customers
    GREATEST(0, ROUND((
        CASE region 
            WHEN 'NA' THEN 3 
            WHEN 'EMEA' THEN 2 
            WHEN 'APAC' THEN 2 
            WHEN 'LATAM' THEN 1 
        END
        * (0.5 + RANDOM())
    ))::INTEGER) as churned_customers,
    
    -- Active users
    ROUND((
        CASE region 
            WHEN 'NA' THEN 5000 
            WHEN 'EMEA' THEN 3500 
            WHEN 'APAC' THEN 2500 
            WHEN 'LATAM' THEN 1500 
        END
        * (1 + 0.001 * (d - '2025-01-01'::date))
        * (0.95 + 0.1 * RANDOM())
    ))::INTEGER as active_users,
    
    NULL as cac,  -- Will be calculated
    NULL as churn_rate,  -- Will be calculated
    NULL as mrr,
    NULL as arr
FROM 
    generate_series('2025-01-01'::date, '2025-12-31'::date, '1 day'::interval) d
    CROSS JOIN (VALUES ('NA'), ('EMEA'), ('APAC'), ('LATAM')) AS regions(region)
    CROSS JOIN (VALUES ('organic'), ('paid'), ('referral')) AS channels(channel);

-- Update calculated fields
UPDATE reporting.daily_kpis 
SET 
    cac = CASE WHEN new_customers > 0 THEN ROUND((marketing_spend / new_customers)::NUMERIC, 2) ELSE NULL END,
    churn_rate = CASE WHEN active_users > 0 THEN ROUND((churned_customers::DECIMAL / active_users)::NUMERIC, 4) ELSE NULL END,
    mrr = ROUND((revenue * 0.85)::NUMERIC, 2),
    arr = ROUND((revenue * 0.85 * 12)::NUMERIC, 2);

-- ============================================================================
-- CUSTOMERS (500 customers)
-- ============================================================================

INSERT INTO reporting.customers (customer_id, region, industry, plan, status, mrr, arr, signup_date, last_active_date, employee_count)
SELECT 
    uuid_generate_v4() as customer_id,
    (ARRAY['NA', 'EMEA', 'APAC', 'LATAM'])[1 + (RANDOM() * 3)::INTEGER] as region,
    (ARRAY['Technology', 'Healthcare', 'Finance', 'Retail', 'Manufacturing', 'Education', 'Media', 'Consulting'])[1 + (RANDOM() * 7)::INTEGER] as industry,
    (ARRAY['starter', 'professional', 'enterprise'])[1 + (RANDOM() * 2)::INTEGER] as plan,
    CASE 
        WHEN RANDOM() < 0.75 THEN 'active'
        WHEN RANDOM() < 0.9 THEN 'churned'
        WHEN RANDOM() < 0.95 THEN 'trial'
        ELSE 'suspended'
    END as status,
    ROUND((
        CASE (ARRAY['starter', 'professional', 'enterprise'])[1 + (RANDOM() * 2)::INTEGER]
            WHEN 'starter' THEN 99 + RANDOM() * 200
            WHEN 'professional' THEN 299 + RANDOM() * 500
            WHEN 'enterprise' THEN 999 + RANDOM() * 4000
        END
    )::NUMERIC, 2) as mrr,
    NULL as arr,
    ('2023-01-01'::date + (RANDOM() * 730)::INTEGER) as signup_date,
    ('2025-11-01'::date + (RANDOM() * 60)::INTEGER) as last_active_date,
    (10 + RANDOM() * 990)::INTEGER as employee_count
FROM generate_series(1, 500);

-- Update ARR
UPDATE reporting.customers SET arr = mrr * 12;

-- ============================================================================
-- RAW CUSTOMERS (PII data)
-- ============================================================================

INSERT INTO raw.customers (customer_id, email, phone, company_name, address_line1, city, state, postal_code, country, contact_name)
SELECT 
    c.customer_id,
    'contact' || ROW_NUMBER() OVER () || '@' || 
        LOWER(REPLACE((ARRAY['Acme', 'Globex', 'Initech', 'Umbrella', 'Stark', 'Wayne', 'Oscorp', 'Cyberdyne'])[1 + (RANDOM() * 7)::INTEGER], ' ', '')) || 
        (ARRAY['.com', '.io', '.co', '.net'])[1 + (RANDOM() * 3)::INTEGER] as email,
    '+1-555-' || LPAD((RANDOM() * 999)::INTEGER::TEXT, 3, '0') || '-' || LPAD((RANDOM() * 9999)::INTEGER::TEXT, 4, '0') as phone,
    (ARRAY['Acme Corp', 'Globex Inc', 'Initech LLC', 'Umbrella Corp', 'Stark Industries', 'Wayne Enterprises', 'Oscorp', 'Cyberdyne Systems'])[1 + (RANDOM() * 7)::INTEGER] || ' ' || ROW_NUMBER() OVER () as company_name,
    (RANDOM() * 999 + 1)::INTEGER::TEXT || ' ' || (ARRAY['Main', 'Oak', 'Elm', 'Park', 'Market', 'Tech', 'Innovation'])[1 + (RANDOM() * 6)::INTEGER] || ' ' || (ARRAY['St', 'Ave', 'Blvd', 'Dr', 'Way'])[1 + (RANDOM() * 4)::INTEGER] as address_line1,
    (ARRAY['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'London', 'Berlin', 'Tokyo', 'Sydney', 'Toronto'])[1 + (RANDOM() * 9)::INTEGER] as city,
    (ARRAY['NY', 'CA', 'IL', 'TX', 'AZ', 'UK', 'DE', 'JP', 'AU', 'ON'])[1 + (RANDOM() * 9)::INTEGER] as state,
    LPAD((RANDOM() * 99999)::INTEGER::TEXT, 5, '0') as postal_code,
    CASE c.region
        WHEN 'NA' THEN (ARRAY['USA', 'Canada'])[1 + (RANDOM())::INTEGER]
        WHEN 'EMEA' THEN (ARRAY['UK', 'Germany', 'France'])[1 + (RANDOM() * 2)::INTEGER]
        WHEN 'APAC' THEN (ARRAY['Japan', 'Australia', 'Singapore'])[1 + (RANDOM() * 2)::INTEGER]
        WHEN 'LATAM' THEN (ARRAY['Brazil', 'Mexico', 'Argentina'])[1 + (RANDOM() * 2)::INTEGER]
    END as country,
    (ARRAY['John', 'Jane', 'Bob', 'Alice', 'Charlie', 'Diana', 'Eve', 'Frank'])[1 + (RANDOM() * 7)::INTEGER] || ' ' ||
    (ARRAY['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis'])[1 + (RANDOM() * 7)::INTEGER] as contact_name
FROM reporting.customers c;

-- ============================================================================
-- RAW PAYMENTS
-- ============================================================================

INSERT INTO raw.payments (customer_id, amount, currency, payment_method, card_last_four, status, processed_at)
SELECT 
    c.customer_id,
    c.mrr as amount,
    'USD' as currency,
    (ARRAY['credit_card', 'bank_transfer', 'paypal'])[1 + (RANDOM() * 2)::INTEGER] as payment_method,
    LPAD((RANDOM() * 9999)::INTEGER::TEXT, 4, '0') as card_last_four,
    'completed' as status,
    (('2025-01-01'::date + (m * 30 || ' days')::interval)::date + (RANDOM() * 5)::INTEGER)::timestamptz as processed_at
FROM reporting.customers c
CROSS JOIN generate_series(0, 11) m
WHERE c.status = 'active' OR (c.status = 'churned' AND m < 6);

-- ============================================================================
-- METRICS REGISTRY
-- ============================================================================

INSERT INTO internal.metrics (name, display_name, description, owner, formula, sql_template, dimensions, tags) VALUES
('cac', 'Customer Acquisition Cost', 'Average cost to acquire a new customer, calculated as total marketing spend divided by new customers acquired', 'marketing', 'total_marketing_spend / new_customers', 
'SELECT date, region, SUM(marketing_spend) / NULLIF(SUM(new_customers), 0) as cac FROM reporting.daily_kpis WHERE {filters} GROUP BY date, region ORDER BY date', 
ARRAY['date', 'region', 'channel'], ARRAY['marketing', 'acquisition', 'cost']),

('churn_rate', 'Churn Rate', 'Percentage of customers who churned in a given period, calculated as churned customers divided by total active customers', 'customer_success', 'churned_customers / active_users',
'SELECT date, region, SUM(churned_customers)::DECIMAL / NULLIF(SUM(active_users), 0) as churn_rate FROM reporting.daily_kpis WHERE {filters} GROUP BY date, region ORDER BY date',
ARRAY['date', 'region'], ARRAY['retention', 'customer_success']),

('mrr', 'Monthly Recurring Revenue', 'Total monthly recurring revenue from all active subscriptions', 'finance', 'SUM(customer_mrr)',
'SELECT SUM(mrr) as total_mrr, region FROM reporting.customers WHERE status = ''active'' AND {filters} GROUP BY region',
ARRAY['region', 'plan', 'industry'], ARRAY['revenue', 'finance', 'subscription']),

('arr', 'Annual Recurring Revenue', 'Annualized recurring revenue, calculated as MRR * 12', 'finance', 'mrr * 12',
'SELECT SUM(arr) as total_arr, region FROM reporting.customers WHERE status = ''active'' AND {filters} GROUP BY region',
ARRAY['region', 'plan', 'industry'], ARRAY['revenue', 'finance', 'subscription']),

('arpu', 'Average Revenue Per User', 'Average monthly revenue generated per active customer', 'finance', 'total_mrr / active_customers',
'SELECT SUM(mrr) / COUNT(*) as arpu FROM reporting.customers WHERE status = ''active'' AND {filters}',
ARRAY['region', 'plan', 'industry'], ARRAY['revenue', 'finance']),

('ltv', 'Customer Lifetime Value', 'Predicted total revenue from a customer over their entire relationship', 'finance', 'arpu / churn_rate',
'SELECT AVG(mrr) / NULLIF(0.02, 0) as ltv FROM reporting.customers WHERE status = ''active''',
ARRAY['region', 'plan'], ARRAY['revenue', 'finance', 'customer_success']),

('nrr', 'Net Revenue Retention', 'Revenue retained from existing customers including expansions minus contractions and churn', 'customer_success', '(starting_mrr + expansion - contraction - churn) / starting_mrr',
NULL, ARRAY['month', 'region'], ARRAY['retention', 'revenue', 'growth']),

('dau', 'Daily Active Users', 'Number of unique users who engaged with the product in a day', 'product', 'COUNT(DISTINCT active_users)',
'SELECT date, region, SUM(active_users) as dau FROM reporting.daily_kpis WHERE {filters} GROUP BY date, region ORDER BY date',
ARRAY['date', 'region'], ARRAY['engagement', 'product']),

('conversion_rate', 'Trial to Paid Conversion Rate', 'Percentage of trial users who convert to paid subscriptions', 'sales', 'paid_conversions / trial_starts',
'SELECT COUNT(*) FILTER (WHERE status = ''active'')::DECIMAL / NULLIF(COUNT(*) FILTER (WHERE status IN (''active'', ''trial'', ''churned'')), 0) as conversion_rate FROM reporting.customers WHERE {filters}',
ARRAY['region', 'industry'], ARRAY['sales', 'conversion']),

('revenue_growth', 'Revenue Growth Rate', 'Month-over-month percentage change in revenue', 'finance', '(current_revenue - previous_revenue) / previous_revenue',
NULL, ARRAY['month', 'region'], ARRAY['revenue', 'growth', 'finance']),

('customer_count', 'Total Customers', 'Total number of customers by status', 'sales', 'COUNT(*)',
'SELECT status, COUNT(*) as customer_count FROM reporting.customers WHERE {filters} GROUP BY status',
ARRAY['region', 'industry', 'plan', 'status'], ARRAY['customers', 'sales']),

('avg_deal_size', 'Average Deal Size', 'Average MRR of new customers', 'sales', 'SUM(new_customer_mrr) / COUNT(new_customers)',
'SELECT AVG(mrr) as avg_deal_size FROM reporting.customers WHERE signup_date >= {start_date} AND {filters}',
ARRAY['region', 'industry', 'plan'], ARRAY['sales', 'revenue']),

('payback_period', 'CAC Payback Period', 'Months required to recover customer acquisition cost', 'finance', 'cac / arpu',
NULL, ARRAY['region', 'channel'], ARRAY['finance', 'marketing', 'efficiency']),

('expansion_mrr', 'Expansion MRR', 'Additional MRR from existing customer upgrades', 'customer_success', 'SUM(upgrade_mrr)',
NULL, ARRAY['month', 'region'], ARRAY['revenue', 'growth', 'customer_success']),

('contraction_mrr', 'Contraction MRR', 'Lost MRR from existing customer downgrades', 'customer_success', 'SUM(downgrade_mrr)',
NULL, ARRAY['month', 'region'], ARRAY['revenue', 'churn', 'customer_success']);

-- ============================================================================
-- DOCUMENTS FOR RAG
-- ============================================================================

INSERT INTO internal.documents (title, content, doc_type, acl_tags, metadata) VALUES
('Metric Definitions Guide', 
'# Metric Definitions Guide

## Revenue Metrics

### MRR (Monthly Recurring Revenue)
Monthly Recurring Revenue represents the predictable revenue generated each month from active subscriptions. It is calculated by summing all active customer subscription values on a monthly basis.

**Formula:** SUM(customer_mrr) for all active customers
**Owner:** Finance Team
**Update Frequency:** Daily

### ARR (Annual Recurring Revenue)
Annual Recurring Revenue is the annualized version of MRR, projecting yearly subscription revenue.

**Formula:** MRR × 12
**Owner:** Finance Team

### ARPU (Average Revenue Per User)
The average monthly revenue generated per active customer.

**Formula:** Total MRR / Active Customer Count

## Acquisition Metrics

### CAC (Customer Acquisition Cost)
The average cost to acquire a new customer, including all marketing and sales expenses.

**Formula:** Total Marketing & Sales Spend / New Customers Acquired
**Owner:** Marketing Team
**Typical Range:** $50-500 depending on market segment

### LTV (Customer Lifetime Value)
The predicted total revenue from a customer over their entire relationship.

**Formula:** ARPU / Monthly Churn Rate
**Note:** Higher LTV:CAC ratios (> 3:1) indicate healthy unit economics

## Retention Metrics

### Churn Rate
The percentage of customers who cancel their subscription in a given period.

**Formula:** Churned Customers / Total Active Customers at Period Start
**Owner:** Customer Success Team
**Target:** < 2% monthly for B2B SaaS

### NRR (Net Revenue Retention)
Measures revenue retained from existing customers, including expansions.

**Formula:** (Starting MRR + Expansion - Contraction - Churn) / Starting MRR
**Target:** > 100% indicates growth from existing customers
', 'knowledge_base', ARRAY['public'], '{"category": "metrics", "version": "1.0"}'),

('Data Dictionary', 
'# Data Dictionary

## Schemas

### reporting
Contains cleaned, aggregated data safe for business analysis. All users with SQL access can query this schema.

### raw
Contains source data including PII. Access restricted to admin and data_analyst roles with approval.

### internal
System tables including audit logs, user management, and document storage.

## Tables

### reporting.daily_kpis
Daily aggregated business metrics by region and channel.

| Column | Type | Description |
|--------|------|-------------|
| date | DATE | The calendar date |
| region | VARCHAR(50) | Geographic region (NA, EMEA, APAC, LATAM) |
| channel | VARCHAR(50) | Acquisition channel (organic, paid, referral) |
| revenue | DECIMAL | Daily revenue in USD |
| marketing_spend | DECIMAL | Daily marketing spend in USD |
| new_customers | INTEGER | New customers acquired |
| churned_customers | INTEGER | Customers who churned |
| active_users | INTEGER | Daily active users |
| cac | DECIMAL | Customer acquisition cost |
| churn_rate | DECIMAL | Daily churn rate |
| mrr | DECIMAL | Monthly recurring revenue |
| arr | DECIMAL | Annual recurring revenue |

### reporting.customers
Customer records without PII.

| Column | Type | Description |
|--------|------|-------------|
| customer_id | UUID | Unique customer identifier |
| region | VARCHAR(50) | Geographic region |
| industry | VARCHAR(100) | Customer industry vertical |
| plan | VARCHAR(50) | Subscription plan (starter, professional, enterprise) |
| status | VARCHAR(50) | Account status (active, churned, trial, suspended) |
| mrr | DECIMAL | Monthly recurring revenue |
| arr | DECIMAL | Annual recurring revenue |
| signup_date | DATE | Account creation date |
| last_active_date | DATE | Most recent activity date |
| employee_count | INTEGER | Customer company size |

### raw.customers (RESTRICTED)
Full customer records including PII. Requires admin approval to access.

Contains: email, phone, address, contact_name

### raw.payments (RESTRICTED)
Payment transaction history. Contains sensitive financial data.

Contains: payment amounts, payment methods, card details
', 'knowledge_base', ARRAY['public'], '{"category": "data_dictionary", "version": "1.0"}'),

('Business Glossary',
'# Business Glossary

## Regions
- **NA**: North America (USA, Canada)
- **EMEA**: Europe, Middle East, and Africa
- **APAC**: Asia-Pacific (Japan, Australia, Southeast Asia)
- **LATAM**: Latin America (Brazil, Mexico, Argentina)

## Customer Status
- **Active**: Currently paying subscriber
- **Churned**: Cancelled subscription
- **Trial**: In free trial period
- **Suspended**: Temporarily disabled (payment issues)

## Subscription Plans
- **Starter**: Entry-level plan, $99-299/month
- **Professional**: Mid-tier plan, $299-799/month
- **Enterprise**: High-tier plan, $999+/month, custom pricing

## Time Periods
- **MTD**: Month to Date
- **QTD**: Quarter to Date
- **YTD**: Year to Date
- **MoM**: Month over Month comparison
- **QoQ**: Quarter over Quarter comparison
- **YoY**: Year over Year comparison

## Key Business Events
- **Fiscal Year**: January 1 - December 31
- **Quarter Boundaries**: Q1 (Jan-Mar), Q2 (Apr-Jun), Q3 (Jul-Sep), Q4 (Oct-Dec)
', 'knowledge_base', ARRAY['public'], '{"category": "glossary", "version": "1.0"}'),

('Data Access Policy',
'# Data Access Policy

## Role-Based Access Control

### Intern Role
- Can access: search_docs, explain_metric tools only
- Cannot execute SQL queries
- Cannot access any raw data

### Marketing Role
- Can access: reporting schema only
- Cannot access: raw.* tables
- Cannot access: PII columns (email, phone, address)
- Can run: SELECT queries with LIMIT

### Sales Role
- Can access: reporting schema only
- Row-level security: Only sees data for their assigned region
- Cannot access: raw.* tables or PII

### Data Analyst Role
- Can access: reporting.*, refined.* schemas
- Cannot access: raw.* without approval
- Can run: Complex analytical queries

### Admin Role
- Full access to all schemas
- PII access requires approval workflow
- Can approve/deny access requests

## Approval Requirements

The following actions require admin approval:
1. Any access to raw.* schema
2. Queries returning PII columns
3. Data exports exceeding 1000 rows
4. Queries on sensitive tables

## Audit Requirements

All tool calls are logged with:
- User identity and role
- Tool name and inputs
- Policy decision and rule IDs
- Redacted outputs
- Timestamp and latency
', 'policy', ARRAY['public'], '{"category": "policy", "version": "1.0"}'),

('Finance Team Data Guide',
'# Finance Team Data Guide

## Available Metrics

### Revenue Tracking
Query monthly revenue trends:
```
"What was our total revenue last quarter by region?"
"Show MRR growth month over month"
"Compare ARR this year vs last year"
```

### Unit Economics
```
"What is our current CAC by channel?"
"Calculate LTV:CAC ratio"
"What is the payback period for enterprise customers?"
```

## Best Practices

1. Always specify the time period for trend analysis
2. Use region filters for geographic breakdown
3. For YoY comparisons, specify both years explicitly
4. Revenue metrics are in USD

## Data Freshness
- Revenue data: Updated daily at 2 AM UTC
- Customer metrics: Real-time
- Aggregated views: Refreshed hourly
', 'knowledge_base', ARRAY['finance_only', 'public'], '{"category": "guide", "team": "finance", "version": "1.0"}');

-- Note: In production, you would also generate embeddings for the document chunks
-- For this seed, we create the chunks without embeddings (they will be generated by the app)

INSERT INTO internal.doc_chunks (doc_id, chunk_index, content, token_count)
SELECT 
    doc_id,
    chunk_index,
    chunk_content,
    LENGTH(chunk_content) / 4 as token_count  -- Rough token estimate
FROM (
    SELECT 
        doc_id,
        ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY ordinality) - 1 as chunk_index,
        chunk as chunk_content
    FROM internal.documents,
    LATERAL unnest(string_to_array(content, E'\n\n')) WITH ORDINALITY AS chunks(chunk, ordinality)
    WHERE LENGTH(chunk) > 50  -- Skip very short chunks
) chunked;

-- ============================================================================
-- Summary
-- ============================================================================

-- Print summary
DO $$
DECLARE
    user_count INTEGER;
    kpi_count INTEGER;
    customer_count INTEGER;
    payment_count INTEGER;
    metric_count INTEGER;
    doc_count INTEGER;
    chunk_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO user_count FROM internal.users;
    SELECT COUNT(*) INTO kpi_count FROM reporting.daily_kpis;
    SELECT COUNT(*) INTO customer_count FROM reporting.customers;
    SELECT COUNT(*) INTO payment_count FROM raw.payments;
    SELECT COUNT(*) INTO metric_count FROM internal.metrics;
    SELECT COUNT(*) INTO doc_count FROM internal.documents;
    SELECT COUNT(*) INTO chunk_count FROM internal.doc_chunks;
    
    RAISE NOTICE '=== Seed Data Summary ===';
    RAISE NOTICE 'Users: %', user_count;
    RAISE NOTICE 'Daily KPIs: %', kpi_count;
    RAISE NOTICE 'Customers: %', customer_count;
    RAISE NOTICE 'Payments: %', payment_count;
    RAISE NOTICE 'Metrics: %', metric_count;
    RAISE NOTICE 'Documents: %', doc_count;
    RAISE NOTICE 'Document Chunks: %', chunk_count;
END $$;
