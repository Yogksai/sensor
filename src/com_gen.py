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

try:
    ser = serial.Serial('COM1', 115200)
except Exception as e:
    print(f"Ошибка порта: {e}")
    exit()

print("--- ЭМУЛЯТОР БАЛЛИСТИКИ (WIDE TRAJECTORY) ---")

# Физические константы для затяжного полета
g = 9.81
v0 = 120.0        # Начальная скорость (увеличил для долгого полета)
launch_angle = 65.0 # Угол пуска (градусы)
dt = 0.02          # Шаг 50Гц (20мс)

def run_simulation():
    t = 0.0
    start_lat, start_lon = 55.7558, 37.6173

    # Коэффициент масштаба для твоего графика (чтобы линия шла вправо)
    m_to_deg = 0.00015

    angle_rad = math.radians(launch_angle)

    while True:
        # Расчет скоростей
        vx = v0 * math.cos(angle_rad)
        vy = v0 * math.sin(angle_rad) - g * t

        # Расчет пройденного пути и высоты
        dist = vx * t
        alt = (v0 * math.sin(angle_rad) * t) - (0.5 * g * t**2)

        # Если упала — выходим из цикла симуляции для рестарта
        if alt < 0 and t > 1:
            print("\n[!] ПЕРЕЗАПУСК...")
            time.sleep(2)
            break

        # Углы: Pitch (тангаж) следует за вектором скорости
        curr_pitch = math.degrees(math.atan2(vy, vx))
        curr_roll = math.sin(t * 10) * 5.0 # Легкая болтанка
        curr_yaw = t * 0.5                # Медленный увод в сторону

        # Геопозиция
        lat = start_lat + (dist * m_to_deg)
        lon = start_lon + (dist * 0.3 * m_to_deg) # Небольшой наклон траектории

        qw, qx, qy, qz = euler_to_quat(curr_roll, curr_pitch, curr_yaw)

        # Формируем пакет данных (как в твоем парсере)
        test_data = (
            f"RP: R={curr_roll:.2f} P={curr_pitch:.2f} | err: 0\r\n"
            f"GPS: alt={alt:.1f}m spd={math.sqrt(vx**2 + vy**2):.1f}\r\n"
            f"     lat={lat:.7f} lon={lon:.7f}\r\n"
            f"IMU: quat=[{qw:.6f} {qx:.6f} {qy:.6f} {qz:.6f}]\r\n"
        )

        ser.write(test_data.encode('utf-8'))

        t += dt
        time.sleep(dt)

try:
    while True:
        run_simulation()
except KeyboardInterrupt:
    ser.close()
    print("Остановлено.")