import sys
import socket
import subprocess
import time
import win32gui
import win32con
import os
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QGridLayout, QWidget, QLabel
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont
import pyqtgraph as pg
from dotenv import load_dotenv
import sys

# --- ОБНОВЛЕННЫЙ ПОТОК ПРИЕМА И РЕЛЕЙ ---
class UDPBridge(QThread):
    angles_received = pyqtSignal(list)
    gps_received = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._run_flag = True # Флаг для безопасной остановки

    def stop(self):
        self._run_flag = False

    def run(self):
        load_dotenv()

        # Безопасное получение портов
        try:
            in_port = int(os.getenv("UI_PORT", "5006"))
        except (ValueError, TypeError):
            in_port = 5006

        try:
            out_port = int(os.getenv("UNITY_PORT", "5005"))
        except (ValueError, TypeError):
            out_port = 5005

        # Дальше создание сокетов...
        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.bind(('127.0.0.1', in_port))

        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.bind(('127.0.0.1', in_port))
        in_sock.settimeout(1.0) # Чтобы цикл не вис на recvfrom

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unity_addr = ('127.0.0.1', out_port)

        while self._run_flag:
            try:
                data, _ = in_sock.recvfrom(1024)
                line = data.decode('utf-8').strip()
                parts = [float(x) for x in line.split(',')]
                if len(parts) >= 6:
                    # Релей в Unity
                    out_sock.sendto(f"{parts[0]:.2f},{parts[1]:.2f},{parts[2]:.2f}".encode(), unity_addr)
                    self.angles_received.emit(parts[0:3])
                    self.gps_received.emit(parts[3:6])
            except socket.timeout:
                continue
            except Exception:
                continue

# --- ОСТАЛЬНАЯ ЛОГИКА ИНТЕРФЕЙСА (БЕЗ ИЗМЕНЕНИЙ) ---
class FlightControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FCS - 6DOF Telemetry Monitor")
        self.resize(1400, 900)
        self.max_points = 100
        self.buffer = {'r': np.zeros(self.max_points), 'p': np.zeros(self.max_points), 'y': np.zeros(self.max_points)}

        central_widget = QWidget()
        self.layout = QGridLayout(central_widget)
        self.setCentralWidget(central_widget)

        # Индикаторы
        self.ind_lat = self.create_indicator("ШИРОТА (LAT)", "#FF0000")
        self.ind_lon = self.create_indicator("ДОЛГОТА (LON)", "#008000")
        self.ind_alt = self.create_indicator("ВЫСОТА (ALT)", "#0000FF")
        self.layout.addWidget(self.ind_lat, 0, 0); self.layout.addWidget(self.ind_lon, 0, 1); self.layout.addWidget(self.ind_alt, 0, 2)

        # Графики
        self.pw_r, self.curve_r = self.create_plot("ROLL", 'r')
        self.pw_p, self.curve_p = self.create_plot("PITCH", 'g')
        self.pw_y, self.curve_y = self.create_plot("YAW", 'b')
        self.layout.addWidget(self.pw_r, 1, 0); self.layout.addWidget(self.pw_p, 2, 0); self.layout.addWidget(self.pw_y, 3, 0)

        # Unity
        self.exe_container = QWidget()
        self.exe_container.setMinimumWidth(800)
        self.exe_container.setStyleSheet("background-color: black; border: 2px solid #333;")
        self.layout.addWidget(self.exe_container, 1, 1, 3, 2)

        self.udp_thread = UDPBridge()
        self.udp_thread.angles_received.connect(self.update_graphs)
        self.udp_thread.gps_received.connect(self.update_labels)
        self.udp_thread.start()

        self.unity_hwnd = None
        QTimer.singleShot(2000, self.launch_exe)

    def create_indicator(self, label_text, color):
        container = QWidget(); l_layout = QGridLayout(container)
        val_lbl = QLabel("0.000000"); val_lbl.setFont(QFont("Consolas", 20, QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {color}; background-color: #222; padding: 10px; border-radius: 5px;")
        l_layout.addWidget(QLabel(label_text), 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        l_layout.addWidget(val_lbl, 1, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        container.value_label = val_lbl
        return container

    def create_plot(self, title, color):
        pw = pg.PlotWidget(title=title); pw.setBackground('w')
        return pw, pw.plot(pen=pg.mkPen(color, width=2))

    def update_graphs(self, values):
        for i, key in enumerate(['r', 'p', 'y']):
            self.buffer[key] = np.roll(self.buffer[key], -1); self.buffer[key][-1] = values[i]
        self.curve_r.setData(self.buffer['r']); self.curve_p.setData(self.buffer['p']); self.curve_y.setData(self.buffer['y'])

    def update_labels(self, nav):
        self.ind_lat.value_label.setText(f"{nav[0]:.7f}")
        self.ind_lon.value_label.setText(f"{nav[1]:.7f}")
        self.ind_alt.value_label.setText(f"{nav[2]:.2f} m")


    def launch_exe(self):
        # 1. Загружаем переменные
        load_dotenv()
        target_title = os.getenv("MODEL_NAME", "My project")

        try:
            # 2. УНИВЕРСАЛЬНЫЙ ПУТЬ: работает и в .py, и в собранном .exe
            if getattr(sys, 'frozen', False):
                # Если это .exe, папка model лежит рядом с ним
                base_dir = os.path.dirname(sys.executable)
            else:
                # Если это скрипт, поднимаемся на уровень выше от src
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            model_dir = os.path.join(base_dir, "model")
            exe_path = os.path.join(model_dir, f"{target_title}.exe")

            # 3. ЗАПУСК
            try:
                subprocess.Popen([exe_path], cwd=model_dir)
            except FileNotFoundError:
                print(f"Ошибка: Не найден {exe_path}")
                return

            # 4. ПОИСК И ВСТРАИВАНИЕ
            for _ in range(20):
                QApplication.processEvents() # Чтобы интерфейс не замерзал

                # Ищем сначала по точному имени, потом по классу Unity
                hwnd = win32gui.FindWindow(None, target_title)
                if not hwnd:
                    hwnd = win32gui.FindWindow("UnityWndClass", None)

                if hwnd:
                    self.unity_hwnd = hwnd
                    # Принудительно вклеиваем в контейнер
                    win32gui.SetParent(self.unity_hwnd, int(self.exe_container.winId()))

                    # Убираем рамки окна
                    style = win32gui.GetWindowLong(self.unity_hwnd, win32con.GWL_STYLE)
                    win32gui.SetWindowLong(self.unity_hwnd, win32con.GWL_STYLE,
                                           style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME)

                    self.resize_exe()
                    print(f"Модель '{target_title}' успешно встроена.")
                    break
                time.sleep(1)

        except Exception as e:
            print(f"Error in launch_exe: {e}")

    def resize_exe(self):
        if self.unity_hwnd:
            rect = self.exe_container.geometry()
            win32gui.MoveWindow(self.unity_hwnd, 0, 0, rect.width(), rect.height(), True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(50, self.resize_exe)
    # ... твой существующий код ...

    def closeEvent(self, event):
        """Метод вызывается автоматически при закрытии окна"""
        print("Закрытие приложения. Очистка процессов...")
        target = os.getenv("MODEL_NAME", "MyProject.exe")
        if not target.endswith('.exe'):
            target += '.exe'
        # 1. Останавливаем поток приема данных
        if hasattr(self, 'udp_thread'):
            self.udp_thread.terminate()

        # 2. Принудительно убиваем Unity, чтобы освободить порт 5005
        # Используем /F (принудительно) и /T (вместе с дочерними процессами)
        os.system(f'taskkill /F /IM "{target}" /T')

        event.accept() # Подтверждаем закрытие окна



if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = FlightControlApp()
    win.show()
    sys.exit(app.exec())