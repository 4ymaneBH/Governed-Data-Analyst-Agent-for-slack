import pytest
from services.mcp_server.analysis import QueryAnalyzer

def test_analyze_select_simple():
    query = "SELECT * FROM reporting.daily_kpis"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["query_type"] == "SELECT"
    assert analysis["has_select_star"] == True
    assert analysis["is_ddl"] == False
    assert analysis["is_dml"] == False
    assert {"schema": "reporting", "table": "daily_kpis"} in analysis["tables"]

def test_analyze_select_with_limit():
    query = "SELECT region, revenue FROM reporting.daily_kpis LIMIT 10"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["has_limit"] == True

def test_analyze_danger_ddl():
    query = "DROP TABLE reporting.daily_kpis"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["is_ddl"] == True
    assert analysis["query_type"] == "DDL"

def test_analyze_danger_dml():
    query = "DELETE FROM reporting.customers WHERE status = 'churned'"
    analysis = QueryAnalyzer.analyze(query)
    
    assert analysis["is_dml"] == True
    assert analysis["query_type"] == "DML"
