# Metric Definitions Guide

This document provides comprehensive definitions for all business metrics tracked by the Data Analyst Agent.

## Revenue Metrics

### MRR (Monthly Recurring Revenue)
Monthly Recurring Revenue represents the predictable revenue generated each month from active subscriptions. It is the foundation of SaaS financial planning.

**Formula:** `SUM(customer_mrr)` for all active customers

**Owner:** Finance Team

**Update Frequency:** Real-time

**Example Query:**
```sql
SELECT region, SUM(mrr) as total_mrr
FROM reporting.customers
WHERE status = 'active'
GROUP BY region
```

---

### ARR (Annual Recurring Revenue)
Annual Recurring Revenue is the annualized version of MRR, projecting yearly subscription revenue.

**Formula:** `MRR × 12`

**Owner:** Finance Team

**Typical Use:** Board reporting, investor updates, annual planning

---

### ARPU (Average Revenue Per User)
The average monthly revenue generated per active customer.

**Formula:** `Total MRR / Active Customer Count`

**Owner:** Finance Team

**Benchmarks:**
- Starter plans: $99-299
- Professional plans: $299-799  
- Enterprise plans: $999+

---

### Revenue Growth Rate
Month-over-month percentage change in revenue.

**Formula:** `(Current Revenue - Previous Revenue) / Previous Revenue`

**Owner:** Finance Team

**Target:** 10-20% MoM for growth-stage SaaS

---

## Acquisition Metrics

### CAC (Customer Acquisition Cost)
The average cost to acquire a new customer, including all marketing and sales expenses.

**Formula:** `Total Marketing & Sales Spend / New Customers Acquired`

**Owner:** Marketing Team

**Typical Range:** $50-500 depending on market segment

**Best Practices:**
- Track by channel (organic, paid, referral)
- Segment by customer size/plan
- Monitor trends over time

---

### New Customers
Number of new customers acquired in a given period.

**Owner:** Sales Team

**Dimensions:** Date, Region, Channel

---

## Retention Metrics

### Churn Rate
The percentage of customers who cancel their subscription in a given period.

**Formula:** `Churned Customers / Total Active Customers at Period Start`

**Owner:** Customer Success Team

**Targets:**
- B2B SaaS: < 2% monthly
- Enterprise: < 1% monthly
- SMB: < 5% monthly

---

### NRR (Net Revenue Retention)
Measures revenue retained from existing customers, including expansions.

**Formula:** `(Starting MRR + Expansion - Contraction - Churn) / Starting MRR`

**Owner:** Customer Success Team

**Interpretation:**
- > 100%: Growing from existing customers
- 100%: Flat (expansions = churn)
- < 100%: Shrinking customer base

**Best-in-class:** 120%+

---

### LTV (Customer Lifetime Value)
The predicted total revenue from a customer over their entire relationship.

**Formula:** `ARPU / Monthly Churn Rate`

**Owner:** Finance Team

**Note:** Higher LTV:CAC ratios (> 3:1) indicate healthy unit economics

---

## Engagement Metrics

### DAU (Daily Active Users)
Number of unique users who engaged with the product in a day.

**Formula:** `COUNT(DISTINCT daily_active_users)`

**Owner:** Product Team

**Related Metrics:**
- WAU (Weekly Active Users)
- MAU (Monthly Active Users)
- DAU/MAU Ratio (stickiness)

---

## Sales Metrics

### Conversion Rate
Percentage of trial users who convert to paid subscriptions.

**Formula:** `Paid Conversions / Trial Starts`

**Owner:** Sales Team

**Typical Range:** 2-5% for self-serve, 10-25% for sales-assisted

---

### Average Deal Size
Average MRR of new customers.

**Formula:** `SUM(New Customer MRR) / COUNT(New Customers)`

**Owner:** Sales Team

**Segments:**
- SMB: $100-500/month
- Mid-market: $500-2000/month
- Enterprise: $2000+/month

---

## Efficiency Metrics

### CAC Payback Period
Months required to recover customer acquisition cost.

**Formula:** `CAC / ARPU`

**Owner:** Finance Team

**Target:** < 12 months for healthy SaaS

---

### LTV:CAC Ratio
Ratio of customer lifetime value to acquisition cost.

**Formula:** `LTV / CAC`

**Owner:** Finance Team

**Benchmarks:**
- < 1: Unsustainable (losing money per customer)
- 1-3: Needs improvement
- 3-5: Healthy
- > 5: Potentially under-investing in growth

---

## Data Freshness

| Metric Category | Update Frequency |
|-----------------|------------------|
| Revenue metrics | Real-time |
| KPI aggregates | Daily at 2 AM UTC |
| Customer counts | Real-time |
| Engagement metrics | Hourly |
