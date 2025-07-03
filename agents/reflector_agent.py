import os
from collections.abc import AsyncIterable
from typing import Any, Literal
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

memory = MemorySaver()

class ResponseFormat(BaseModel):
    """Respond to the user in this format."""
    status: Literal['summarizing', 'completed', 'error'] = 'summarizing'
    message: str

class ReflectorAgent:
    """
    ReflectorAgent: Summarizes all tool results into a final answer using an LLM.
    Now supports streaming and structured responses.
    """
    SYSTEM_INSTRUCTION = (
        'You are a travel assistant. Given a list of tool results (e.g., flight details, sightseeing suggestions), '
        'summarize them into a single, user-friendly answer. Focus on clarity and completeness.'
    )
    FORMAT_INSTRUCTION = (
        'Set response status to summarizing if you are still working on the summary.'
        'Set response status to error if there is an error while processing the request.'
        'Set response status to completed if the summary is complete.'
    )

    def __init__(self, llm=None):
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

    async def stream(self, tool_results: list, context_id: str = 'reflector') -> AsyncIterable[dict[str, Any]]:
        user_prompt = "Summarize the following tool results for a user:\n"
        for result in tool_results:
            user_prompt += f"- {result}\n"
        inputs = {'messages': [('user', user_prompt)]}
        config = {'configurable': {'thread_id': context_id}}
        # Streaming progress message
        yield {
            'status': 'summarizing',
            'message': 'Summarizing your travel results...'
        }
        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if isinstance(message, AIMessage):
                yield {
                    'status': 'completed',
                    'message': message.content
                }
                return
        yield {
            'status': 'error',
            'message': 'Sorry, I could not generate a summary.'
        }
