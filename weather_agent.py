#----------------------FILE DESCRIPTION----------------------#
# THIS PROGRAM IMPLEMENTS AN AI AGENT VIA ANTHROPIC FRAMEWORK
# RETRIEVES WEATHER REPORT FOR GIVEN CITY
#--------------------------CHANGES---------------------------#
#----DATE----NAME------------CHANGES MADE--------------------#
# 9/03/2025 J. LICURSE








import os, requests, json
from typing import List, Dict, Any
from anthropic import Anthropic

#connect to claude
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

#Define a tool Calude can call
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather and up to 7 day forecast using Open-Meteo",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": { "type": "string", "description": "City, state or city, country (e.g., 'New Paltz, NY'"},
                "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 1},
                "units": {"type": "string", "enum": ["metric", "imperial"], "default": "imperial"}
            },
            "required": ["location"]
        },
    }
]

def geocode(location: str) -> Dict[str, Any]:
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout = 15
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        raise ValueError(f"Could not geocode '{location}'. Try a more specific query.")
    top = data["results"][0]
    return {
        "name": top.get("name"),
        "lat": top["latitude"],
        "lon": top["longitude"],
        "admin1": top.get("admin1"),
        "country": top.get("country")
    }

def fetch_weather(location: str, days: int = 1, units: str ="imperial") -> Dict[str, Any]:
    g = geocode(location)
    params = {
        "latitude": g["lat"],
        "longitude": g["lon"],
        "current_weather": True,
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "weathercode"],
        "timezone": "auto",
        "forecast_days": days
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    def c_to_f(c): return None if c is None else round((c * 9/5) + 32, 1)

    current = data.get("current_weather", {})
    daily = data.get("daily", {})
    place = ", ".join(x for x in [g["name"], g.get("admin1"), g.get("country")] if x)

    if units == "imperial":
        current_temp = c_to_f(current.get("temperature"))
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
    else:
        current_temp = current.get("temperature")
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])

    result = {
        "place": place,
        "latitude": g["lat"],
        "longitude": g["lon"],
        "units": units,
        "current": {
            "temperature": current_temp,
            "windspeed_kmh": current.get("windspeed"),
            "winddirection_deg": current.get("winddirection"),
            "weathercode": current.get("weathercode"),
            "time": current.get("time"),
        },
        "daily": [
            {
                "date": daily.get("time", [])[i],
                "tmax": tmax[i] if i < len(tmax) else None,
                "tmin": tmin[i] if i < len(tmin) else None,
                "precip_mm": daily.get("precipitation_sum", [None])[i],
                "weathercode": daily.get("weathercode", [None])[i],
            }
            for i in range(min(days, len(daily.get("time", []))))
        ]
    }
    return result

def call_tool(name: str, tool_input: dict):
    if name == "get_weather":
        return fetch_weather(
            tool_input["location"],
            tool_input.get("days", 1),
            tool_input.get("units", "imperial")
        )
    raise ValueError(f"No such tool: {name}")

def ask_agent(user_query: str) -> str:
    messages = [{"role": "user", "content": user_query}]
    resp = client.messages.create(
        model = "claude-opus-4-1-20250805",
        max_tokens=800,
        tools=tools,
        messages=messages
    )

    tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

    if not tool_uses:
        text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(text_parts).strip()

    tool_results_blocks : List[Dict[str, Any]] = []
    for tu in tool_uses:
        output = call_tool(tu.name, tu.input)
        tool_results_blocks.append({
            "type": "tool_result",
            "tool_use_id": tu.id,
            "content": [{"type": "text", "text": json.dumps(output)}]
        })
    messages.extend([
        {"role": "assistant", "content": resp.content},
        {"role": "user", "content": tool_results_blocks},
    ])

    final = client.messages.create(
        model = "claude-opus-4-1-20250805",
        max_tokens=800,
        tools=tools,
        messages=messages
    )

    text_parts = [b.text for b in final.content if getattr(b, "type", None) == "text"]
    return "\n".join(text_parts).strip()

if __name__ == "__main__":
    try:
        question = input("Ask your weather agent (e.g., '3-day forecast for New Paltz, NY'): ")
        print(ask_agent(question))
    except Exception as e:
        print("Error:", e)

