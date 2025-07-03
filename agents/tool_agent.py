import os
import requests
from collections.abc import AsyncIterable
from typing import Any, Literal
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


memory = MemorySaver()

class ResponseFormat(BaseModel):
    status: Literal['working', 'completed', 'error'] = 'working'
    message: str
    result: dict = {}

class ToolAgent:
    """
    ToolAgent: Uses an LLM to select and call the correct tool on the specified MCP server, and summarizes results.
    """
    SYSTEM_INSTRUCTION = (
        'You are a tool execution agent. Given a task description and an MCP server (TransportServer or SightseeingServer), '
        'decide which tool to call (FlightDetailsTool, BusDetailsTool, PlacesToSee), '
        'infer the required parameters from the task description, call the correct MCP server endpoint, and return the result.\n'
        'Example:\n'
        'Input: {"task": "Book a flight from Paris to Rome", "mcp_server": "TransportServer", "depends": []}\n'
        'Output: Call TransportServer/FlightDetailsTool with params {"source": "Paris", "destination": "Rome"}\n'
        'Input: {"task": "Find sightseeing spots in Rome", "mcp_server": "SightseeingServer", "depends": []}\n'
        'Output: Call SightseeingServer/PlacesToSee with params {"query": "Rome"}'
    )
    FORMAT_INSTRUCTION = (
        'Set response status to working if you are still working on the tool call.'
        'Set response status to error if there is an error while processing the request.'
        'Set response status to completed if the tool call is complete.'
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
        self.transport_server_url = "http://127.0.0.1:9000/mcp"
        self.sightseeing_server_url = "http://127.0.0.1:9002/mcp"

    async def call_tool_via_mcp(self, tool_name: str, argument: dict) -> dict:
        """
        Call a tool on the MCP server using the fastmcp client (async).
        """
        try:
            # Choose the correct MCP server URL based on the tool
            if tool_name == "PlacesToSee":
                mcp_url = self.sightseeing_server_url
            else:
                mcp_url = self.transport_server_url
            transport = StreamableHttpTransport(mcp_url)
            async with Client(transport=transport) as client:
                tools = await client.list_tools()
                print(f"Available tools: {tools}")
                result = await client.call_tool(tool_name, argument)
                return {"result": result}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def stream(self, task, context_id: str = 'tool') -> AsyncIterable[dict[str, Any]]:
        print(f"[ToolAgent.stream] Received task: {task!r}")  # Debug print
        import json
        if isinstance(task, str):
            try:
                task = json.loads(task)
            except Exception:
                yield {
                    'status': 'error',
                    'message': 'ToolAgent received invalid task format.',
                    'result': {}
                }
                return
        yield {
            'status': 'working',
            'message': f"Analyzing task and selecting tool for: {task.get('task')}",
            'result': {}
        }
        tool_to_call = None
        params = task.get('params', {})
        argument = {}
        if task.get('mcp_server') == 'TransportServer':
            if 'bus' in task.get('task', '').lower():
                tool_to_call = 'BusDetailsTool'
                argument = {"source": params.get('source', 'Paris'), "destination": params.get('destination', 'Rome')}
            else:
                tool_to_call = 'FlightDetailsTool'
                argument = {"source": params.get('source', 'Paris'), "destination": params.get('destination', 'Rome')}
        elif task.get('mcp_server') == 'SightseeingServer':
            tool_to_call = 'PlacesToSee'
            argument = {"query": params.get('query', 'Rome')}
        if tool_to_call:
            result = await self.call_tool_via_mcp(tool_to_call, argument)
        else:
            result = {'error': 'Unknown tool'}
        status = 'completed' if 'error' not in result else 'error'
        yield {
            'status': status,
            'message': f"Tool {tool_to_call} execution {'succeeded' if status == 'completed' else 'failed'}.",
            'result': result
        }

    async def execute_tool(self, task: dict) -> dict:
        # Async version for compatibility
        tool = task.get("tool")
        argument = {}
        if tool == "FlightDetailsTool" or tool == "BusDetailsTool":
            argument = {"source": task.get("source", "Paris"), "destination": task.get("destination", "Rome")}
        elif tool == "PlacesToSee":
            argument = {"query": task.get("destination", "Rome")}
        else:
            return {"error": "Unknown tool"}
        return await self.call_tool_via_mcp(tool, argument)
