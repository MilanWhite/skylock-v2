"""Network connectivity interface and implementations for satellite data services."""
import abc
import requests
import time


class IConnectionManager(abc.ABC):
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if any connection method is available."""
        pass

    @abc.abstractmethod
    def get_connection_status(self):
        """Get detailed status of all connection methods."""
        pass

    @abc.abstractmethod
    def fetch_url(self, url: str, params = None, timeout: int = 20) -> str:
        """Fetch data from URL using best available connection method."""
        pass


class ConnectionStrategy(abc.ABC):
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if this connection method is available."""
        pass

    @abc.abstractmethod
    def get_status(self):
        """Get detailed status for this connection method."""
        pass

    @abc.abstractmethod
    def fetch_url(self, url: str, params = None, timeout: int = 20):
        """Try to fetch URL using this connection method. Returns None if fails."""
        pass


class WifiStrategy(ConnectionStrategy):
    def __init__(self, test_url: str = "https://celestrak.org"):
        self.test_url = test_url
        self._last_check_time = 0
        self._check_interval = 5  # seconds between availability checks

    def is_available(self) -> bool:
        now = time.time()
        if now - self._last_check_time < self._check_interval:
            return self._last_status

        try:
            requests.get(self.test_url, timeout=5)
            self._last_status = True
        except Exception:
            self._last_status = False

        self._last_check_time = now
        return self._last_status

    def get_status(self):
        return {
            "type": "wifi",
            "available": self.is_available(),
            "last_check": self._last_check_time
        }

    def fetch_url(self, url: str, params = None, timeout: int = 20):
        if not self.is_available():
            return None

        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception:
            return None


# Add more strategies here, e.g.:
# - CellularStrategy for mobile data
# - SatelliteModemStrategy for direct satellite comms
# - RadioStrategy for amateur radio data


class ConnectionManager(IConnectionManager):
    def __init__(self, strategies = None):
        self.strategies = strategies or [WifiStrategy()]

    def is_available(self) -> bool:
        return any(s.is_available() for s in self.strategies)

    def get_connection_status(self):
        return {
            "any_available": self.is_available(),
            "strategies": [s.get_status() for s in self.strategies]
        }

    def fetch_url(self, url: str, params = None, timeout: int = 20) -> str:
        """Try each strategy in order until successful."""
        errors = []

        for strategy in self.strategies:
            if not strategy.is_available():
                continue

            result = strategy.fetch_url(url, params, timeout)
            if result is not None:
                return result

            errors.append(f"{strategy.__class__.__name__} failed to fetch")

        raise ConnectionError(
            f"All connection strategies failed: {', '.join(errors)}"
        )