import pytest
from unittest.mock import AsyncMock, patch
from services.agent.main import parse_intent, AgentState

@pytest.mark.asyncio
async def test_parse_intent_metric():
    # Setup state
    state = AgentState(
        question="What is our CAC?",
        question_type="unknown",
        request_id="test-id",
        user_context={}
    )
    
    # Mock ollama_client
    with patch("services.agent.main.ollama_client") as mock_client:
        mock_client.generate = AsyncMock(return_value="metric")
        
        # Execute
        new_state = await parse_intent(state)
        
        # Assert
        assert new_state["question_type"] == "metric"
        mock_client.generate.assert_called_once()

@pytest.mark.asyncio
async def test_parse_intent_fallback():
    # Setup state
    state = AgentState(
        question="Show me top customers",
        question_type="unknown",
        request_id="test-id",
        user_context={}
    )
    
    # Mock ollama_client returning garbage
    with patch("services.agent.main.ollama_client") as mock_client:
        mock_client.generate = AsyncMock(return_value="I think this is a sql query")
        
        # Execute
        new_state = await parse_intent(state)
        
        # Assert - should default to sql_analysis
        assert new_state["question_type"] == "sql_analysis"
