import os
from collections.abc import AsyncIterable
from typing import Any, Literal
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
import re

memory = MemorySaver()

class ResponseFormat(BaseModel):
    """Respond to the user in this format."""
    status: Literal['planning', 'completed', 'error'] = 'planning'
    message: str

class PlannerAgent:
    """
    PlannerAgent: Decomposes user input into a list of tasks with MCP server and dependencies using an LLM.
    Now supports streaming and structured responses.
    """
    SYSTEM_INSTRUCTION = (
        'You are a travel planning assistant. Given a user request, break it down into a list of tasks. '
        'Each task should have a name, the MCP server to use (e.g., TransportServer, SightseeingServer), and dependencies (if any). '
        'Output a list of JSON objects with keys: task, mcp_server, depends.\n'
        'Example:\n'
        '[\n'
        '  {"task": "Book a flight from Paris to Rome", "mcp_server": "TransportServer", "depends": []},\n'
        '  {"task": "Find sightseeing spots in Rome", "mcp_server": "SightseeingServer", "depends": []}\n'
        ']'
    )
    FORMAT_INSTRUCTION = (
        'Set response status to planning if you are still working on the plan.'
        'Set response status to error if there is an error while processing the request.'
        'Set response status to completed if the plan is complete.'
    )

    def __init__(self):
        model_source = os.getenv('model_source', 'google')
        if model_source == 'google':
            self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
        else:
            self.model = ChatOpenAI(
                model=os.getenv('TOOL_LLM_NAME'),
                openai_api_key=os.getenv('API_KEY', 'EMPTY'),
                openai_api_base=os.getenv('TOOL_LLM_URL'),
                temperature=0,
            )
        self.graph = create_react_agent(
            self.model,
            tools=[],
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=(self.FORMAT_INSTRUCTION, ResponseFormat),
        )

    async def stream(self, user_input: str, context_id: str = 'planner') -> AsyncIterable[dict[str, Any]]:
        # Streaming progress message
        yield {
            'status': 'planning',
            'message': 'Planning your trip...'
        }
        inputs = {'messages': [('user', user_input)]}
        config = {'configurable': {'thread_id': context_id}}
        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if isinstance(message, AIMessage):
                return_plan = message.content
                # Remove markdown code block if present
                return_plan_clean = re.sub(r'^```json\\s*|```$', '', return_plan.strip(), flags=re.MULTILINE)
                yield {
                    'status': 'completed',
                    'message': return_plan_clean
                }
                return
        yield {
            'status': 'error',
            'message': 'Sorry, I could not generate a plan.'
        }
