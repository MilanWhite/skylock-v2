import math
import board
import busio
from adafruit_lsm303dlh_mag import LSM303DLH_Mag
from adafruit_lsm303_accel import LSM303_Accel

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