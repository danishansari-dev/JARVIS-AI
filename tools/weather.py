import requests
from pydantic import BaseModel
from tools.registry import ToolRegistry

class WeatherInput(BaseModel):
    city: str

def _get_weather(data: WeatherInput) -> str:
    city = data.city
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_resp = requests.get(geo_url).json()
        if not geo_resp.get("results"):
            return f"Weather unavailable for {city} (location not found)"
        
        lat = geo_resp["results"][0]["latitude"]
        lon = geo_resp["results"][0]["longitude"]
        
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=relativehumidity_2m"
        weather_resp = requests.get(weather_url).json()
        
        current = weather_resp.get("current_weather", {})
        temp = current.get("temperature", "?")
        code = current.get("weathercode", -1)
        
        hourly = weather_resp.get("hourly", {})
        humidities = hourly.get("relativehumidity_2m", [])
        humidity = humidities[0] if humidities else "?"
        
        weather_map = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog", 51: "Light drizzle",
            53: "Moderate drizzle", 55: "Dense drizzle", 61: "Light rain",
            63: "Moderate rain", 65: "Heavy rain", 71: "Light snow",
            73: "Moderate snow", 75: "Heavy snow", 80: "Rain showers",
            81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with light hail",
            99: "Thunderstorm with heavy hail"
        }
        
        desc = weather_map.get(code, "Unknown conditions")
        
        return f"{city}: {temp}°C, {desc}, humidity {humidity}%"
    except Exception:
        return f"Weather unavailable for {city}"

def register_weather_tools(registry: ToolRegistry) -> None:
    registry.register(
        name="get_weather",
        description="Get current weather details for a city.",
        input_schema=WeatherInput,
        handler=_get_weather,
    )
