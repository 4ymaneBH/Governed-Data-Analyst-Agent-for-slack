package analyst.test_main

import data.analyst.main
import rego.v1

test_marketing_reporting_query_allowed if {
    main.decision with input as {
        "role": "marketing",
        "tool": "run_sql",
        "tables": [{"schema": "reporting", "table": "daily_kpis"}],
        "columns": [],
        "query_type": "SELECT",
        "has_limit": true,
        "row_count": null,
        "region": null,
    } == "ALLOW"
}

test_intern_sql_denied if {
    main.decision with input as {
        "role": "intern",
        "tool": "run_sql",
        "tables": [{"schema": "reporting", "table": "daily_kpis"}],
        "columns": [],
        "query_type": "SELECT",
        "has_limit": true,
        "row_count": null,
        "region": null,
    } == "DENY"
}

test_marketing_raw_schema_denied if {
    main.decision with input as {
        "role": "marketing",
        "tool": "run_sql",
        "tables": [{"schema": "raw", "table": "customers"}],
        "columns": [],
        "query_type": "SELECT",
        "has_limit": true,
        "row_count": null,
        "region": null,
    } == "DENY"
}

test_marketing_financial_column_denied if {
    main.decision with input as {
        "role": "marketing",
        "tool": "run_sql",
        "tables": [{"schema": "reporting", "table": "customers"}],
        "columns": ["bank_account"],
        "query_type": "SELECT",
        "has_limit": true,
        "row_count": null,
        "region": null,
    } == "DENY"
}

test_large_query_requires_approval if {
    main.decision with input as {
        "role": "data_analyst",
        "tool": "run_sql",
        "tables": [{"schema": "reporting", "table": "daily_kpis"}],
        "columns": [],
        "query_type": "SELECT",
        "has_limit": true,
        "row_count": 1001,
        "region": null,
    } == "REQUIRE_APPROVAL"
}

test_sales_region_constraint if {
    main.constraints with input as {
        "role": "sales",
        "tool": "run_sql",
        "tables": [{"schema": "reporting", "table": "daily_kpis"}],
        "columns": [],
        "query_type": "SELECT",
        "has_limit": true,
        "row_count": null,
        "region": "NA",
    } == {"region_filter": "NA"}
}
