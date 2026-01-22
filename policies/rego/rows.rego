# Row-Level Security Policy
# Enforces region-based access for sales roles

package analyst.rows

import rego.v1

# Constraints for RLS filtering
constraints := {"region_filter": input.region} if {
    input.role == "sales"
    input.region != null
}

constraints := {} if {
    input.role != "sales"
}

constraints := {} if {
    input.role == "sales"
    input.region == null
}

# Rule IDs
rule_ids := ["rows.sales_region_filter"] if {
    input.role == "sales"
    input.region != null
}

rule_ids := [] if {
    input.role != "sales"
}
