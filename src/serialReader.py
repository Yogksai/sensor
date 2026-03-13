import serial
import time

def get_serial_data(port_name, baudrate=115200):
    """
    Принимает выбранный порт (например, 'COM10') и начинает чтение.
    Работает как генератор (yield).
    """
    try:
        # Пытаемся открыть порт, который нам "прокинули"
        ser = serial.Serial(port_name, baudrate, timeout=0.1)
        print(f" Успешное подключение: {port_name} ")

        ser.reset_input_buffer()

        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        yield line
                except UnicodeDecodeError:
                    continue
            time.sleep(0.001)

    except serial.SerialException as e:
        print(f"Ошибка порта {port_name}: {e} ")
        yield ""
