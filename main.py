from datetime import datetime, timezone
import json
import time
import math

from server.model.repository import SqliteTleRepository
from server.service.satellite_service import Sgp4SatelliteService

import board
import busio
from adafruit_lsm303dlh_mag import LSM303DLH_Mag
from adafruit_lsm303_accel import LSM303_Accel

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

def get_heading(use_tilt_compensation=False):

    i2c = busio.I2C(board.SCL, board.SDA)

    # Initialize magnetometer and accelerometer
    mag = LSM303DLH_Mag(i2c)
    accel = LSM303_Accel(i2c)


    #mag field
    mag_x, mag_y, mag_z = mag.magnetic

    # mag_x -= cal_offset_x
    # mag_y -= cal_offset_y
    # mag_z -= cal_offset_z

    mag_x, mag_y, mag_z = (mag_x, mag_y, mag_z)

    if use_tilt_compensation:
        # Get accelerometer data for tilt compensation
        accel_x, accel_y, accel_z = accel.acceleration

        # Calculate roll and pitch
        roll = math.atan2(accel_y, accel_z)
        pitch = math.atan2(-accel_x, math.sqrt(accel_y**2 + accel_z**2))

        # Tilt compensated magnetic field
        mag_x_comp = mag_x * math.cos(pitch) + mag_z * math.sin(pitch)
        mag_y_comp = (mag_x * math.sin(roll) * math.sin(pitch) +
                        mag_y * math.cos(roll) -
                        mag_z * math.sin(roll) * math.cos(pitch))

        heading = math.atan2(mag_y_comp, mag_x_comp)
    else:
        # Simple heading calculation (sensor must be level)
        heading = math.atan2(mag_y, mag_x)

    # Convert to degrees
    heading_degrees = math.degrees(heading)

    # Normalize to 0-360
    if heading_degrees < 0:
        heading_degrees += 360

    return heading_degrees


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


    print(get_heading())



if __name__ == "__main__":
    main()
