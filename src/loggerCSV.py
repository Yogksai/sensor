import csv
import os
from datetime import datetime

class TelemetryLogger:
    def __init__(self, folder="logs"):
        self.folder = folder
        self.file = None
        self.writer = None

        if not os.path.exists(self.folder):
            os.makedirs(self.folder)

    def start_logging(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.folder, f"raw_log_{timestamp}.csv")

        # newline='' важно для модуля csv, чтобы не было пустых строк
        self.file = open(filename, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)

        # Строка старта
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.writer.writerow([f"--- SESSION START: {start_time} ---"])

        # Заголовок
        self.writer.writerow(["Timestamp", "Raw_Data"])
        self.file.flush()
        print(f"Запись сырых логов: {filename}")

    def log_raw(self, raw_line):
        """Записывает сырую строку из порта"""
        if self.writer:
            curr_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            # Убираем лишние пробелы и переносы строк по краям
            clean_line = raw_line.strip()
            self.writer.writerow([curr_time, clean_line])
            self.file.flush()

    def stop_logging(self):
        if self.file:
            self.file.close()
            self.file = None
            print("Логирование завершено.")