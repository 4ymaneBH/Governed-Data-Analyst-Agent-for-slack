# Table Access Policy
# Controls which schemas and tables each role can access

package analyst.tables

import rego.v1

default allow := true
default deny_reason := ""

# Schema access by role
schema_access := {
    "intern": set(),  # No SQL access
    "marketing": {"reporting"},
    "sales": {"reporting"},
    "data_analyst": {"reporting", "refined"},
    "admin": {"reporting", "refined", "raw", "internal"}
}

# Blocked tables by role (even if schema is allowed)
blocked_tables := {
    "marketing": {"reporting.user_sessions"},
    "sales": {"reporting.financial_details"},
    "data_analyst": set()
}

# Check if all tables are in allowed schemas
schemas_allowed if {
    input.tool != "run_sql"
}

schemas_allowed if {
    input.tool == "run_sql"
    count(input.tables) == 0
}

schemas_allowed if {
    input.tool == "run_sql"
    count(input.tables) > 0
    every table in input.tables {
        table.schema in schema_access[input.role]
    }
}

# Check if query type is allowed
query_type_allowed if {
    input.tool != "run_sql"
}

query_type_allowed if {
    input.tool == "run_sql"
    input.query_type == "SELECT"
}

query_type_allowed if {
    input.tool == "run_sql"
    input.query_type in {"DDL", "DML"}
    input.role == "admin"
}

# Check for blocked tables
no_blocked_tables if {
    input.tool != "run_sql"
}

no_blocked_tables if {
    input.tool == "run_sql"
    not blocked := blocked_tables[input.role]
}

no_blocked_tables if {
    input.tool == "run_sql"
    blocked := blocked_tables[input.role]
    every table in input.tables {
        full_name := sprintf("%s.%s", [table.schema, table.table])
        not full_name in blocked
    }
}

# Check for LIMIT requirement
has_required_limit if {
    input.tool != "run_sql"
}

has_required_limit if {
    input.tool == "run_sql"
    input.has_limit
}

has_required_limit if {
    input.tool == "run_sql"
    input.role in {"data_analyst", "admin"}
}

# Allow rule
allow if {
    schemas_allowed
    query_type_allowed
    no_blocked_tables
    has_required_limit
}

# Denial reasons
deny_reason := msg if {
    input.tool == "run_sql"
    not schemas_allowed
    denied_schemas := {t.schema | some t in input.tables; not t.schema in schema_access[input.role]}
    msg := sprintf("Access denied to schema(s): %v", [denied_schemas])
}

deny_reason := msg if {
    input.tool == "run_sql"
    schemas_allowed
    not query_type_allowed
    msg := sprintf("Role '%s' cannot execute %s queries", [input.role, input.query_type])
}

deny_reason := "Query requires LIMIT clause for non-aggregate selects" if {
    input.tool == "run_sql"
    schemas_allowed
    query_type_allowed
    not has_required_limit
}

# Rule IDs
rule_ids := ["tables.schema_access"] if {
    input.tool == "run_sql"
    schemas_allowed
}

rule_ids := ["tables.schema_denied"] if {
    input.tool == "run_sql"
    not schemas_allowed
}

rule_ids := [] if {
    input.tool != "run_sql"
}
