# Governed Data Analyst Agent - OPA Policies
# Main policy entry point that aggregates all policy decisions

package analyst.main

import data.analyst.rbac
import data.analyst.tables
import data.analyst.columns
import data.analyst.rows
import data.analyst.approval

import rego.v1

default decision := "DENY"
default reason := "Access denied by default policy"

# Collect all rule IDs that matched
rule_ids := array.concat(
    array.concat(
        array.concat(rbac.rule_ids, tables.rule_ids),
        columns.rule_ids
    ),
    approval.rule_ids
)

# Collect all constraints
constraints := object.union(
    object.union(columns.constraints, rows.constraints),
    approval.constraints
)

# Main decision logic
decision := "ALLOW" if {
    rbac.allow
    tables.allow
    columns.allow
    not approval.required
}

decision := "REQUIRE_APPROVAL" if {
    rbac.allow
    tables.allow
    columns.allow
    approval.required
}

decision := "DENY" if {
    not rbac.allow
}

decision := "DENY" if {
    rbac.allow
    not tables.allow
}

decision := "DENY" if {
    rbac.allow
    tables.allow
    not columns.allow
}

# Determine denial reason
reason := rbac.deny_reason if {
    not rbac.allow
}

reason := tables.deny_reason if {
    rbac.allow
    not tables.allow
}

reason := columns.deny_reason if {
    rbac.allow
    tables.allow
    not columns.allow
}

reason := approval.reason if {
    rbac.allow
    tables.allow
    columns.allow
    approval.required
}

reason := "Access granted" if {
    decision == "ALLOW"
}
