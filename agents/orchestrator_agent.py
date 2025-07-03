import os
import json
from collections.abc import AsyncIterable
from typing import Any, Literal
from uuid import uuid4
import httpx
from langchain_core.messages import AIMessage
from pydantic import BaseModel
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
)

class ResponseFormat(BaseModel):
    status: Literal['orchestrating', 'completed', 'error'] = 'orchestrating'
    message: str
    results: list[Any] = []
        
class OrchestratorAgent:
    """
    OrchestratorAgent: Orchestrates task execution and dependency resolution.
    Acts as both a2a server and client to ToolAgent(s).
    """
    def __init__(self, tool_agent_base_url: str = "http://localhost:11002"):
        self.tool_agent_base_url = tool_agent_base_url  # Base URL for ToolAgent's a2a endpoint
        self.tool_agent_card_path = '/.well-known/agent.json'

    async def stream(self, planned_tasks: list, context_id: str = 'orchestrator') -> AsyncIterable[dict[str, Any]]:
        # Streaming progress message
        yield {
            'status': 'orchestrating',
            'message': 'Orchestrating your travel tasks...'
        }
        results = []
        async with httpx.AsyncClient() as httpx_client:
            # Resolve ToolAgent's card
            resolver = A2ACardResolver(
                httpx_client=httpx_client,
                base_url=self.tool_agent_base_url,
            )
            tool_agent_card = await resolver.get_agent_card()
            client = A2AClient(httpx_client=httpx_client, agent_card=tool_agent_card)
            for task in planned_tasks:
                try:
                    send_message_payload = {
                        'message': {
                            'role': 'user',
                            'parts': [
                                {'kind': 'text', 'text': json.dumps(task)}
                            ],
                            'messageId': uuid4().hex,
                        },
                    }
                    request = SendMessageRequest(
                        id=str(uuid4()), params=MessageSendParams(**send_message_payload)
                    )
                    response = await client.send_message(request)
                    tool_result = response.model_dump(mode='json', exclude_none=True)
                    results.append(tool_result)
                    yield {
                        'status': 'orchestrating',
                        'message': f"Completed task: {task['task']}",
                        'results': results.copy()
                    }
                except Exception as e:
                    yield {
                        'status': 'error',
                        'message': f"Error executing task {task['task']}: {e}",
                        'results': results.copy()
                    }
                    return
        yield {
            'status': 'completed',
            'message': 'All tasks completed.',
            'results': results
        }
