# _mcp_client_test.py
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import asyncio

async def main():
    try:
        # Create a StreamableHttpTransport explicitly - matching your server configuration
        print("Connecting to server...")
        transport = StreamableHttpTransport("http://127.0.0.1:9002/mcp")

        # Use the transport with the client
        async with Client(transport=transport) as client:
            # List available tools
            tools = await client.list_tools()
            print(f"Available tools: {tools}")
            result = await client.call_tool("PlacesToSee", {"query": "Rome"})
            print(f"Result from PlacesToSee: {result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # This runs the async function properly
    asyncio.run(main())