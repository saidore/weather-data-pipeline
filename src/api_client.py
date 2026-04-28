# api_client.py
# Author: Sai Dore 
import requests  # Make HTTP requests to the API

class OpenMeteoClient:
    """Simple client for requesting historical weather data from Open-Meteo."""

    def __init__(self, base_url: str = "https://archive-api.open-meteo.com/v1/archive"):
        """Store the base API URL once when the client is created."""
        self.base_url = base_url

    def get_weather_data(self, latitude: float, longitude: float, start_date: str, end_date: str,
        hourly_vars: list[str] | None = None, daily_vars: list[str] | None = None, timezone: str = "auto") -> dict:
        """Request historical weather data for one location and date range."""

        # Start with parameters required by the API
        params = {"latitude": latitude, "longitude": longitude, "start_date": start_date, "end_date": end_date, "timezone": timezone}

        if hourly_vars: # Add hourly variables only if the user supplied them
            params["hourly"] = ",".join(hourly_vars)
        if daily_vars:   # Add daily variables only if the user supplied them
            params["daily"] = ",".join(daily_vars)
        # Make sure at least one variable group was requested
        if not hourly_vars and not daily_vars:
            raise ValueError("At least one of hourly_vars or daily_vars must be provided.")

        try:
            response = requests.get(self.base_url, params=params, timeout=30)  # Send GET request to the API
            response.raise_for_status()            # Raise error if status code is 4xx or 5xx
            return response.json()             # Convert API response into Python dictionary

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Open-Meteo API request failed: {exc}") from exc   # Raise an error message for the pipeline

if __name__ == "__main__":
    # Example run for quick testing
    client = OpenMeteoClient()
    sample_data = client.get_weather_data(
        latitude=35.9940,
        longitude=-78.8986,
        start_date="2023-01-01",
        end_date="2023-01-07",
        hourly_vars=["temperature_2m", "precipitation"],
        daily_vars=["temperature_2m_max", "temperature_2m_min"],
        timezone="America/New_York",
    )
    # Print top-level keys so you can confirm the response structure
    print("Returned keys:", sample_data.keys())