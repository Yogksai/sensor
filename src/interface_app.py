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
from PyQt6.QtGui import QFont, QColor
import pyqtgraph as pg
from dotenv import load_dotenv


# --- МОДУЛЬ СЕТИ (БЕЗ ИЗМЕНЕНИЙ) ---
class UDPBridge(QThread):
    angles_received = pyqtSignal(list)
    gps_received = pyqtSignal(list)

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
                    out_sock.sendto(f"{parts[0]:.2f},{parts[1]:.2f},{parts[2]:.2f}".encode(), unity_addr)
                    self.angles_received.emit(parts[0:3])
                    self.gps_received.emit(parts[3:6])
            except (socket.timeout, ValueError, IndexError):
                continue


# --- ОСНОВНОЕ ПРИЛОЖЕНИЕ (РАСШИРЕННОЕ) ---
class FlightControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FCS - Advanced Telemetry Monitor")
        self.resize(1600, 950)  # Немного увеличим для вкладок
        self.max_points = 200  # Больше точек для плавности

        # Данные
        self.buffer = {'r': np.zeros(self.max_points), 'p': np.zeros(self.max_points), 'y': np.zeros(self.max_points)}
        self.x_axis = np.arange(self.max_points)  # Ось X для графиков

        # --- 1. КРАСИВЫЙ ЦВЕТОВОЙ ИНТЕРФЕЙС (CSS) ---
        # Задаем общую темную тему
        app.setPalette(QApplication.style().standardPalette())
        self.setStyleSheet("""
            QMainWindow { background-color: #1a1a1a; color: #f0f0f0; }
            QLabel { color: #f0f0f0; font-family: 'Segoe UI'; }
            QTabWidget::pane { border: 1px solid #333; background-color: #1a1a1a; }
            QTabBar::tab { background: #2d2d2d; color: #b0b0b0; padding: 10px 20px; border: 1px solid #333; border-bottom: none; }
            QTabBar::tab:selected { background: #3d3d3d; color: #ffffff; border-color: #555; }
            QTabBar::tab:hover { background: #353535; }
        """)

        central_widget = QWidget()
        self.main_layout = QGridLayout(central_widget)
        self.setCentralWidget(central_widget)

        # --- 2. ДОБАВЛЕНИЕ ВКЛАДОК (Рисунок 2) ---
        self.tabs = QTabWidget()
        # Добавляем вкладку "Real-Time Data"
        self.telemetry_tab = QWidget()
        self.telemetry_layout = QGridLayout(self.telemetry_tab)

        # Добавляем вкладки-заглушки "Mission" и "Analyze"
        self.tabs.addTab(QWidget(), "Mission")
        self.tabs.addTab(self.telemetry_tab, "Real-Time Data")
        self.tabs.addTab(QWidget(), "Analyze")

        # Основной лейаут теперь содержит вкладки и Unity
        # Вкладки слева
        self.main_layout.addWidget(self.tabs, 0, 0, 1, 1)

        # --- 3. ИНДИКАТОРЫ (Внутри вкладки) ---
        # Создаем контейнер для индикаторов
        indicators_container = QWidget()
        indicators_layout = QGridLayout(indicators_container)

        self.ind_lat = self.create_indicator("ШИРОТА (LAT)", "#FF4444")
        self.ind_lon = self.create_indicator("ДОЛГОТА (LON)", "#44FF44")
        self.ind_alt = self.create_indicator("ВЫСОТА (ALT)", "#4444FF")

        indicators_layout.addWidget(self.ind_lat, 0, 0);
        indicators_layout.addWidget(self.ind_lon, 0, 1);
        indicators_layout.addWidget(self.ind_alt, 0, 2)

        # Размещаем индикаторы внутри вкладки сверху
        self.telemetry_layout.addWidget(indicators_container, 0, 0, 1, 3)

        # --- 4. КРАСИВЫЕ ГРАФИКИ (Внутри вкладки, Рисунок 1) ---
        # Настройка глобальных стилей pyqtgraph
        pg.setConfigOption('background', '#1a1a1a')  # Фон как у окна
        pg.setConfigOption('foreground', '#d0d0d0')  # Цвет осей и текста

        # Создаем графики с улучшенными стилями
        self.pw_r, self.curve_r = self.create_plot("ROLL ANGLE", '#FF4444')
        self.pw_p, self.curve_p = self.create_plot("PITCH ANGLE", '#44FF44')
        self.pw_y, self.curve_y = self.create_plot("YAW ANGLE", '#4444FF')

        # Размещаем графики внутри вкладки под индикаторами
        self.telemetry_layout.addWidget(self.pw_r, 1, 0);
        self.telemetry_layout.addWidget(self.pw_p, 2, 0);
        self.telemetry_layout.addWidget(self.pw_y, 3, 0)

        # Растягиваем графики
        self.telemetry_layout.setRowStretch(1, 1);
        self.telemetry_layout.setRowStretch(2, 1);
        self.telemetry_layout.setRowStretch(3, 1)
        self.telemetry_layout.setColumnStretch(0, 1)

        # --- 5. UNITY КОНТЕЙНЕР (Справа) ---
        self.exe_container = QWidget()
        self.exe_container.setMinimumWidth(800)
        self.exe_container.setStyleSheet("background-color: black; border: 2px solid #3d3d3d; border-radius: 5px;")
        # Размещаем Unity контейнер справа от вкладок
        self.main_layout.addWidget(self.exe_container, 0, 1, 1, 2)

        # Соотношение ширины вкладок и Unity
        self.main_layout.setColumnStretch(0, 1)
        self.main_layout.setColumnStretch(1, 2)

        # Потоки (без изменений)
        self.udp_thread = UDPBridge()
        self.udp_thread.angles_received.connect(self.update_graphs)
        self.udp_thread.gps_received.connect(self.update_labels)
        self.udp_thread.start()

        self.unity_hwnd = None
        QTimer.singleShot(2000, self.launch_exe)

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (УЛУЧШЕННЫЕ) ---
    def create_indicator(self, label_text, color):
        container = QWidget();
        l_layout = QGridLayout(container)

        # Красивый шрифт для заголовка
        label_lbl = QLabel(label_text);
        label_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        label_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Красивый шрифт для значения
        val_lbl = QLabel("0.000000");
        val_lbl.setFont(QFont("Consolas", 22, QFont.Weight.Bold))

        # Стилизация индикатора: тень, отступы, фон
        val_lbl.setStyleSheet(f"""
            color: {color}; 
            background-color: #2d2d2d; 
            padding: 15px; 
            border-radius: 8px; 
            border: 1px solid #3d3d3d;
        """)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        l_layout.addWidget(label_lbl, 0, 0)
        l_layout.addWidget(val_lbl, 1, 0)
        l_layout.setContentsMargins(5, 5, 5, 5)  # Отступы внутри

        container.value_label = val_lbl
        return container

    def create_plot(self, title, color):
        # Создаем PlotWidget с заголовком
        pw = pg.PlotWidget(title=title)

        # --- Стилизация графика (Рисунок 1) ---
        # 1. Сетка
        pw.showGrid(x=True, y=True, alpha=0.3)

        # 2. Настройка осей (шрифт, цвет)
        font = QFont("Segoe UI", 9)
        pw.getAxis('left').setTickFont(font)
        pw.getAxis('bottom').setTickFont(font)
        pw.getAxis('left').setPen('#808080')
        pw.getAxis('bottom').setPen('#808080')

        # 3. Настройка заголовка (цвет, шрифт)
        title_item = pw.getPlotItem().titleLabel
        title_item.setText(title, color='#ffffff', size='11pt')
        title_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        # 4. Прозрачность фона самого графика
        pw.setBackground(None)

        # 5. Линия графика: делаем её толще и сглаженной
        pen = pg.mkPen(color, width=2.5)  # Толщина
        curve = pw.plot(pen=pen, antialias=True)  # Сглаживание (antialias)

        return pw, curve

    # --- МЕТОДЫ ОБНОВЛЕНИЯ И ЛОГИКИ (БЕЗ ИЗМЕНЕНИЙ ЛОГИКИ) ---
    def update_graphs(self, values):
        for i, key in enumerate(['r', 'p', 'y']):
            self.buffer[key] = np.roll(self.buffer[key], -1)
            self.buffer[key][-1] = values[i]

        # Обновляем данные на графиках
        self.curve_r.setData(self.buffer['r'])
        self.curve_p.setData(self.buffer['p'])
        self.curve_y.setData(self.buffer['y'])

    def update_labels(self, nav):
        self.ind_lat.value_label.setText(f"{nav[0]:.7f}")
        self.ind_lon.value_label.setText(f"{nav[1]:.7f}")
        self.ind_alt.value_label.setText(f"{nav[2]:.2f} m")

    def launch_exe(self):
        load_dotenv()
        target_title = os.getenv("MODEL_NAME", "My project")
        try:
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            model_dir = os.path.join(base_dir, "model")
            exe_path = os.path.join(model_dir, f"{target_title}.exe")

            try:
                subprocess.Popen([exe_path], cwd=model_dir)
            except FileNotFoundError:
                return

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
        if hasattr(self, 'udp_thread'): self.udp_thread.terminate()
        os.system(f'taskkill /F /IM "{target}" /T')
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Базовая современная тема
    win = FlightControlApp()
    win.show()
    sys.exit(app.exec())