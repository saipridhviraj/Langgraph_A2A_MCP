import logging
import asyncio
from typing import Any, TypedDict, Optional, List, Dict
from uuid import uuid4
import httpx

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
)

from langgraph.graph import StateGraph, END

PLANNER_URL = 'http://localhost:11000'
ORCHESTRATOR_URL = 'http://localhost:11001'
REFLECTOR_URL = 'http://localhost:11003'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NodeOutput(TypedDict, total=False):
    node_name: str
    raw_response: SendMessageResponse
    extracted_artifact_name: Optional[str]
    extracted_artifact_text: Optional[str]

class AgentState(TypedDict):
    user_input: str
    history: List[NodeOutput]

async def fetch_agent_card(httpx_client: httpx.AsyncClient, base_url: str) -> AgentCard:
    logger.debug(f"Fetching agent card from {base_url}...")
    resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
    card = await resolver.get_agent_card()
    logger.debug(f"Agent card fetched for {base_url}: {card.name}")
    return card

async def call_a2a_agent(
    client: A2AClient,
    text: str,
    artifact_name: Optional[str] = None,
    artifact_text: Optional[str] = None,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> SendMessageResponse:
    message_parts = [{'kind': 'text', 'text': text}]
    message = {
        'role': 'user',
        'parts': message_parts,
        'messageId': uuid4().hex,
    }
    if context_id:
        message['contextId'] = context_id
    if task_id:
        message['taskId'] = task_id
    artifacts_list = None
    if artifact_name and artifact_text is not None:
        artifacts_list = [{
            'name': artifact_name,
            'parts': [{'kind': 'text', 'text': artifact_text}]
        }]
    params = MessageSendParams(message=message, artifacts=artifacts_list) if artifacts_list else MessageSendParams(message=message)
    request = SendMessageRequest(id=str(uuid4()), params=params)
    response = await client.send_message(request)
    logger.debug(f"Received response from agent.")
    return response

def _find_extracted_artifact(
    history: List[NodeOutput], 
    source_node_name: str, 
    artifact_name: str
) -> Optional[str]:
    for entry in reversed(history):
        if entry.get('node_name') == source_node_name and \
           entry.get('extracted_artifact_name') == artifact_name:
            return entry.get('extracted_artifact_text')
    return None

class PlannerNode:
    def __init__(self, client: A2AClient):
        self.client = client
        self.node_name = 'planner'
    async def __call__(self, state: AgentState) -> AgentState:
        logger.info(f'--- Node: Calling {self.node_name.capitalize()}Agent ---')
        user_input = state['user_input']
        response = await call_a2a_agent(self.client, user_input)
        if not hasattr(response.root, "result"):
            logger.error(f"{self.node_name.capitalize()}Agent returned error: {getattr(response.root, 'error', 'Unknown error')}")
            raise RuntimeError(f"{self.node_name.capitalize()}Agent error: {getattr(response.root, 'error', 'Unknown error')}")
        planned_tasks = None
        for artifact in getattr(response.root.result, 'artifacts', []):
            if artifact.name == 'planned_tasks':
                planned_tasks = artifact.parts[0].root.text
                break
        if not planned_tasks:
            logger.error(f'Error: No "planned_tasks" artifact found in {self.node_name.capitalize()}Agent response.')
            raise RuntimeError(f'No "planned_tasks" artifact found in {self.node_name.capitalize()}Agent response. Cannot proceed.')
        node_output: NodeOutput = {
            'node_name': self.node_name,
            'raw_response': response,
            'extracted_artifact_name': 'planned_tasks',
            'extracted_artifact_text': planned_tasks
        }
        state['history'].append(node_output)
        logger.info(f"{self.node_name.capitalize()}Agent returned planned_tasks: {planned_tasks[::]}...")
        return state

class OrchestratorNode:
    def __init__(self, client: A2AClient):
        self.client = client
        self.node_name = 'orchestrator'
    async def __call__(self, state: AgentState) -> AgentState:
        logger.info(f'--- Node: Calling {self.node_name.capitalize()}Agent ---')
        planned_tasks = _find_extracted_artifact(state['history'], 'planner', 'planned_tasks')
        if not planned_tasks:
            logger.error(f'Error: "planned_tasks" not available in history for {self.node_name.capitalize()}Agent.')
            raise RuntimeError(f'"planned_tasks" not available for {self.node_name.capitalize()}Agent. Cannot proceed.')
        response = await call_a2a_agent(
            self.client, 
            text=planned_tasks,
            artifact_name='planned_tasks', 
            artifact_text=planned_tasks
        )
        if not hasattr(response.root, "result"):
            logger.error(f"{self.node_name.capitalize()}Agent returned error: {getattr(response.root, 'error', 'Unknown error')}")
            raise RuntimeError(f"{self.node_name.capitalize()}Agent error: {getattr(response.root, 'error', 'Unknown error')}")
        orchestrated_results = None
        for artifact in getattr(response.root.result, 'artifacts', []):
            if artifact.name == 'orchestrated_results':
                orchestrated_results = artifact.parts[0].root.text
                break
        if not orchestrated_results:
            logger.error(f'Error: No "orchestrated_results" artifact found in {self.node_name.capitalize()}Agent response.')
            raise RuntimeError(f'No "orchestrated_results" artifact found in {self.node_name.capitalize()}Agent response. Cannot proceed.')
        node_output: NodeOutput = {
            'node_name': self.node_name,
            'raw_response': response,
            'extracted_artifact_name': 'orchestrated_results',
            'extracted_artifact_text': orchestrated_results
        }
        state['history'].append(node_output)
        logger.info(f"{self.node_name.capitalize()}Agent returned orchestrated_results (first 100 chars): {orchestrated_results[:100]}...")
        return state

class ReflectorNode:
    def __init__(self, client: A2AClient):
        self.client = client
        self.node_name = 'reflector'
    async def __call__(self, state: AgentState) -> AgentState:
        logger.info(f'--- Node: Calling {self.node_name.capitalize()}Agent ---')
        orchestrated_results = _find_extracted_artifact(state['history'], 'orchestrator', 'orchestrated_results')
        if not orchestrated_results:
            logger.error(f'Error: "orchestrated_results" not available in history for {self.node_name.capitalize()}Agent.')
            raise RuntimeError(f'"orchestrated_results" not available for {self.node_name.capitalize()}Agent. Cannot proceed.')
        response = await call_a2a_agent(self.client, orchestrated_results)
        node_output: NodeOutput = {
            'node_name': self.node_name,
            'raw_response': response,
        }
        state['history'].append(node_output)
        logger.info(f"{self.node_name.capitalize()}Agent response received. Processing complete.")
        return state

async def main():
    user_input = 'Plan a trip from Paris to Rome with sightseeing.'
    async with httpx.AsyncClient(timeout=120.0) as httpx_client:
        logger.info("Initializing A2A clients for Planner, Orchestrator, and Reflector...")
        planner_card = await fetch_agent_card(httpx_client, PLANNER_URL)
        planner_client = A2AClient(httpx_client=httpx_client, agent_card=planner_card)
        logger.info(f"PlannerAgent client initialized for {PLANNER_URL}")
        orchestrator_card = await fetch_agent_card(httpx_client, ORCHESTRATOR_URL)
        orchestrator_client = A2AClient(httpx_client=httpx_client, agent_card=orchestrator_card)
        logger.info(f"OrchestratorAgent client initialized for {ORCHESTRATOR_URL}")
        reflector_card = await fetch_agent_card(httpx_client, REFLECTOR_URL)
        reflector_client = A2AClient(httpx_client=httpx_client, agent_card=reflector_card)
        logger.info(f"ReflectorAgent client initialized for {REFLECTOR_URL}")
        graph = StateGraph(AgentState) 
        graph.add_node('planner', PlannerNode(planner_client))
        graph.add_node('orchestrator', OrchestratorNode(orchestrator_client))
        graph.add_node('reflector', ReflectorNode(reflector_client))
        graph.add_edge('planner', 'orchestrator')
        graph.add_edge('orchestrator', 'reflector')
        graph.set_entry_point('planner')
        graph.set_finish_point('reflector')
        app = graph.compile()
        logger.info("LangGraph workflow compiled successfully.")
        initial_state: AgentState = {'user_input': user_input, 'history': []}
        logger.info(f"\n--- Starting LangGraph execution for user input: '{user_input}' ---")
        try:
            result_state = await app.ainvoke(initial_state)
            logger.info("\n--- LangGraph execution completed successfully! ---")
            print("\n--- Final Results from LangGraph History ---")
            print(f"Original User Input: {result_state['user_input']}")
            for entry in result_state['history']:
                print(f"\n--- Output from Node: {entry.get('node_name').capitalize()} ---")
                raw_response = entry.get('raw_response')
                if raw_response:
                    print(f"Raw A2A Response:\n{raw_response.model_dump(mode='json', exclude_none=True)}")
                extracted_artifact_name = entry.get('extracted_artifact_name')
                extracted_artifact_text = entry.get('extracted_artifact_text')
                if extracted_artifact_name and extracted_artifact_text:
                    print(f"Extracted Artifact ('{extracted_artifact_name}'):\n{extracted_artifact_text}")
                elif extracted_artifact_name:
                    print(f"Artifact '{extracted_artifact_name}' was requested but not extracted/found.")
            # After the loop, print only the last Reflector message
            for entry in reversed(result_state['history']):
                if entry.get('node_name') == 'reflector':
                    raw_response = entry.get('raw_response')
                    if raw_response:
                        final_answer = None
                        for artifact in getattr(raw_response.root.result, 'artifacts', []):
                            if artifact.name == 'final_answer':
                                final_answer = artifact.parts[0].root.text
                                break
                        if final_answer:
                            print(f"\nReflector Agent's Final Message:\n{final_answer}")
                        else:
                            print("\nNo 'final_answer' artifact found in ReflectorAgent response.")
                    break
            print("\n------------------------------------------------------")
        except RuntimeError as e:
            logger.error(f"Workflow failed due to a crucial step: {e}")
        except Exception as e:
            logger.exception("An unexpected error occurred during workflow execution.")

if __name__ == '__main__':
    asyncio.run(main())
