# Approval Policy
# Defines conditions that require admin approval

package analyst.approval

import rego.v1

default required := false
default reason := ""

# Schemas that always require approval
approval_required_schemas := {"raw"}

# Actions that require approval
approval_required_actions := {
    "data_export",
    "bulk_query"
}

# Large result sets require approval
large_result_threshold := 1000

# Check if accessing approval-required schema
accessing_sensitive_schema if {
    some table in input.tables
    table.schema in approval_required_schemas
}

# Check if large data request
large_data_request if {
    input.row_count != null
    input.row_count > large_result_threshold
}

# Check if PII access by admin
admin_pii_access if {
    input.role == "admin"
    some col in input.columns
    col in {"email", "phone", "ssn"}
}

# Approval required checks
required if {
    input.tool == "run_sql"
    accessing_sensitive_schema
    input.role != "admin"
}

required if {
    input.tool == "run_sql"
    large_data_request
}

required if {
    input.tool == "run_sql"
    admin_pii_access
}

# Reason for approval
reason := "Access to raw schema requires admin approval" if {
    input.tool == "run_sql"
    accessing_sensitive_schema
    input.role != "admin"
}

reason := sprintf("Large data request (%d rows) requires approval", [input.row_count]) if {
    input.tool == "run_sql"
    large_data_request
}

reason := "Admin PII access requires explicit approval" if {
    input.tool == "run_sql"
    admin_pii_access
}

# Constraints
constraints := {"approval_type": "sensitive_schema"} if {
    required
    accessing_sensitive_schema
}

constraints := {"approval_type": "large_data"} if {
    required
    large_data_request
    not accessing_sensitive_schema
}

constraints := {"approval_type": "admin_pii"} if {
    required
    admin_pii_access
    not accessing_sensitive_schema
    not large_data_request
}

constraints := {} if {
    not required
}

# Rule IDs
rule_ids := ["approval.sensitive_schema"] if {
    required
    accessing_sensitive_schema
}

rule_ids := ["approval.large_data"] if {
    required
    large_data_request
    not accessing_sensitive_schema
}

rule_ids := ["approval.admin_pii"] if {
    required
    admin_pii_access
    not accessing_sensitive_schema
    not large_data_request
}

rule_ids := [] if {
    not required
}
