"""Weather from Open-Meteo (free, no API key)."""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from datetime import date

import certifi

# python.org builds on macOS ship without root certificates; use certifi's bundle.
_SSL = ssl.create_default_context(cafile=certifi.where())

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "violent showers", 95: "thunderstorm",
}


def forecast(lat: float, lon: float, day: str) -> dict:
    """Daily summary plus hourly temperature and rain chance for one day (°F, mph)."""
    try:
        params = {
            "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,wind_speed_10m_max",
                "hourly": "temperature_2m,apparent_temperature,precipitation_probability",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "start_date": day,
                "end_date": day,
        }
        with urllib.request.urlopen(f"{FORECAST_URL}?{urllib.parse.urlencode(params)}", timeout=10, context=_SSL) as r:
            data = json.loads(r.read())
    except Exception as e:
        return _seasonal_estimate(day, f"live forecast unavailable ({type(e).__name__})")

    d = data["daily"]
    h = data["hourly"]
    hourly = [
        {"hour": t[11:16], "temp_f": round(temp), "feels_like_f": round(feel), "rain_pct": rain}
        for t, temp, feel, rain in zip(h["time"], h["temperature_2m"], h["apparent_temperature"], h["precipitation_probability"])
        if 6 <= int(t[11:13]) <= 22 and int(t[11:13]) % 2 == 0
    ]
    return {
        "date": day,
        "source": "Open-Meteo forecast",
        "summary": CODES.get(d["weather_code"][0], "mixed"),
        "high_f": round(d["temperature_2m_max"][0]),
        "low_f": round(d["temperature_2m_min"][0]),
        "rain_chance_pct": d["precipitation_probability_max"][0],
        "wind_mph": round(d["wind_speed_10m_max"][0]),
        "hourly": hourly,
    }


def _seasonal_estimate(day: str, why: str) -> dict:
    """Fallback so the planner still works offline: rough New England monthly normals."""
    month = date.fromisoformat(day).month
    normals = {1: (37, 22), 2: (40, 24), 3: (48, 31), 4: (59, 40), 5: (69, 50), 6: (78, 59),
               7: (84, 65), 8: (82, 64), 9: (75, 56), 10: (64, 45), 11: (53, 36), 12: (42, 27)}
    hi, lo = normals[month]
    return {"date": day, "source": f"seasonal estimate ({why})", "summary": "typical for the season",
            "high_f": hi, "low_f": lo, "rain_chance_pct": None, "wind_mph": None, "hourly": []}


def season_for(day: str, lat: float = 41.3) -> str:
    m = date.fromisoformat(day).month
    north = lat >= 0
    seasons = ["winter", "winter", "spring", "spring", "spring", "summer", "summer", "summer", "fall", "fall", "fall", "winter"]
    s = seasons[m - 1]
    if not north:
        s = {"winter": "summer", "summer": "winter", "spring": "fall", "fall": "spring"}[s]
    return s
