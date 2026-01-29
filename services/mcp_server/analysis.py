import re

class QueryAnalyzer:
    """Analyze SQL queries for governance checks."""
    
    # Dangerous patterns
    DDL_PATTERNS = re.compile(
        r'\b(CREATE|ALTER|DROP|TRUNCATE|RENAME)\b',
        re.IGNORECASE
    )
    DML_PATTERNS = re.compile(
        r'\b(INSERT|UPDATE|DELETE|MERGE)\b',
        re.IGNORECASE
    )
    
    # Table extraction pattern
    TABLE_PATTERN = re.compile(
        r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)'
        r'|\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)',
        re.IGNORECASE
    )
    
    # Column extraction (simplified)
    SELECT_STAR_PATTERN = re.compile(r'\bSELECT\s+\*', re.IGNORECASE)
    
    # Limit check
    LIMIT_PATTERN = re.compile(r'\bLIMIT\s+\d+', re.IGNORECASE)
    AGGREGATE_PATTERN = re.compile(
        r'\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b',
        re.IGNORECASE
    )
    
    @classmethod
    def analyze(cls, query: str) -> dict:
        """Analyze SQL query and extract metadata."""
        result = {
            "is_ddl": bool(cls.DDL_PATTERNS.search(query)),
            "is_dml": bool(cls.DML_PATTERNS.search(query)),
            "has_select_star": bool(cls.SELECT_STAR_PATTERN.search(query)),
            "has_limit": bool(cls.LIMIT_PATTERN.search(query)),
            "is_aggregate": bool(cls.AGGREGATE_PATTERN.search(query)),
            "tables": [],
            "query_type": "SELECT"
        }
        
        # Determine query type
        if result["is_ddl"]:
            result["query_type"] = "DDL"
        elif result["is_dml"]:
            result["query_type"] = "DML"
        
        # Extract tables
        for match in cls.TABLE_PATTERN.finditer(query):
            table = match.group(1) or match.group(2)
            if table:
                parts = table.split(".")
                if len(parts) == 2:
                    result["tables"].append({"schema": parts[0], "table": parts[1]})
                else:
                    result["tables"].append({"schema": "public", "table": parts[0]})
        
        return result
