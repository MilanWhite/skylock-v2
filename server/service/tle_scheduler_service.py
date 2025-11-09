import json
import threading
import time
from datetime import datetime, timedelta, timezone

from server.model.repository import ITleRepository
from server.service.connection_manager import IConnectionManager, ConnectionManager

class TleSchedulerService:
    def __init__(self, repo: ITleRepository, tle_group: str,
                 interval_seconds: int = 3600,
                 connection_manager = None):
        self.repo = repo
        self.tle_group = tle_group
        self.interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread = None
        self._last_fetch_time = None
        self._conn_manager = connection_manager or ConnectionManager()

    def _run(self):
        while not self._stop_event.is_set():
            now = datetime.now()
            # If never fetched or it's been more than interval, try to fetch
            if (self._last_fetch_time is None or
                (now - self._last_fetch_time) >= timedelta(seconds=self.interval)):
                try:
                    if self._conn_manager.is_available():
                        # Use TleRepositoryUtils for the high-level fetch and store operation
                        from server.model.repository import TleRepositoryUtils
                        TleRepositoryUtils.fetch_and_store_group(self.repo, self.tle_group, timeout=20)
                        self._last_fetch_time = datetime.now()
                    else:
                        status = self._conn_manager.get_connection_status()
                        print(f"[TleSchedulerService] No connection available. Status: {status}")
                except Exception as e:
                    print(f"[TleSchedulerService] Error in scheduler loop: {e}")
            # Sleep in short intervals to allow quick recovery after connection returns
            time.sleep(60)

    def _do_initial_fetch(self):
        """Performs initial data fetch when service starts."""
        print("[TleSchedulerService] Performing initial data fetch...")
        try:
            from server.model.repository import TleRepositoryUtils
            TleRepositoryUtils.fetch_and_store_group(self.repo, self.tle_group, timeout=20)
            self._last_fetch_time = datetime.now()
        except Exception as e:
            print(f"[TleSchedulerService] Warning: Could not fetch new data: {e}")
            print("[TleSchedulerService] Will use existing data from database")
            self._last_fetch_time = None  # Force a retry on next scheduler loop

    def start(self, initial_fetch=True):
        """Start the scheduler service.

        Args:
            initial_fetch (bool): If True, performs immediate data fetch
        """
        if self._thread is None or not self._thread.is_alive():
            # Do initial fetch if requested
            if initial_fetch:
                self._do_initial_fetch()

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            print("[TleSchedulerService] Scheduler started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            print("[TleSchedulerService] Scheduler stopped.")
