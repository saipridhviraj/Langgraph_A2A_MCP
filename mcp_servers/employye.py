# mcp_server.py
from fastmcp import FastMCP
import json

mcp = FastMCP("My MCP Server")

@mcp.tool()
def addition(a: int, b: int) -> int:
    """This tool helps you in addition of two numbers"""
    c = a + b
    return c

@mcp.tool()
def employees(name: str = "") -> str:
    """This tool provides you with information about the employees"""
    emp_data = [
        {"emp_id": "E003", "name": "Alex", "location": "Texas"},
        {"emp_id": "E002", "name": "Coop", "location": "California"},
        {"emp_id": "E009", "name": "Steve", "location": "Hawkins"}
    ]
    if name:
        for employee in emp_data:
            if employee["name"].lower() == name.lower():
                return json.dumps(employee)
        return "Employee not found"

    return json.dumps(emp_data)

if _name_ == "_main_":
    mcp.run(transport="http", host="127.0.0.1", port=8000, path="/mcp")