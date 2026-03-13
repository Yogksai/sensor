import serial
import time
import math
import random

def euler_to_quat(roll, pitch, yaw):
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
    cy, sy = math.cos(y * 0.5), math.sin(y * 0.5)
    cp, sp = math.cos(p * 0.5), math.sin(p * 0.5)
    cr, sr = math.cos(r * 0.5), math.sin(r * 0.5)
    return (cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * sp * sy,
            cr * cp * sy - sr * sp * cy)

try:
    ser = serial.Serial('COM1', 115200)
except:
    print("Ошибка: COM1 не найден"); exit()

def run():
    t = 0.0
    start_lat, start_lon = 55.7558, 37.6173
    v0, angle = 400.0, math.radians(83.0)

    while True:
        vx = v0 * math.cos(angle)
        vy = v0 * math.sin(angle) - 9.81 * t
        dist = vx * t
        alt = (v0 * math.sin(angle) * t) - (0.5 * 9.81 * t**2)

        if alt < 0 and t > 2:
            ser.write(b"alt=0.0m lat=55.7558 lon=37.6173\n")
            time.sleep(2); break

        lat = start_lat + (dist * 0.00012)
        lon = start_lon + (dist * 0.00004)
        qw, qx, qy, qz = euler_to_quat(math.sin(t)*5, math.degrees(math.atan2(vy, vx)), (t*2)%360)

        # Формат под твой TelemetryParser
        data = f"GPS: alt={alt:.2f}m lat={lat:.7f} lon={lon:.7f}\nIMU: quat=[{qw:.4f} {qx:.4f} {qy:.4f} {qz:.4f}]\n"
        ser.write(data.encode())
        t += 0.02
        time.sleep(0.02)

if __name__ == "__main__":
    while True: run()