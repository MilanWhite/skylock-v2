from datetime import datetime, timezone
import abc

from server.model.connect import get_db_connection
from server.service.connection_manager import IConnectionManager, ConnectionManager


CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"
UPSERT_SQL = '''
INSERT INTO tles (name, line1, line2, source, fetched_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(name, line1, line2) DO UPDATE SET
    source=excluded.source,
    fetched_at=excluded.source;
'''


# OOP interface for TLE repository
class ITleRepository(abc.ABC):
    @abc.abstractmethod
    def fetch_all_tles(self):
        pass

    @abc.abstractmethod
    def fetch_satellite_by_id(self, satellite_id: int):
        """Fetch a specific satellite's TLE data by its ID.

        Args:
            satellite_id: The ID of the satellite to fetch.

        Returns:
            A dictionary containing the satellite's data if found, None otherwise.
            The dictionary includes: id, name, line1, line2, source, and fetched_at.
        """
        pass

    @abc.abstractmethod
    def upsert_tles(self, tles, source: str):
        pass

    @abc.abstractmethod
    def fetch_tle_group(self, group: str, timeout=20) -> str:
        pass

    @abc.abstractmethod
    def parse_tles(self, text: str):
        pass


# Concrete implementation using SQLite
class SqliteTleRepository(ITleRepository):
    def __init__(self, conn=None, connection_manager = None):
        self._external_conn = conn
        self._conn_manager = connection_manager or ConnectionManager()

    def _get_conn(self):
        if self._external_conn is not None:
            return self._external_conn, False
        return get_db_connection(), True

    def fetch_satellite_by_id(self, satellite_id: int):
        """Fetch a specific satellite's TLE data by its ID.

        Args:
            satellite_id: The ID of the satellite to fetch.

        Returns:
            A dictionary containing the satellite's data if found, None otherwise.
        """
        conn, close_conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, line1, line2, source, fetched_at FROM tles WHERE id = ?",
                (satellite_id,)
            )
            row = cur.fetchone()
            if row is None:
                return None

            return {
                "id": row[0],
                "name": row[1],
                "line1": row[2],
                "line2": row[3],
                "source": row[4],
                "fetched_at": row[5],
            }
        except Exception as e:
            print(f"Error in fetch_satellite_by_id: {e}")
            return None
        finally:
            if close_conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def fetch_all_tles(self):
        conn, close_conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, line1, line2, source, fetched_at FROM tles"
            )
            rows = cur.fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "name": row[1],
                    "line1": row[2],
                    "line2": row[3],
                    "source": row[4],
                    "fetched_at": row[5],
                })
            return results
        except Exception as e:
            print(f"Error in fetch_all_tles: {e}")
            return []
        finally:
            if close_conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def upsert_tles(self, tles, source: str):
        conn, close_conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        try:
            cur = conn.cursor()
            data_to_insert = [
                (name, l1, l2, source, now) for name, l1, l2 in tles
            ]
            cur.executemany(UPSERT_SQL, data_to_insert)
            conn.commit()
        except Exception as e:
            print(f"Error in upsert_tles: {e}")
        finally:
            if close_conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def fetch_tle_group(self, group: str, timeout=20) -> str:
        params = { 'GROUP': group, 'FORMAT': 'tle' }
        return self._conn_manager.fetch_url(CELESTRAK_URL, params=params, timeout=timeout)

    def parse_tles(self, text: str):
        lines = [l.rstrip('\n') for l in text.splitlines() if l.strip() != '']
        tles = []
        i = 0
        while i < len(lines) - 1:
            if lines[i].startswith('1 ') and i >= 1:
                name = lines[i-1]
                line1 = lines[i]
                line2 = lines[i+1] if (i+1) < len(lines) else ''
                tles.append((name, line1, line2))
                i += 2
            else:
                if i + 2 < len(lines):
                    name = lines[i]
                    line1 = lines[i+1]
                    line2 = lines[i+2]
                    if line1.startswith('1 ') and line2.startswith('2 '):
                        tles.append((name, line1, line2))
                        i += 3
                    else:
                        i += 1
                else:
                    break
        return tles


class TleRepositoryUtils:
    @staticmethod
    def fetch_and_store_group(repo: ITleRepository, group: str, timeout: int):
        """High-level function: fetches, parses, and stores TLEs for a single group using a repository instance."""

        # MARK: uncomment later when demo to prevent rate limit from celestrak


        # source_name = f'celestrak:{group}'
        # print(f'Fetching group: {group}')

        # # 1. Fetch
        # text = repo.fetch_tle_group(group, timeout=timeout)
        # # 2. Parse
        # tles = repo.parse_tles(text)
        # print(f'  parsed {len(tles)} TLE entries from group {group}')
        # # 3. Store
        # repo.upsert_tles(tles, source=source_name)
        # print(f'  Successfully stored group {group} in the database.')