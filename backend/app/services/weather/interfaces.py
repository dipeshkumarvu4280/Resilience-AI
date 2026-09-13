from abc import ABC, abstractmethod
from app.models.weather import WeatherEvidence


class WeatherProvider(ABC):
    """
    Abstract interface for external location-specific weather providers.
    Zero fabricated data; missing metrics must remain None.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def fetch_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> WeatherEvidence:
        """
        Fetches genuine weather observations and multi-horizon forecasts
        for specific incident coordinates.
        """
        pass
