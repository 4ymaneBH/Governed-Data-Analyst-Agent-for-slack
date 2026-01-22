# Role-Based Access Control Policy
# Defines which roles can access which tools

package analyst.rbac

import rego.v1

default allow := false
default deny_reason := ""

# Tool permissions by role
tool_permissions := {
    "intern": {"search_docs", "explain_metric"},
    "marketing": {"search_docs", "explain_metric", "run_sql", "generate_chart"},
    "sales": {"search_docs", "explain_metric", "run_sql", "generate_chart"},
    "data_analyst": {"search_docs", "explain_metric", "run_sql", "generate_chart"},
    "admin": {"search_docs", "explain_metric", "run_sql", "generate_chart"}
}

# Valid roles
valid_roles := {"intern", "marketing", "sales", "data_analyst", "admin"}

# Check if role is valid
role_valid if {
    input.role in valid_roles
}

# Check if tool is allowed for role
tool_allowed if {
    input.tool in tool_permissions[input.role]
}

# Allow rule
allow if {
    role_valid
    tool_allowed
}

# Denial reason
deny_reason := sprintf("Role '%s' is not authorized to use tool '%s'", [input.role, input.tool]) if {
    role_valid
    not tool_allowed
}

deny_reason := sprintf("Invalid role: '%s'", [input.role]) if {
    not role_valid
}

# Rule IDs for audit
rule_ids := ["rbac.tool_permission"] if {
    allow
}

rule_ids := ["rbac.tool_denied"] if {
    role_valid
    not tool_allowed
}

rule_ids := ["rbac.invalid_role"] if {
    not role_valid
}
