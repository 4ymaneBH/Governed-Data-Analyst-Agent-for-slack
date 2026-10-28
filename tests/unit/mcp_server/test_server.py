from services.mcp_server.analysis import QueryAnalyzer


def test_analyze_select_simple():
    query = "SELECT * FROM reporting.daily_kpis"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["query_type"] == "SELECT"
    assert analysis["has_select_star"]
    assert not analysis["is_ddl"]
    assert not analysis["is_dml"]
    assert {"schema": "reporting", "table": "daily_kpis"} in analysis["tables"]

def test_analyze_select_with_limit():
    query = "SELECT region, revenue FROM reporting.daily_kpis LIMIT 10"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["has_limit"]

def test_analyze_danger_ddl():
    query = "DROP TABLE reporting.daily_kpis"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["is_ddl"]
    assert analysis["query_type"] == "DDL"

def test_analyze_danger_dml():
    query = "DELETE FROM reporting.customers WHERE status = 'churned'"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["is_dml"]
    assert analysis["query_type"] == "DML"
