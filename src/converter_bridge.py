import socket
import math
import time
import os
from src.parser import TelemetryParser
from src.loggerCSV import TelemetryLogger
from src.serialReader import get_serial_data
from dotenv import load_dotenv


load_dotenv()
in_port = int(os.getenv("UI_PORT", 5006))
out_port = int(os.getenv("UNITY_PORT", 5005))
serial_port = os.getenv("SERIAL_PORT", "COM1")
UNITY_ADDR = ("127.0.0.1", out_port)
UI_ADDR    = ("127.0.0.1", in_port)

def quat_to_euler(x, y, z, w):
    # 1. Roll (Крен) - вращение вокруг оси X
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # 2. Pitch (Тангаж) - вращение вокруг оси Y
    sinp = 2.0 * (w * y - z * x)
    # Защита от ошибок области определения asin (-1.0 to 1.0)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # 3. Yaw (Рыскание) - вращение вокруг оси Z
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    # Переводим радианы в градусы для графиков PyQtGraph
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)

def run_converter(port_name):
    # Создаем сокет в контекстном менеджере, чтобы он закрылся сам
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        parser = TelemetryParser()
        print(f"BRIDGE STARTED ON {port_name}")

        try:
            # Если get_serial_data возвращает генератор,
            # нам нужно убедиться, что внутри него закрывается порт.
            for raw_text in get_serial_data(port_name):
                if not raw_text:
                    continue

                data = parser.parse(raw_text)
                if data:
                    r, p, y = quat_to_euler(*data['quat'])
                    lat, lon, alt = data.get('lat', 0), data.get('lon', 0), data.get('alt', 0)
                    s1, s2, s3, s4 = data.get('servos', [0, 0, 0, 0])

                    ui_payload = f"{r:.2f},{p:.2f},{y:.2f},{lat:.7f},{lon:.7f},{alt:.2f},{s1:.1f},{s2:.1f},{s3:.1f},{s4:.1f}"
                    print(f"Parsed: {ui_payload}")
                    sock.sendto(ui_payload.encode(), UI_ADDR)
        except Exception as e:
            print(f"Ошибка в цикле конвертера: {e}")
        finally:
            logger.stop_logging()
            # ВАЖНО: Если у тебя есть доступ к объекту serial внутри get_serial_data,
            # он должен закрываться там через try...finally.
            print("Конвертер остановлен, ресурсы освобождены.")

if __name__ == "__main__":
    run_converter()