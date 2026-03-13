import time
import random
from datetime import datetime

def generate_telemetry():
    # Имитация данных
    lat, lon, alt = 55.7558, 37.6173, 150.5
    q = [0.707, 0.0, 0.707, 0.0] # Пример кватерниона

    while True:
        now = datetime.utcnow()
        # Немного шума в данные
        alt += random.uniform(-0.1, 0.1)
        q = [round(x + random.uniform(-0.01, 0.01), 6) for x in q]

        report = (
            f"RP: R=0.00 P=0.00 | err: Re=0.00 Pe=0.00 | u: Ur=0.00 Up=0.00\r\n"
            f"S(deg): S1=0 S2=0 S3=0 S4=0 | CCR: 1000 1000 1000 1000\r\n"
            f"GPS: fix=1 q=3 sats=NA hdop=NA alt={alt:.1f}m spd=0.00m/s age=0ms\r\n"
            f"     lat={lat:.7f} lon={lon:.7f}\r\n"
            f"     date={now.day:02d}-{now.month:02d}-{now.year:04d} time={now.hour:02d}:{now.minute:02d}:{now.second:02d}\r\n"
            f"IMU: quat=[{q[0]:.6f} {q[1]:.6f} {q[2]:.6f} {q[3]:.6f}]\r\n"
        )
        yield report
        time.sleep(1)

if __name__ == "__main__":
    for data in generate_telemetry():
        print(data)