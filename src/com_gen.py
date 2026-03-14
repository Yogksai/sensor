import serial
import time
import math

def euler_to_quat(roll, pitch, yaw):
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
    cy, sy = math.cos(y * 0.5), math.sin(y * 0.5)
    cp, sp = math.cos(p * 0.5), math.sin(p * 0.5)
    cr, sr = math.cos(r * 0.5), math.sin(r * 0.5)
    return (cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy)

def run_smooth_emulator():
    try:
        ser = serial.Serial('COM1', 115200, timeout=1)
    except Exception as e:
        print(f"Ошибка порта: {e}")
        return

    print("--- 3-PHASE MISSION EMULATOR ---")

    t = 0.0
    dt = 0.1
    start_lat, start_lon = 55.7558, 37.6173

    try:
        while True:
            # --- ЭТАП 1: ВЗЛЕТ (0-60 сек) ---
            if t <= 60:
                alt = (8000.0 / 60.0) * t
                curr_pitch = 90 - (t / 60.0) * 45  # Уходит в наклон

            # --- ЭТАП 2: КОРРЕКТИРОВКА (60-70 сек) ---
            elif t <= 70:
                t_adj = t - 60
                # Колебания 8000-7000 (амплитуда 500 вокруг 7500)
                alt = 7500.0 + math.cos(t_adj * 0.6) * 500.0
                curr_pitch = 45.0 + math.sin(t_adj * 2) * 5.0

            # --- ЭТАП 3: СПУСК (70-130 сек) ---
            elif t <= 130:
                t_desc = t - 70
                alt = max(0, 8000.0 - (t_desc / 60.0) * 8000.0)
                curr_pitch = -45.0 # Нос вниз

            else:
                print("\n[!] ПЕРЕЗАПУСК ЦИКЛА...")
                t = 0; continue

            # Общая динамика
            dist = 50.0 * t
            lat = start_lat + (dist * 0.000009)
            lon = start_lon + (dist * 0.000005)
            curr_roll = math.sin(t * 0.5) * 2.0
            curr_yaw = (t * 0.2) % 360

            qw, qx, qy, qz = euler_to_quat(curr_roll, curr_pitch, curr_yaw)

            # Работа рулей
            s1 = 2.0 * math.sin(t * 10) if 60 < t < 70 else 0.5 * math.sin(t * 5)
            s2, s3, s4 = s1, -s1, -s1

            report = (
                f"RP: R={curr_roll:.2f} P={curr_pitch:.2f} | err: Re=0.01 Pe=0.01\r\n"
                f"S(deg): S1={s1:.1f} S2={s2:.1f} S3={s3:.1f} S4={s4:.1f} | CCR: 1500 1500 1500 1500\r\n"
                f"GPS: fix=3 q=3 sats=12 hdop=0.8 alt={alt:.1f}m spd={50.0:.2f}m/s\r\n"
                f"     lat={lat:.7f} lon={lon:.7f}\r\n"
                f"IMU: quat=[{qw:.6f} {qx:.6f} {qy:.6f} {qz:.6f}]\r\n"
            )

            ser.write(report.encode('utf-8'))

            if int(t * 10) % 20 == 0:
                print(f"T={t:.1f}s | Alt={alt:.1f}m | Pitch={curr_pitch:.1f}°")

            t += dt
            time.sleep(dt)

    except KeyboardInterrupt:
        print("\nEmulator stopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_smooth_emulator()