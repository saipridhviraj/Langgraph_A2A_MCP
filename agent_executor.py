import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError

from agents.planner_agent import PlannerAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.tool_agent import ToolAgent
from agents.reflector_agent import ReflectorAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlannerAgentExecutor(AgentExecutor):
    """
    PlannerAgentExecutor: Decomposes user input into a list of tasks (a2a-compliant).
    Now uses streaming from PlannerAgent.
    """
    def __init__(self, agent=None):
        self.agent = agent or PlannerAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_input = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.contextId)
        try:
            async for item in self.agent.stream(user_input):
                await updater.update_status(
                    TaskState.working if item['status'] == 'planning' else TaskState.completed,
                    new_agent_text_message(item['message'], task.contextId, task.id),
                )
                if item['status'] == 'completed':
                    await updater.add_artifact([
                        Part(root=TextPart(text=str(item['message'])))
                    ], name="planned_tasks")
                    await updater.complete()
                    break
        except Exception as e:
            logger.error(f"[PlannerAgentExecutor] Error: {e}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


class OrchestratorAgentExecutor(AgentExecutor):
    """
    OrchestratorAgentExecutor: Orchestrates task execution and dependency resolution (a2a-compliant).
    """
    def __init__(self, agent=None):
        self.agent = agent or OrchestratorAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.contextId)
        try:
            # Debug print
            print("DEBUG: context.artifacts =", getattr(context, 'artifacts', None))
            print("DEBUG: context.get_user_input() =", context.get_user_input())
            # Robust artifact extraction: handle both dict and object
            planned_tasks = None
            for artifact in getattr(context, 'artifacts', []):
                name = getattr(artifact, 'name', None) or (artifact.get('name') if isinstance(artifact, dict) else None)
                if name == 'planned_tasks':
                    parts = getattr(artifact, 'parts', None) or (artifact.get('parts') if isinstance(artifact, dict) else None)
                    if parts:
                        part = parts[0]
                        # Try object, then dict
                        text = getattr(part, 'root', None)
                        if text and hasattr(text, 'text'):
                            planned_tasks = text.text
                        else:
                            planned_tasks = part.get('text') or (part.get('root', {}).get('text') if isinstance(part.get('root', {}), dict) else None)
            if not planned_tasks:
                # Fallback to user input
                planned_tasks = context.get_user_input()
                print("DEBUG: Fallback to user input for planned_tasks:", planned_tasks)
            if not planned_tasks:
                raise ValueError('No planned_tasks artifact found in context or user input.')
            # Remove markdown code block if present
            import re, json
            planned_tasks_clean = re.sub(r'```json|```', '', planned_tasks, flags=re.IGNORECASE).strip()
            print("DEBUG: planned_tasks_clean =", planned_tasks_clean)
            planned_tasks_list = json.loads(planned_tasks_clean)
            # Stream orchestration progress
            async for item in self.agent.stream(planned_tasks_list):
                await updater.update_status(
                    TaskState.working if item['status'] == 'orchestrating' else TaskState.completed,
                    new_agent_text_message(item['message'], task.contextId, task.id),
                )
                if item['status'] == 'completed':
                    await updater.add_artifact([
                        Part(root=TextPart(text=str(item['results'])))
                    ], name="orchestrated_results")
                    await updater.complete()
                    break
        except Exception as e:
            logger.error(f"[OrchestratorAgentExecutor] Error: {e}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


class ToolAgentExecutor(AgentExecutor):
    """
    ToolAgentExecutor: Executes a single tool task via MCP (a2a-compliant).
    """
    def __init__(self, agent=None):
        self.agent = agent or ToolAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.contextId)
        try:
            # Robust artifact extraction: handle both dict and object
            import json
            tool_task = None
            for artifact in getattr(context, 'artifacts', []):
                name = getattr(artifact, 'name', None) or (artifact.get('name') if isinstance(artifact, dict) else None)
                if name == 'tool_task':
                    parts = getattr(artifact, 'parts', None) or (artifact.get('parts') if isinstance(artifact, dict) else None)
                    if parts:
                        part = parts[0]
                        text = getattr(part, 'root', None)
                        if text and hasattr(text, 'text'):
                            tool_task = text.text
                        else:
                            tool_task = part.get('text') or (part.get('root', {}).get('text') if isinstance(part.get('root', {}), dict) else None)
            if not tool_task:
                # Fallback to user input
                tool_task = context.get_user_input()
            if not tool_task:
                raise ValueError('No tool_task artifact found in context or user input.')
            # Parse tool_task if it's a JSON string
            if isinstance(tool_task, str):
                try:
                    tool_task_dict = json.loads(tool_task)
                except Exception:
                    tool_task_dict = tool_task  # fallback to string if not JSON
            else:
                tool_task_dict = tool_task
            # Stream tool execution progress
            async for item in self.agent.stream(tool_task_dict):
                await updater.update_status(
                    TaskState.working if item.get('status', '') != 'completed' else TaskState.completed,
                    new_agent_text_message(item.get('message', ''), task.contextId, task.id),
                )
                if item.get('status', '') == 'completed':
                    await updater.add_artifact([
                        Part(root=TextPart(text=str(item.get('result', item.get('message', '')))))
                    ], name="tool_result")
                    await updater.complete()
                    break
        except Exception as e:
            logger.error(f"[ToolAgentExecutor] Error: {e}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


class ReflectorAgentExecutor(AgentExecutor):
    """
    ReflectorAgentExecutor: Summarizes all tool results into a final answer (a2a-compliant).
    """
    def __init__(self, agent=None):
        self.agent = agent or ReflectorAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.contextId)
        try:
            # Robust artifact extraction: handle both dict and object
            orchestrated_results = None
            for artifact in getattr(context, 'artifacts', []):
                name = getattr(artifact, 'name', None) or (artifact.get('name') if isinstance(artifact, dict) else None)
                if name == 'orchestrated_results':
                    parts = getattr(artifact, 'parts', None) or (artifact.get('parts') if isinstance(artifact, dict) else None)
                    if parts:
                        part = parts[0]
                        text = getattr(part, 'root', None)
                        if text and hasattr(text, 'text'):
                            orchestrated_results = text.text
                        else:
                            orchestrated_results = part.get('text') or (part.get('root', {}).get('text') if isinstance(part.get('root', {}), dict) else None)
            if not orchestrated_results:
                # Fallback to user input
                orchestrated_results = context.get_user_input()
            if not orchestrated_results:
                raise ValueError('No orchestrated_results artifact found in context or user input.')
            # If orchestrated_results is a JSON string, parse it
            import json
            try:
                results_list = json.loads(orchestrated_results)
            except Exception:
                results_list = orchestrated_results
            # Stream reflection progress (assuming agent has a stream method)
            async for item in self.agent.stream(results_list):
                await updater.update_status(
                    TaskState.working if item.get('status', '') != 'completed' else TaskState.completed,
                    new_agent_text_message(item.get('message', ''), task.contextId, task.id),
                )
                if item.get('status', '') == 'completed':
                    await updater.add_artifact([
                        Part(root=TextPart(text=str(item.get('final_answer', item.get('message', '')))))
                    ], name="final_answer")
                    await updater.complete()
                    break
        except Exception as e:
            logger.error(f"[ReflectorAgentExecutor] Error: {e}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())
