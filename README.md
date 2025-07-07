# A2A_MCP
Built Multi Agent Travel Chat Service System Using Langgraph, A2A, MCP Frameworks

## Overview

This project demonstrates a modular, agent-based architecture for travel planning and information retrieval. It uses multiple agents (Planner, Orchestrator, Tool, Reflector) that communicate via the A2A protocol and interact with MCP servers for tool execution.

### Key Components

- **Planner Agent**: Decomposes user requests into structured travel tasks.
- **Orchestrator Agent**: Manages task execution and dependencies.
- **Tool Agent**: Selects and calls the appropriate MCP server/tool (e.g., flight, bus, sightseeing).
- **Reflector Agent**: Summarizes tool results into a user-friendly answer.
- **MCP Servers**: Provide endpoints for transport, sightseeing, and employee information.

## Directory Structure

- `agents/`: Agent implementations.
- `mcp_servers/`: Example MCP servers (transport, sightseeing, employee).
- `agent_executor.py`: A2A-compliant agent executors.
- `main.py`: CLI to launch agent servers.
- `test_client.py`, `testclientPrevious.py`: Example clients for end-to-end testing.

## Getting Started

1. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

2. **Set environment variables:**  
   Edit `.env` with your API keys and model settings.

3. **Start MCP servers:**
   ```sh
   python mcp_servers/transport_server.py
   python mcp_servers/sightseeing_server.py
   python mcp_servers/employye.py
   ```

4. **Start all agents:**
   ```sh
   python main.py all_agents
   ```

5. **Run a test client:**
   ```sh
   python test_client.py
   ```

## Example Usage

- **User Input:**  
  `Plan a trip from Paris to Rome with sightseeing.`

- **System Output:**  
  The system plans the trip, orchestrates tool calls, and summarizes the results for the user.

## Requirements

- Python 3.9+
- See [requirements.txt](requirements.txt) for dependencies.

---

For more details, see the code and docstrings in each agent and server file.
