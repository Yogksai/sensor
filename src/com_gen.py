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

    print("--- SMOOTH ASCENT EMULATOR (10 min to 8km) ---")

    t = 0.0
    dt = 0.1 # Обновление 10 раз в секунду
    target_height = 8000.0
    target_time = 600.0 # 10 минут в секундах

    # Средняя вертикальная скорость должна быть ~13.3 м/с
    # Для плавности добавим небольшое ускорение в начале

    start_lat, start_lon = 55.7558, 37.6173

    try:
        while True:
            # Модель плавного подъема (квадратичная зависимость для разгона, потом линейная)
            if t < target_time:
                # Плавный набор высоты до 8000м
                alt = (target_height / (target_time**2)) * (t**2) if t < 60 else \
                    (13.3 * t) # упрощенно
                # Ограничим для реализма
                alt = min(alt, target_height + (t - target_time) * 0.5)
            else:
                alt = target_height + math.sin(t * 0.1) * 10 # Дрейф на эшелоне

            # Горизонтальное движение (медленное удаление)
            dist = 20.0 * t # Скорость 20 м/с вперед
            lat = start_lat + (dist * 0.000009)
            lon = start_lon + (dist * 0.000005)

            # Углы: медленный тангаж (Pitch) от 90 до 10 градусов
            curr_pitch = max(10, 90 - (t / target_time) * 80)
            curr_roll = math.sin(t * 0.5) * 2.0 # Легкое покачивание
            curr_yaw = (t * 0.2) % 360

            qw, qx, qy, qz = euler_to_quat(curr_roll, curr_pitch, curr_yaw)

            # Имитация работы рулей (вибрация от потока воздуха)
            s1 = 1.5 * math.sin(t * 5)
            s2 = 1.5 * math.cos(t * 5)
            s3, s4 = -s1, -s2

            report = (
                f"RP: R={curr_roll:.2f} P={curr_pitch:.2f} | err: Re=0.01 Pe=0.01 | u: Ur=0.0 Up=0.0\r\n"
                f"S(deg): S1={s1:.1f} S2={s2:.1f} S3={s3:.1f} S4={s4:.1f} | CCR: 1500 1500 1500 1500\r\n"
                f"GPS: fix=3 q=3 sats=12 hdop=0.8 alt={alt:.1f}m spd={25.0:.2f}m/s age=5ms\r\n"
                f"     lat={lat:.7f} lon={lon:.7f}\r\n"
                f"     date=14-03-2026 time=14:00:00\r\n"
                f"IMU: quat=[{qw:.6f} {qx:.6f} {qy:.6f} {qz:.6f}]\r\n"
            )

            ser.write(report.encode('utf-8'))

            if int(t) % 10 == 0 and t > 0:
                print(f"Status: Time={int(t)}s, Alt={alt:.1f}m, Pitch={curr_pitch:.1f}°")

            t += dt
            time.sleep(dt)

    except KeyboardInterrupt:
        print("\nEmulator stopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_smooth_emulator()