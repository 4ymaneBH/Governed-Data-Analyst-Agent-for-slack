# Column-Level Security Policy
# Controls access to sensitive columns (PII, financial data)

package analyst.columns

import rego.v1

default allow := true
default deny_reason := ""

# PII columns that require special handling
pii_columns := {
    "email", "phone", "address", "address_line1", "address_line2",
    "contact_name", "card_last_four", "ssn", "tax_id"
}

# Financial sensitive columns
financial_columns := {
    "payment_method", "bank_account", "routing_number"
}

# Roles that can see PII (with approval)
pii_allowed_roles := {"admin", "data_analyst"}

# Roles that can see financial data
financial_allowed_roles := {"admin", "data_analyst", "finance"}

# Columns that should be masked instead of denied
maskable_columns := {
    "email": "***@***.***",
    "phone": "***-***-****",
    "card_last_four": "****"
}

# Roles that get masked data instead of denied
mask_eligible_roles := {"sales", "marketing"}

# Check if requested columns contain PII
has_pii_columns if {
    some col in input.columns
    lower(col) in pii_columns
}

# Check if requested columns contain financial data
has_financial_columns if {
    some col in input.columns
    lower(col) in financial_columns
}

# Determine if access is allowed
allow if {
    input.tool != "run_sql"
}

allow if {
    input.tool == "run_sql"
    not has_pii_columns
    not has_financial_columns
}

allow if {
    input.tool == "run_sql"
    has_pii_columns
    input.role in pii_allowed_roles
}

allow if {
    input.tool == "run_sql"
    has_financial_columns
    not has_pii_columns
    input.role in financial_allowed_roles
}

allow if {
    input.tool == "run_sql"
    has_pii_columns
    input.role in mask_eligible_roles
}

# Denial reason
deny_reason := "Access to PII columns requires data_analyst or admin role" if {
    input.tool == "run_sql"
    has_pii_columns
    not input.role in pii_allowed_roles
    not input.role in mask_eligible_roles
}

deny_reason := "Access to financial columns requires appropriate role" if {
    input.tool == "run_sql"
    has_financial_columns
    not input.role in financial_allowed_roles
}

# Constraints - columns to mask
constraints := {"masked_columns": masked} if {
    input.tool == "run_sql"
    input.role in mask_eligible_roles
    has_pii_columns
    masked := [col | some col in input.columns; lower(col) in pii_columns]
}

constraints := {} if {
    input.tool != "run_sql"
}

constraints := {} if {
    input.tool == "run_sql"
    not input.role in mask_eligible_roles
}

constraints := {} if {
    input.tool == "run_sql"
    input.role in mask_eligible_roles
    not has_pii_columns
}

# Rule IDs
rule_ids := ["columns.pii_access"] if {
    input.tool == "run_sql"
    has_pii_columns
    input.role in pii_allowed_roles
}

rule_ids := ["columns.pii_masked"] if {
    input.tool == "run_sql"
    has_pii_columns
    input.role in mask_eligible_roles
}

rule_ids := ["columns.pii_denied"] if {
    input.tool == "run_sql"
    has_pii_columns
    not input.role in pii_allowed_roles
    not input.role in mask_eligible_roles
}

rule_ids := [] if {
    input.tool != "run_sql"
}

rule_ids := [] if {
    input.tool == "run_sql"
    not has_pii_columns
    not has_financial_columns
}
