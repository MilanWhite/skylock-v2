"""Service for determining satellite targeting and connection feasibility."""
import abc
import math

class ISatelliteTargetingService(abc.ABC):
    @abc.abstractmethod
    def can_connect(self,
                   ground_lat: float,
                   ground_lon: float,
                   ground_alt: float,
                   satellite_ecef: List[float],
                   current_azimuth_deg: float,
                   current_elevation_deg: float,
                   current_range_km: float,
                   max_range_km: float = 2000.0,
                   azimuth_tolerance_deg: float = 10.0,
                   elevation_tolerance_deg: float = 5.0,
                   range_tolerance_km: float = 100.0) -> bool:
        """
        Determines if a satellite connection is possible based on position alignment.

        Args:
            ground_lat: Ground station latitude in degrees
            ground_lon: Ground station longitude in degrees
            ground_alt: Ground station altitude in meters
            satellite_ecef: Satellite position in ECEF coordinates [x, y, z] (km)
            current_azimuth_deg: Current azimuth angle of the antenna in degrees (0-360)
            current_elevation_deg: Current elevation angle of the antenna in degrees
            current_range_km: Current range setting/estimate in kilometers
            max_range_km: Maximum range in kilometers for viable connection
            azimuth_tolerance_deg: Maximum allowed difference in azimuth
            elevation_tolerance_deg: Maximum allowed difference in elevation
            range_tolerance_km: Maximum allowed difference in range

        Returns:
            bool: True if connection is possible (within all tolerances)
        """
        pass

    @abc.abstractmethod
    def get_targeting_info(self,
                          ground_lat: float,
                          ground_lon: float,
                          ground_alt: float,
                          satellite_ecef,
                          current_azimuth_deg = None,
                          current_elevation_deg = None,
                          current_range_km = None):
        """
        Calculates targeting information for satellite connection.

        Args:
            ground_lat: Ground station latitude in degrees
            ground_lon: Ground station longitude in degrees
            ground_alt: Ground station altitude in meters
            satellite_ecef: Satellite position in ECEF coordinates [x, y, z] (km)
            current_azimuth_deg: Optional current azimuth angle in degrees
            current_elevation_deg: Optional current elevation angle in degrees
            current_range_km: Optional current range setting in kilometers

        Returns:
            Dict containing:
                - azimuth_deg: Target azimuth angle in degrees (0-360, 0=North, 90=East)
                - elevation_deg: Target elevation angle in degrees
                - range_km: Target slant range to satellite in km
                - azimuth_diff_deg: Difference from current azimuth (if provided)
                - elevation_diff_deg: Difference from current elevation (if provided)
                - range_diff_km: Difference from current range (if provided)
                - enu_vector: Satellite position in local ENU frame [e, n, u] (km)
        """
        pass


class SatelliteTargetingService(ISatelliteTargetingService):
    def __init__(self, max_range_km: float = 2000.0):
        """Initialize the targeting service.

        Args:
            max_range_km: Maximum range in kilometers for viable connection
        """
        self.max_range_km = max_range_km

    def can_connect(self,
                   ground_lat: float,
                   ground_lon: float,
                   ground_alt: float,
                   current_azimuth_deg: float,
                   current_elevation_deg: float,
                   current_range_km: float,
                   satellite_ecef,
                   max_range_km: float = 2000.0,
                   azimuth_tolerance_deg: float = 10.0,
                   elevation_tolerance_deg: float = 5.0,
                   range_tolerance_km: float = 100.0) -> bool:
        """Check if satellite connection is possible based on position alignment."""
        targeting_info = self.get_targeting_info(
            ground_lat, ground_lon, ground_alt, satellite_ecef,
            current_azimuth_deg, current_elevation_deg, current_range_km
        )

        # Check if satellite is beyond maximum range
        if targeting_info['range_km'] > max_range_km:
            return False

        # Check azimuth alignment
        if targeting_info['azimuth_diff_deg'] > azimuth_tolerance_deg:
            return False

        # Check elevation alignment
        if abs(targeting_info['elevation_diff_deg']) > elevation_tolerance_deg:
            return False

        # Check range alignment
        if abs(targeting_info['range_diff_km']) > range_tolerance_km:
            return False

        return True

    def get_targeting_info(self,
                          ground_lat: float,
                          ground_lon: float,
                          ground_alt: float,
                          satellite_ecef,
                          current_azimuth_deg = None,
                          current_elevation_deg = None,
                          current_range_km = None):
        """Calculate targeting information for the satellite."""
        # Convert ground station to ECEF
        from server.service.satellite_service import _geodetic_to_ecef
        ground_ecef = _geodetic_to_ecef(ground_lat, ground_lon, ground_alt)

        # Calculate relative vector in ECEF
        rel_vector = [
            satellite_ecef[0] - ground_ecef[0],
            satellite_ecef[1] - ground_ecef[1],
            satellite_ecef[2] - ground_ecef[2]
        ]

        # Convert to local ENU frame
        enu = self._ecef_to_enu(rel_vector, ground_lat, ground_lon)
        e, n, u = enu

        # Calculate range, elevation and azimuth
        range_km = math.sqrt(sum(x*x for x in rel_vector))
        horizontal_dist = math.sqrt(e*e + n*n)
        elevation_deg = math.degrees(math.atan2(u, horizontal_dist))
        azimuth_deg = self._calculate_azimuth(e, n)

        # Calculate differences if current values are provided
        result = {
            "azimuth_deg": azimuth_deg,
            "elevation_deg": elevation_deg,
            "range_km": range_km,
            "enu_vector": enu
        }

        if current_azimuth_deg is not None:
            azimuth_diff = abs(azimuth_deg - current_azimuth_deg)
            if azimuth_diff > 180:
                azimuth_diff = 360 - azimuth_diff
            result["azimuth_diff_deg"] = azimuth_diff

        if current_elevation_deg is not None:
            result["elevation_diff_deg"] = elevation_deg - current_elevation_deg

        if current_range_km is not None:
            result["range_diff_km"] = range_km - current_range_km

        return result

    def _ecef_to_enu(self,
                     ecef_vector,
                     lat_deg: float,
                     lon_deg: float):
        """Convert ECEF vector to local East-North-Up (ENU) frame.

        Args:
            ecef_vector: Vector in ECEF frame [x, y, z]
            lat_deg: Observer latitude in degrees
            lon_deg: Observer longitude in degrees

        Returns:
            Vector in ENU frame [east, north, up]
        """
        lat = math.radians(lat_deg)
        lon = math.radians(lon_deg)

        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        sin_lon = math.sin(lon)
        cos_lon = math.cos(lon)

        # ECEF to ENU transformation matrix
        # First rotate by longitude around z-axis
        # Then rotate by (90-latitude) around new y-axis

        # [e] = [-sin_lon           cos_lon          0     ] [x]
        # [n] = [-sin_lat*cos_lon  -sin_lat*sin_lon cos_lat] [y]
        # [u] = [ cos_lat*cos_lon   cos_lat*sin_lon sin_lat] [z]

        x, y, z = ecef_vector

        east = -sin_lon * x + cos_lon * y
        north = -sin_lat * cos_lon * x - sin_lat * sin_lon * y + cos_lat * z
        up = cos_lat * cos_lon * x + cos_lat * sin_lon * y + sin_lat * z

        return [east, north, up]

    def _calculate_azimuth(self, east: float, north: float) -> float:
        """Calculate azimuth angle from east and north components.

        Args:
            east: East component of the vector
            north: North component of the vector

        Returns:
            Azimuth angle in degrees (0-360, 0=North, 90=East)
        """
        azimuth_rad = math.atan2(east, north)
        azimuth_deg = math.degrees(azimuth_rad)
        if azimuth_deg < 0:
            azimuth_deg += 360
        return azimuth_deg