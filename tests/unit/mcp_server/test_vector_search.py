import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp_server.models import PolicyDecision
from services.mcp_server.server import ToolContext, execute_search_docs


@pytest.mark.asyncio
async def test_search_docs_vector():
    # Setup context
    ctx = ToolContext(
        user_id="test-user",
        slack_user_id="U123",
        role="data_analyst",
        request_id=str(uuid.uuid4())
    )
    
    # Mock PolicyClient to allow access
    mock_policy = AsyncMock()
    mock_policy.evaluate.return_value = PolicyDecision(decision="ALLOW")
    
    # Mock EmbeddingService
    mock_embedding = AsyncMock()
    mock_embedding.generate_embedding.return_value = [0.1, 0.2, 0.3]
    
    # Mock DB pool
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    # Mock DB rows
    mock_conn.fetch.return_value = [
        {
            "doc_id": "doc-1",
            "title": "Test Doc",
            "snippet": "Content",
            "score": 0.9,
            "section": "knowledge_base",
            "metadata": "{}"
        }
    ]
    
    # Apply mocks
    with patch("services.mcp_server.server.policy_client", mock_policy), \
         patch("services.mcp_server.server.embedding_service", mock_embedding), \
         patch("services.mcp_server.server.get_db_pool", new_callable=AsyncMock) as mock_get_pool:
        
        mock_get_pool.return_value = mock_pool
        
        # Execute
        results = await execute_search_docs("test query", ctx)
        
        # Assertions
        assert len(results) == 1
        assert results[0].doc_id == "doc-1"
        
        # Verify embedding was generated
        mock_embedding.generate_embedding.assert_called_once_with("test query")
        
        # Verify SQL query contained vector operator
        call_args = mock_conn.fetch.call_args
        sql_query = call_args[0][0]
        assert "<=>" in sql_query
        assert "INSERT INTO internal.audit_logs" in mock_conn.execute.call_args.args[0]


@pytest.mark.asyncio
async def test_search_docs_denied_before_embedding():
    ctx = ToolContext(
        user_id="test-user",
        slack_user_id="U123",
        role="intern",
        request_id=str(uuid.uuid4()),
    )
    mock_policy = AsyncMock()
    mock_policy.evaluate.return_value = PolicyDecision(
        decision="DENY", reason="Access denied by policy"
    )
    mock_embedding = AsyncMock()

    with (
        patch("services.mcp_server.server.policy_client", mock_policy),
        patch("services.mcp_server.server.embedding_service", mock_embedding),
        patch("services.mcp_server.server.AuditLogger.log", new_callable=AsyncMock) as audit_log,
    ):
        results = await execute_search_docs("restricted query", ctx)

    assert results == []
    mock_embedding.generate_embedding.assert_not_awaited()
    audit_log.assert_awaited_once()
