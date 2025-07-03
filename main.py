import logging
import os
import sys
import subprocess

import click
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv

from agents.planner_agent import PlannerAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.tool_agent import ToolAgent
from agents.reflector_agent import ReflectorAgent
from agent_executor import (
    PlannerAgentExecutor,
    OrchestratorAgentExecutor,
    ToolAgentExecutor,
    ReflectorAgentExecutor,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AGENT_CONFIGS = [
    {
        'name': 'Planner Agent',
        'executor': PlannerAgentExecutor(),
        'class': PlannerAgent,
        'port': 11000,
        'description': 'Decomposes user input into a list of travel tasks',
        'skill_id': 'plan_travel',
        'skill_name': 'Travel Planning',
        'skill_desc': 'Plans and decomposes travel requests into tasks',
        'examples': ['Plan a trip from Paris to Rome with sightseeing.'],
    },
    {
        'name': 'Orchestrator Agent',
        'executor': OrchestratorAgentExecutor(),
        'class': OrchestratorAgent,
        'port': 11001,
        'description': 'Orchestrates task execution and dependency resolution',
        'skill_id': 'orchestrate_travel',
        'skill_name': 'Travel Orchestration',
        'skill_desc': 'Orchestrates and routes travel tasks to tool agents',
        'examples': ['Orchestrate planned travel tasks.'],
    },
    {
        'name': 'Tool Agent',
        'executor': ToolAgentExecutor(),
        'class': ToolAgent,
        'port': 11002,
        'description': 'Executes travel tools (MCP servers)',
        'skill_id': 'tool_travel',
        'skill_name': 'Travel Tool Execution',
        'skill_desc': 'Executes travel-related tools and APIs',
        'examples': ['Book a flight from Paris to Rome.'],
    },
    {
        'name': 'Reflector Agent',
        'executor': ReflectorAgentExecutor(),
        'class': ReflectorAgent,
        'port': 11003,
        'description': 'Summarizes tool results into a final answer',
        'skill_id': 'reflect_travel',
        'skill_name': 'Travel Reflection',
        'skill_desc': 'Summarizes and reflects on travel results',
        'examples': ['Summarize all travel bookings and plans.'],
    },
]

@click.group()
def cli():
    pass

@cli.command(name="all_agents")
def run_all_agents():
    """Starts all agent servers in parallel (each in its own process)."""
    agents = [
        "planner_agent",
        "orchestrator_agent",
        "tool_agent",
        "reflector_agent",
    ]
    processes = []
    for agent in agents:
        print(f"Starting {agent}...")
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), agent])
        processes.append(p)
    print("All agents started. Press Ctrl+C to stop.")
    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        print("\nShutting down all agents...")
        for p in processes:
            p.terminate()
        print("All agents stopped.")

for agent_cfg in AGENT_CONFIGS:
    @cli.command(name=agent_cfg['name'].replace(' ', '_').lower())
    @click.option('--host', default='localhost')
    @click.option('--port', default=agent_cfg['port'])
    def run_agent(host, port, agent_cfg=agent_cfg):
        """Starts the {} server.""".format(agent_cfg['name'])
        try:
            capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
            skill = AgentSkill(
                id=agent_cfg['skill_id'],
                name=agent_cfg['skill_name'],
                description=agent_cfg['skill_desc'],
                tags=['travel', 'a2a'],
                examples=agent_cfg['examples'],
            )
            agent_card = AgentCard(
                name=agent_cfg['name'],
                description=agent_cfg['description'],
                url=f'http://{host}:{port}/',
                version='1.0.0',
                defaultInputModes=['text/plain'],
                defaultOutputModes=['text/plain'],
                capabilities=capabilities,
                skills=[skill],
            )
            httpx_client = httpx.AsyncClient()
            request_handler = DefaultRequestHandler(
                agent_executor=agent_cfg['executor'],
                task_store=InMemoryTaskStore(),
                push_notifier=InMemoryPushNotifier(httpx_client),
            )
            server = A2AStarletteApplication(
                agent_card=agent_card, http_handler=request_handler
            )
            uvicorn.run(server.build(), host=host, port=port)
        except Exception as e:
            logger.error(f'An error occurred during server startup: {e}')
            sys.exit(1)

if __name__ == '__main__':
    cli()
