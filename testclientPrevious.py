import logging
from typing import Any
from uuid import uuid4
import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
)

PLANNER_URL = 'http://localhost:11000'
ORCHESTRATOR_URL = 'http://localhost:11001'
REFLECTOR_URL = 'http://localhost:11003'

async def fetch_agent_card(httpx_client, base_url):
    resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
    return await resolver.get_agent_card()

async def call_agent(client, text, context_id=None, task_id=None):
    message = {
        'role': 'user',
        'parts': [{'kind': 'text', 'text': text}],
        'messageId': uuid4().hex,
    }
    if context_id:
        message['contextId'] = context_id
    if task_id:
        message['taskId'] = task_id
    request = SendMessageRequest(
        id=str(uuid4()), params=MessageSendParams(message=message)
    )
    response = await client.send_message(request)
    return response

async def call_agent_with_artifact(client, artifact_name, artifact_text, context_id=None, task_id=None):
    message = {
        'role': 'user',
        'parts': [{'kind': 'text', 'text': artifact_text}],
        'messageId': uuid4().hex,
    }
    if context_id:
        message['contextId'] = context_id
    if task_id:
        message['taskId'] = task_id
    # a2a artifact support: send as 'artifacts' in params
    params = MessageSendParams(message=message, artifacts=[{
        'name': artifact_name,
        'parts': [{'kind': 'text', 'text': artifact_text}]
    }])
    request = SendMessageRequest(id=str(uuid4()), params=params)
    response = await client.send_message(request)
    return response

async def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    user_input = 'Plan a trip from Paris to Rome with sightseeing.'
    async with httpx.AsyncClient() as httpx_client:
        # 1. Call PlannerAgent
        planner_card = await fetch_agent_card(httpx_client, PLANNER_URL)
        planner_client = A2AClient(httpx_client=httpx_client, agent_card=planner_card)
        logger.info('Calling PlannerAgent...')
        planner_response = await call_agent(planner_client, user_input)
        print("planner_response-------:",planner_response)
        print('PlannerAgent response:', planner_response.model_dump(mode='json', exclude_none=True))
        planned_tasks = None
        # Try to extract planned_tasks artifact
        for artifact in getattr(planner_response.root.result, 'artifacts', []):
            if artifact.name == 'planned_tasks':
                planned_tasks = artifact.parts[0].root.text
        if not planned_tasks:
            raise RuntimeError('No planned_tasks artifact found in PlannerAgent response.')
        

        # 2. Call OrchestratorAgent (send planned_tasks as artifact)
        orchestrator_card = await fetch_agent_card(httpx_client, ORCHESTRATOR_URL)
        orchestrator_client = A2AClient(httpx_client=httpx_client, agent_card=orchestrator_card)
        logger.info('Calling OrchestratorAgent...')
        orchestrator_response = await call_agent_with_artifact(
            orchestrator_client, 'planned_tasks', planned_tasks
        )
        print('OrchestratorAgent response:', orchestrator_response.model_dump(mode='json', exclude_none=True))
        orchestrated_results = None
        for artifact in getattr(orchestrator_response.root.result, 'artifacts', []):
            if artifact.name == 'orchestrated_results':
                orchestrated_results = artifact.parts[0].root.text
        if not orchestrated_results:
            raise RuntimeError('No orchestrated_results artifact found in OrchestratorAgent response.')
        
        
        # 3. Call ReflectorAgent
        reflector_card = await fetch_agent_card(httpx_client, REFLECTOR_URL)
        reflector_client = A2AClient(httpx_client=httpx_client, agent_card=reflector_card)
        logger.info('Calling ReflectorAgent...')
        reflector_response = await call_agent(reflector_client, orchestrated_results)
        print('ReflectorAgent response:', reflector_response.model_dump(mode='json', exclude_none=True))

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
