from fastmcp import FastMCP

mcp = FastMCP("SightseeingServer")

@mcp.tool(name="PlacesToSee")
def places_to_see(query: str) -> dict:
    """
    Return a curated list of must-visit places for the given query.
    """
    key = query.lower()
    hardcoded = {
        "paris": [
            {"name": "Eiffel Tower", "category": "Landmark", "notes": "Book tickets in advance"},
            {"name": "Louvre Museum", "category": "Museum", "notes": "Closed Tuesdays"},
            {"name": "Montmartre", "category": "Neighborhood", "notes": "Great for sunset views"},
        ],
        "rome": [
            {"name": "Colosseum", "category": "Landmark", "notes": "Try the underground tour"},
            {"name": "Pantheon", "category": "Historic Temple", "notes": "Free entry"},
            {"name": "Trastevere", "category": "Neighborhood", "notes": "Charming evening vibe"},
        ],
        "goa": [
            {"name": "Baga Beach", "category": "Beach", "notes": "Water-sports hub"},
            {"name": "Basilica of Bom Jesus", "category": "UNESCO Church", "notes": "Baroque architecture"},
            {"name": "Dudhsagar Falls", "category": "Waterfall", "notes": "Best just after monsoon"},
        ],
    }
    recommendations = hardcoded.get(
        key,
        [
            {"name": "Central Park", "category": "Park", "notes": "Iconic urban green space"},
            {"name": "City Museum", "category": "Museum", "notes": "Check special exhibits"},
            {"name": "Old Town Market", "category": "Market", "notes": "Local crafts & street food"},
        ],
    )
    return {"query": query, "recommendations": recommendations}

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=9002)



