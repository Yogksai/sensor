import sys
import threading
import os
from dotenv import load_dotenv

# Импортируем PyQt6 компоненты
from PyQt6.QtWidgets import QApplication

# Импортируем твои модули (убедись, что пути верны)
from src.config_launcher import LauncherWindow
from src import converter_bridge
from src.interface_app import FlightControlApp

def run_telemetry_logic():
    load_dotenv()
    selected_port = os.getenv("SERIAL_PORT")
    if not selected_port:
        print("[Ошибка]: Порт не указан в .env")
        return
    #"""Функция для запуска моста в отдельном потоке"""
    try:
        # Запускаем бесконечный цикл чтения, парсинга и рассылки UDP
        converter_bridge.run_converter(selected_port)
    except Exception as e:
        print(f"\n[Критическая ошибка моста]: {e}")

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    print("SYSTEM STARTUP")
    launcher = LauncherWindow()
    if launcher.exec() != LauncherWindow.DialogCode.Accepted:
        print("Запуск отменен пользователем.")
        sys.exit()
    load_dotenv(override=True)
    active_port = os.getenv("SERIAL_PORT")
    if not active_port:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Ошибка конфига",
                             "SERIAL_PORT не найден в .env. Запуск невозможен.")
        return
    model_name = os.getenv("MODEL_NAME", "Unknown Model")
    print(f"Настройки приняты. Порт: {active_port}, Модель: {model_name}")


    # 2. ШАГ: Запуск логики обработки данных (Serial -> Parser -> UDP)
    # Запускаем в фоне (daemon=True), чтобы поток закрылся вместе с программой
    data_thread = threading.Thread(
        target=run_telemetry_logic,
        daemon=True
    )
    data_thread.start()

    window = FlightControlApp()
    window.setWindowTitle(f"FCS - {model_name}") # Устанавливаем имя из конфига
    window.show()

    print("Система активна. Ожидание данных...")


    sys.exit(app.exec())

if __name__ == "__main__":
    main()