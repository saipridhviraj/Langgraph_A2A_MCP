from fastmcp import FastMCP

mcp = FastMCP("TransportServer",stateless_http=True)

@mcp.tool(name="FlightDetailsTool")
def flight_details(source: str, destination: str) -> dict:
    """
    Stub endpoint for flight options between two cities.
    """
    return {
        "source": source,
        "destination": destination,
        "flights": [
            {
                "airline": "Air Sample",
                "flight_no": "AS123",
                "departure": "09:00",
                "arrival": "11:30",
                "price_usd": 150.0,
            },
            {
                "airline": "Demo Air",
                "flight_no": "DA456",
                "departure": "18:45",
                "arrival": "21:15",
                "price_usd": 175.0,
            },
        ],
    }

@mcp.tool(name="BusDetailsTool")
def bus_details(source: str, destination: str) -> dict:
    """
    Stub endpoint for inter-city bus options.
    """
    return {
        "source": source,
        "destination": destination,
        "buses": [
            {
                "operator": "Sample Travels",
                "departure": "07:00",
                "arrival": "13:00",
                "price_usd": 35.0,
            },
            {
                "operator": "Demo Bus Co.",
                "departure": "23:00",
                "arrival": "05:30",
                "price_usd": 32.0,
            },
        ],
    }

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=9000)
