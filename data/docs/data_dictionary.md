# Data Dictionary

This document describes the database schema, tables, and columns available for analytics.

## Schemas

### `reporting`
Contains cleaned, aggregated data safe for business analysis. All users with SQL access can query this schema.

**Access:** marketing, sales, data_analyst, admin

### `raw`
Contains source data including PII (Personally Identifiable Information). Access is restricted and requires approval.

**Access:** admin (requires approval)

### `internal`
System tables including audit logs, user management, document storage, and metrics registry.

**Access:** admin only

---

## Tables

### reporting.daily_kpis

Daily aggregated business metrics by region and channel.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| id | SERIAL | Primary key | 1 |
| date | DATE | The calendar date | 2025-01-15 |
| region | VARCHAR(50) | Geographic region | NA, EMEA, APAC, LATAM |
| channel | VARCHAR(50) | Acquisition channel | organic, paid, referral |
| revenue | DECIMAL(15,2) | Daily revenue in USD | 50000.00 |
| marketing_spend | DECIMAL(15,2) | Daily marketing spend | 8000.00 |
| new_customers | INTEGER | New customers acquired | 12 |
| churned_customers | INTEGER | Customers who churned | 3 |
| active_users | INTEGER | Daily active users | 5000 |
| cac | DECIMAL(10,2) | Customer acquisition cost | 666.67 |
| churn_rate | DECIMAL(5,4) | Daily churn rate | 0.0006 |
| mrr | DECIMAL(15,2) | Monthly recurring revenue | 42500.00 |
| arr | DECIMAL(15,2) | Annual recurring revenue | 510000.00 |

**Indexes:** date, region, (date, region)

---

### reporting.customers

Customer records without PII. Contains subscription and engagement data.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| customer_id | UUID | Unique identifier | 550e8400-e29b-41d4-a716-446655440000 |
| region | VARCHAR(50) | Geographic region | NA |
| industry | VARCHAR(100) | Customer industry | Technology |
| plan | VARCHAR(50) | Subscription plan | starter, professional, enterprise |
| status | VARCHAR(50) | Account status | active, churned, trial, suspended |
| mrr | DECIMAL(10,2) | Monthly recurring revenue | 299.00 |
| arr | DECIMAL(12,2) | Annual recurring revenue | 3588.00 |
| signup_date | DATE | Account creation date | 2024-03-15 |
| last_active_date | DATE | Most recent activity | 2025-01-14 |
| employee_count | INTEGER | Customer company size | 150 |

**Indexes:** region, status, industry

---

### reporting.monthly_kpis (VIEW)

Aggregated monthly metrics by region.

| Column | Type | Description |
|--------|------|-------------|
| month | DATE | First day of month |
| region | VARCHAR(50) | Geographic region |
| total_revenue | DECIMAL | Sum of monthly revenue |
| total_marketing_spend | DECIMAL | Sum of marketing spend |
| total_new_customers | INTEGER | New customers in month |
| total_churned | INTEGER | Churned customers |
| avg_active_users | INTEGER | Average DAU |
| cac | DECIMAL | Calculated CAC |
| churn_rate | DECIMAL | Monthly churn rate |

---

### reporting.customer_summary (VIEW)

Customer statistics grouped by region and industry.

| Column | Type | Description |
|--------|------|-------------|
| region | VARCHAR(50) | Geographic region |
| industry | VARCHAR(100) | Industry vertical |
| customer_count | INTEGER | Total customers |
| active_count | INTEGER | Active customers |
| churned_count | INTEGER | Churned customers |
| total_mrr | DECIMAL | Sum of MRR |
| total_arr | DECIMAL | Sum of ARR |
| avg_mrr | DECIMAL | Average MRR |

---

### raw.customers (RESTRICTED)

Full customer records including PII. **Requires admin approval to access.**

| Column | Type | Description | PII |
|--------|------|-------------|-----|
| customer_id | UUID | Primary key | No |
| email | VARCHAR(255) | Customer email | ⚠️ Yes |
| phone | VARCHAR(50) | Phone number | ⚠️ Yes |
| company_name | VARCHAR(255) | Company name | No |
| address_line1 | VARCHAR(255) | Street address | ⚠️ Yes |
| city | VARCHAR(100) | City | No |
| state | VARCHAR(100) | State/Province | No |
| postal_code | VARCHAR(20) | Postal code | No |
| country | VARCHAR(100) | Country | No |
| contact_name | VARCHAR(255) | Contact name | ⚠️ Yes |

---

### raw.payments (RESTRICTED)

Payment transaction history. **Contains sensitive financial data.**

| Column | Type | Description | Sensitive |
|--------|------|-------------|-----------|
| payment_id | UUID | Primary key | No |
| customer_id | UUID | Foreign key | No |
| amount | DECIMAL(10,2) | Payment amount | No |
| currency | VARCHAR(3) | Currency code | No |
| payment_method | VARCHAR(50) | Method used | ⚠️ Yes |
| card_last_four | VARCHAR(4) | Last 4 digits | ⚠️ Yes |
| status | VARCHAR(50) | Payment status | No |
| processed_at | TIMESTAMPTZ | Process time | No |

---

## Column Tags

### PII Columns (Blocked for most roles)
- email
- phone
- address_line1, address_line2
- contact_name
- card_last_four

### Sensitive Columns
- payment_method
- amount (in raw schema)

### Safe Columns
All columns in `reporting` schema are safe for business users.

---

## Common Queries

### Revenue by Region
```sql
SELECT region, SUM(revenue) as total_revenue
FROM reporting.daily_kpis
WHERE date >= '2025-01-01'
GROUP BY region
ORDER BY total_revenue DESC
```

### Customer Count by Status
```sql
SELECT status, COUNT(*) as count
FROM reporting.customers
GROUP BY status
```

### Top Industries by ARR
```sql
SELECT industry, SUM(arr) as total_arr
FROM reporting.customers
WHERE status = 'active'
GROUP BY industry
ORDER BY total_arr DESC
LIMIT 10
```
