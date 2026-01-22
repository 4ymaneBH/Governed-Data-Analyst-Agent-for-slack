# OPA Policy Tests

package analyst.test_rbac

import data.analyst.rbac
import rego.v1

# Test intern can access search_docs
test_intern_search_docs_allowed if {
    rbac.allow with input as {
        "role": "intern",
        "tool": "search_docs"
    }
}

# Test intern cannot access run_sql
test_intern_run_sql_denied if {
    not rbac.allow with input as {
        "role": "intern",
        "tool": "run_sql"
    }
}

# Test marketing can access all basic tools
test_marketing_run_sql_allowed if {
    rbac.allow with input as {
        "role": "marketing",
        "tool": "run_sql"
    }
}

test_marketing_generate_chart_allowed if {
    rbac.allow with input as {
        "role": "marketing",
        "tool": "generate_chart"
    }
}

# Test admin has full access
test_admin_all_tools if {
    rbac.allow with input as {"role": "admin", "tool": "run_sql"}
    rbac.allow with input as {"role": "admin", "tool": "search_docs"}
    rbac.allow with input as {"role": "admin", "tool": "explain_metric"}
    rbac.allow with input as {"role": "admin", "tool": "generate_chart"}
}

# Test invalid role is denied
test_invalid_role_denied if {
    not rbac.allow with input as {
        "role": "hacker",
        "tool": "run_sql"
    }
}
