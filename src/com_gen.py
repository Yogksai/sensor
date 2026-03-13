import serial
import time
import math

def euler_to_quat(roll, pitch, yaw):
    """Превращает углы Эйлера (градусы) в кватернион для IMU: quat=[w x y z]"""
    # Переводим в радианы
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)

    cy = math.cos(y * 0.5); sy = math.sin(y * 0.5)
    cp = math.cos(p * 0.5); sp = math.sin(p * 0.5)
    cr = math.cos(r * 0.5); sr = math.sin(r * 0.5)

    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y_val = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return w, x, y_val, z

# Настройка порта (пишем в COM1, main.py слушает COM2)
ser = serial.Serial('COM1', 115200)

print("Запущен ПЛАВНЫЙ эмулятор (50Hz)...")

t = 0.0
try:
    while True:
        # Рассчитываем плавные углы
        curr_roll  = math.sin(t * 1.5) * 15.0   # Покачивание влево-вправо
        curr_pitch = math.cos(t * 1.1) * 10.0   # Наклон вперед-назад
        curr_yaw   = (t * 20.0) % 360           # Плавный разворот

        # Генерируем правильный кватернион
        qw, qx, qy, qz = euler_to_quat(curr_roll, curr_pitch, curr_yaw)

        # Динамические GPS данные
        lat = 55.7558 + math.sin(t * 0.2) * 0.0005
        lon = 37.6173 + math.cos(t * 0.2) * 0.0005
        alt = 120.0 + math.sin(t) * 2.0

        # Формируем многострочный пакет
        test_data = (
            f"RP: R={curr_roll:.2f} P={curr_pitch:.2f} | err: Re=0.00 Pe=0.00 | u: Ur=0.0 Up=0.0\r\n"
            f"S(deg): S1=0.0 S2=0.0 S3=0.0 S4=0.0 | CCR: 0 0 0 0\r\n"
            f"GPS: fix=3 q=3 sats=12 hdop=0.8 alt={alt:.1f}m spd=0.05m/s age=1ms\r\n"
            f"     lat={lat:.7f} lon={lon:.7f}\r\n"
            f"     date=02-03-2026 time=12:00:00\r\n"
            f"IMU: quat=[{qw:.6f} {qx:.6f} {qy:.6f} {qz:.6f}]\r\n"
        )

        ser.write(test_data.encode('utf-8'))

        t += 0.02  # Шаг времени (соответствует 20мс)
        time.sleep(0.02) # 50 кадров в секунду

except KeyboardInterrupt:
    ser.close()
    print("\nЭмулятор остановлен.")