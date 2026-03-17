import serial
import time
import math
import random

def run_precision_room_emulator():
    # Укажи свой порт (например, 'COM1' или '/dev/ttyUSB0')
    port = 'COM1'
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except Exception as e:
        print(f"Ошибка порта {port}: {e}")
        return

    print("--- PRECISION ROOM EMULATOR (10m x 1m) ---")
    print("Диапазон: 10 метров по горизонтали, 0-1 метр по высоте.")

    t = 0.0
    dt = 0.1  # Обновление 10 раз в секунду

    # Стартовая точка (центр комнаты)
    start_lat, start_lon = 43.238949, 76.889709

    # Коэффициенты перевода метров в градусы
    M_TO_DEG_LAT = 0.00000898
    M_TO_DEG_LON = M_TO_DEG_LAT / math.cos(math.radians(start_lat))

    try:
        while True:
            # 1. ДВИЖЕНИЕ ПО ПОЛУ (10 метров)
            # Моделька ходит "восьмеркой" в пределах +/- 5 метров
            dist_x = 5.0 * math.sin(t * 0.5)
            dist_y = 5.0 * math.sin(t * 0.25)

            # 2. ВЫСОТА (0.0 - 1.0 метр)
            # Плавно поднимается и опускается
            alt = 0.5 + 0.45 * math.sin(t * 0.8)

            # Итоговые координаты
            lat = start_lat + (dist_x * M_TO_DEG_LAT)
            lon = start_lon + (dist_y * M_TO_DEG_LON)

            # 3. УГЛЫ (Имитация покачивания)
            curr_pitch = 2.0 * math.sin(t * 0.5)
            curr_roll = 2.0 * math.cos(t * 0.5)
            curr_yaw = (t * 10.0) % 360

            # 4. РУЛИ (Вибрация для проверки графиков Analyze)
            s1 = 5.0 * math.sin(t * 15.0)

            # 5. СБОРКА И ОТПРАВКА
            # Формат соответствует твоему парсеру в UDPBridge
            report = (
                f"RP: R={curr_roll:.2f} P={curr_pitch:.2f} | err: Re=0.00 Pe=0.00\r\n"
                f"S(deg): S1={s1:.1f} S2={-s1:.1f} S3={s1:.1f} S4={-s1:.1f} | CCR: 1500 1500 1500 1500\r\n"
                f"GPS: fix=3 q=3 sats=18 hdop=0.6 alt={alt:.2f}m spd=0.20m/s\r\n"
                f"     lat={lat:.7f} lon={lon:.7f}\r\n"
                f"IMU: quat=[1.000000 0.000000 0.000000 0.000000]\r\n"
            )

            ser.write(report.encode('utf-8'))

            if int(t * 10) % 50 == 0:
                print(f"T={t:.1f}s | Alt={alt:.2f}m | Dist_X={dist_x:.1f}m")

            t += dt
            time.sleep(dt)

    except KeyboardInterrupt:
        print("\nEmulator stopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    run_precision_room_emulator()