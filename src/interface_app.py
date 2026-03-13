import sys
import socket
import subprocess
import time
import os
import numpy as np
import win32gui
import win32con
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGridLayout,
                             QWidget, QLabel, QTabWidget, QVBoxLayout)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont
import pyqtgraph as pg
from dotenv import load_dotenv


# --- МОДУЛЬ СЕТИ ---
class UDPBridge(QThread):
    # Сигнал теперь передает словарь: {'type': 'telemetry', 'data': [...]}
    data_received = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def stop(self):
        self._run_flag = False

    def run(self):
        load_dotenv()
        in_port = int(os.getenv("UI_PORT", "5006"))
        out_port = int(os.getenv("UNITY_PORT", "5005"))

        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.bind(('127.0.0.1', in_port))
        in_sock.settimeout(1.0)

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unity_addr = ('127.0.0.1', out_port)

        while self._run_flag:
            try:
                data, _ = in_sock.recvfrom(1024)
                line = data.decode('utf-8').strip()
                parts = [float(x) for x in line.split(',')]

                if len(parts) >= 6:
                    # Релей в Unity (углы)
                    out_sock.sendto(f"{parts[0]:.2f},{parts[1]:.2f},{parts[2]:.2f}".encode(), unity_addr)

                    # Отправляем упакованные данные в интерфейс
                    self.data_received.emit({
                        'angles': parts[0:3],
                        'gps': parts[3:6]
                    })
            except (socket.timeout, ValueError, IndexError):
                continue


# --- ОСНОВНОЕ ПРИЛОЖЕНИЕ ---
class FlightControlApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # 1. КОНФИГУРАЦИЯ (Сюда добавлять новые элементы)
        self.GRAPH_CONFIG = [
            {'key': 'roll', 'title': 'ROLL', 'color': 'r', 'index': 0},
            {'key': 'pitch', 'title': 'PITCH', 'color': 'g', 'index': 1},
            {'key': 'yaw', 'title': 'YAW', 'color': 'b', 'index': 2},
            # Чтобы добавить график: {'key': 'speed', 'title': 'SPEED', 'color': 'y', 'index': 6}
        ]

        self.INDICATOR_CONFIG = [
            {'label': "ШИРОТА (LAT)", 'color': "#FF0000", 'suffix': "", 'index': 0},
            {'label': "ДОЛГОТА (LON)", 'color': "#008000", 'suffix': "", 'index': 1},
            {'label': "ВЫСОТА (ALT)", 'color': "#0000FF", 'suffix': " m", 'index': 2},
        ]

        self.init_ui()
        self.init_threads()

    def init_ui(self):
        self.setWindowTitle("FCS - Modular Telemetry Monitor")
        self.resize(1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QGridLayout(central_widget)

        # Создаем вкладки (Tabs) для удобства расширения
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs, 1, 0, 3, 1)  # Графики слева

        # --- БЛОК ИНДИКАТОРОВ (ВЕРХ) ---
        self.indicators = {}
        for i, cfg in enumerate(self.INDICATOR_CONFIG):
            ind = self.create_indicator(cfg['label'], cfg['color'])
            self.main_layout.addWidget(ind, 0, i)
            self.indicators[cfg['index']] = ind

        # --- БЛОК ГРАФИКОВ ---
        # Создаем прокручиваемую область или вкладки под графики
        graph_container = QWidget()
        graph_layout = QVBoxLayout(graph_container)

        self.plots = {}
        self.max_points = 100

        for cfg in self.GRAPH_CONFIG:
            pw, curve = self.create_plot(cfg['title'], cfg['color'])
            graph_layout.addWidget(pw)
            self.plots[cfg['key']] = {
                'curve': curve,
                'data': np.zeros(self.max_points),
                'index': cfg['index']
            }

        self.tabs.addTab(graph_container, "Телеметрия")
        self.tabs.addTab(QWidget(), "Доп. настройки")  # Заглушка под новую вкладку

        # --- БЛОК UNITY ---
        self.exe_container = QWidget()
        self.exe_container.setMinimumWidth(800)
        self.exe_container.setStyleSheet("background-color: black; border: 2px solid #333;")
        self.main_layout.addWidget(self.exe_container, 1, 1, 3, 2)

    def init_threads(self):
        self.udp_thread = UDPBridge()
        self.udp_thread.data_received.connect(self.process_incoming_data)
        self.udp_thread.start()

        self.unity_hwnd = None
        QTimer.singleShot(2000, self.launch_exe)

    # --- ЛОГИКА ОБРАБОТКИ ---
    def process_incoming_data(self, packet):
        # Обновляем графики по конфигу
        angles = packet['angles']
        for key, plot_obj in self.plots.items():
            idx = plot_obj['index']
            if idx < len(angles):
                plot_obj['data'] = np.roll(plot_obj['data'], -1)
                plot_obj['data'][-1] = angles[idx]
                plot_obj['curve'].setData(plot_obj['data'])

        # Обновляем индикаторы по конфигу
        gps = packet['gps']
        for idx, ind_widget in self.indicators.items():
            if idx < len(gps):
                suffix = next(item['suffix'] for item in self.INDICATOR_CONFIG if item['index'] == idx)
                ind_widget.value_label.setText(f"{gps[idx]:.6f}{suffix}")

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (БЕЗ ИЗМЕНЕНИЙ) ---
    def create_indicator(self, label_text, color):
        container = QWidget()
        l_layout = QVBoxLayout(container)
        val_lbl = QLabel("0.000000")
        val_lbl.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {color}; background-color: #222; padding: 5px; border-radius: 5px;")
        l_layout.addWidget(QLabel(label_text), alignment=Qt.AlignmentFlag.AlignCenter)
        l_layout.addWidget(val_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        container.value_label = val_lbl
        return container

    def create_plot(self, title, color):
        pw = pg.PlotWidget(title=title)
        pw.setBackground('w')
        pw.showGrid(x=True, y=True)
        return pw, pw.plot(pen=pg.mkPen(color, width=2))

    def launch_exe(self):
        load_dotenv()
        target_title = os.getenv("MODEL_NAME", "My project")
        try:
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            model_dir = os.path.join(base_dir, "model")
            exe_path = os.path.join(model_dir, f"{target_title}.exe")

            subprocess.Popen([exe_path], cwd=model_dir)

            for _ in range(20):
                QApplication.processEvents()
                hwnd = win32gui.FindWindow(None, target_title) or win32gui.FindWindow("UnityWndClass", None)
                if hwnd:
                    self.unity_hwnd = hwnd
                    win32gui.SetParent(self.unity_hwnd, int(self.exe_container.winId()))
                    style = win32gui.GetWindowLong(self.unity_hwnd, win32con.GWL_STYLE)
                    win32gui.SetWindowLong(self.unity_hwnd, win32con.GWL_STYLE,
                                           style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME)
                    self.resize_exe()
                    break
                time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")

    def resize_exe(self):
        if self.unity_hwnd:
            rect = self.exe_container.geometry()
            win32gui.MoveWindow(self.unity_hwnd, 0, 0, rect.width(), rect.height(), True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(50, self.resize_exe)

    def closeEvent(self, event):
        target = os.getenv("MODEL_NAME", "MyProject.exe")
        if not target.endswith('.exe'): target += '.exe'
        if hasattr(self, 'udp_thread'): self.udp_thread.stop()
        os.system(f'taskkill /F /IM "{target}" /T')
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = FlightControlApp()
    win.show()
    sys.exit(app.exec())