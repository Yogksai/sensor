import serial.tools.list_ports

def choose_active_port():
    print("\nВЫБОР ПОРТА ДЛЯ ПОДКЛЮЧЕНИЯ")

    # 1. Получаем список всех доступных COM-портов
    ports = serial.tools.list_ports.comports()

    if not ports:
        print("Порты не найдены. Проверь подключение и драйвера")
        return None

    # 2. Показываем список пользователю
    print("Доступные устройства:")
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")

    # 3. Даем выбрать
    try:
        idx = int(input("\nВведите номер порта: "))
        selected_name = ports[idx].device
        print(f"-> Выбран порт: {selected_name}")
        return selected_name
    except (ValueError, IndexError):
        print("Ошибка: введен неверный номер порта")
        return None

if __name__ == "__main__":
    target_port = choose_active_port()