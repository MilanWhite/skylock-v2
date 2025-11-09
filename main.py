from datetime import datetime, timezone
import json
import time

from server.model.repository import SqliteTleRepository
from server.service.satellite_service import Sgp4SatelliteService

def pretty_print_satellite(info: dict):
    if info is None:
        print("No satellite found (empty DB or all TLEs invalid).")
        return

    # Restrict printed fields for readability
    out = {
        "id": info.get("id"),
        "name": info.get("name"),
        "source": info.get("source"),
        "when_utc": info.get("when_utc"),
        "distance_km": info.get("distance_km"),
        "position_ecef_km": info.get("position_ecef_km"),
        "velocity_km_s": info.get("velocity_km_s"),
    }

    print(json.dumps(out, indent=2))


def main():
    # Example: UofT St. George campus (approx)
    lat_deg = 43.6625
    lon_deg = -79.3950
    alt_m = 100.0

    # Set up repository and services
    repo = SqliteTleRepository()
    service = Sgp4SatelliteService(repo)


    # Find nearest satellite
    when = datetime.now(timezone.utc)
    print(f"\nFinding nearest satellite to ({lat_deg}, {lon_deg}, {alt_m} m) at {when.isoformat()} UTC")
    nearest = service.find_nearest_satellite(lat_deg, lon_deg, alt_m, when=when)
    pretty_print_satellite(nearest)



if __name__ == "__main__":
    main()
