# OPA Table Access Policy Tests

package analyst.test_tables

import data.analyst.tables
import rego.v1

# Test marketing can access reporting schema
test_marketing_reporting_allowed if {
    tables.allow with input as {
        "role": "marketing",
        "tool": "run_sql",
        "tables": [{"schema": "reporting", "table": "daily_kpis"}],
        "query_type": "SELECT",
        "has_limit": true
    }
}

# Test marketing cannot access raw schema
test_marketing_raw_denied if {
    not tables.allow with input as {
        "role": "marketing",
        "tool": "run_sql",
        "tables": [{"schema": "raw", "table": "customers"}],
        "query_type": "SELECT",
        "has_limit": true
    }
}

# Test data_analyst can access refined schema
test_analyst_refined_allowed if {
    tables.allow with input as {
        "role": "data_analyst",
        "tool": "run_sql",
        "tables": [{"schema": "refined", "table": "metrics"}],
        "query_type": "SELECT",
        "has_limit": true
    }
}

# Test admin can access raw schema
test_admin_raw_allowed if {
    tables.allow with input as {
        "role": "admin",
        "tool": "run_sql",
        "tables": [{"schema": "raw", "table": "customers"}],
        "query_type": "SELECT",
        "has_limit": true
    }
}

# Test DDL blocked for non-admin
test_ddl_blocked_for_marketing if {
    not tables.allow with input as {
        "role": "marketing",
        "tool": "run_sql",
        "tables": [],
        "query_type": "DDL",
        "has_limit": true
    }
}
