import sys
import socket
import subprocess
import time
import os
import numpy as np
import win32gui
import win32con
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGridLayout,
                             QWidget, QLabel, QTabWidget, QVBoxLayout, QHBoxLayout)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont
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
        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.bind(('127.0.0.1', int(os.getenv("UI_PORT", "5006"))))
        in_sock.settimeout(1.0)
        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unity_addr = ('127.0.0.1', int(os.getenv("UNITY_PORT", "5005")))
        while self._run_flag:
            try:
                data, _ = in_sock.recvfrom(1024)
                parts = [float(x) for x in data.decode('utf-8').strip().split(',')]
                if len(parts) >= 6:
                    out_sock.sendto(f"{parts[0]:.2f},{parts[1]:.2f},{parts[2]:.2f}".encode(), unity_addr)
                    self.angles_received.emit(parts[0:3])
                    self.gps_received.emit(parts[3:6])
            except:
                continue


# --- ОСНОВНОЕ ПРИЛОЖЕНИЕ ---
class FlightControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FCS - Integrated Monitor")
        self.resize(1600, 900)

        if QApplication.instance():
            QApplication.instance().setPalette(QApplication.style().standardPalette())

        self.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            QTabWidget::pane { border: 1px solid #333; background: #121212; }
            QTabBar::tab { background: #1e1e1e; color: #888; padding: 12px 30px; border: 1px solid #333; }
            QTabBar::tab:selected { background: #2d2d2d; color: #fff; border-bottom: 2px solid #0078d7; }
        """)

        self.max_points = 150
        self.buffer = {'r': np.zeros(self.max_points), 'p': np.zeros(self.max_points), 'y': np.zeros(self.max_points)}
        self.unity_hwnd = None

        # ГЛАВНЫЙ LAYOUT (Теперь просто на все окно)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)  # Вертикальный для вкладок

        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # --- ВКЛАДКА REAL-TIME DATA (Здесь и графики, и Unity) ---
        self.rt_widget = QWidget()
        self.rt_content_layout = QHBoxLayout(self.rt_widget)  # ГОРИЗОНТАЛЬНЫЙ внутри вкладки

        # Левая колонка во вкладке: Индикаторы и Графики
        left_column = QVBoxLayout()
        ind_row = QHBoxLayout()
        self.ind_lat = self.create_indicator("LATITUDE", "#FF4444")
        self.ind_lon = self.create_indicator("LONGITUDE", "#44FF44")
        self.ind_alt = self.create_indicator("ALTITUDE", "#4444FF")
        ind_row.addWidget(self.ind_lat);
        ind_row.addWidget(self.ind_lon);
        ind_row.addWidget(self.ind_alt)
        left_column.addLayout(ind_row)

        pg.setConfigOption('background', '#121212')
        self.pw_r, self.curve_r = self.create_plot("ROLL", '#FF4444')
        self.pw_p, self.curve_p = self.create_plot("PITCH", '#44FF44')
        self.pw_y, self.curve_y = self.create_plot("YAW", '#4444FF')
        left_column.addWidget(self.pw_r);
        left_column.addWidget(self.pw_p);
        left_column.addWidget(self.pw_y)

        self.rt_content_layout.addLayout(left_column, stretch=1)

        # ПРАВАЯ КОЛОНКА ВО ВКЛАДКЕ: Контейнер Unity
        self.exe_container = QWidget()
        self.exe_container.setMinimumWidth(800)
        self.exe_container.setStyleSheet("background-color: #000; border: 1px solid #333;")
        self.rt_content_layout.addWidget(self.exe_container, stretch=2)

        # Другие вкладки (Они будут пустыми и растянутся на все окно)
        self.tabs.addTab(QWidget(), "Mission")
        self.tabs.addTab(self.rt_widget, "Real-Time Data")
        self.tabs.addTab(QWidget(), "Analyze")
        self.tabs.setCurrentIndex(1)

        # Потоки и таймеры
        self.udp_thread = UDPBridge()
        self.udp_thread.angles_received.connect(self.update_graphs)
        self.udp_thread.gps_received.connect(self.update_labels)
        self.udp_thread.start()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QTimer.singleShot(2000, self.launch_exe)

    def create_indicator(self, label_text, color):
        container = QWidget();
        vbox = QVBoxLayout(container)
        val = QLabel("0.000000");
        val.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {color}; background: #1e1e1e; padding: 10px; border: 1px solid #333;")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(QLabel(label_text));
        vbox.addWidget(val)
        container.value_label = val
        return container

    def create_plot(self, title, color):
        pw = pg.PlotWidget(title=title)
        pw.showGrid(x=True, y=True, alpha=0.2)
        curve = pw.plot(pen=pg.mkPen(color=color, width=2), antialias=True)
        return pw, curve

    def on_tab_changed(self, index):
        if self.unity_hwnd:
            if index == 1:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_SHOW)
                # Даем время Qt пересчитать layout вкладки
                QTimer.singleShot(50, self.resize_exe)
            else:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_HIDE)

    def resize_exe(self):
        """Форсированное растягивание Unity"""
        if self.unity_hwnd and self.exe_container.isVisible():
            # Получаем ГЛОБАЛЬНЫЕ координаты контейнера
            rect = self.exe_container.geometry()
            # Нам нужны координаты относительно внутреннего окна, поэтому 0,0
            w, h = rect.width(), rect.height()

            if w > 100:  # Защита от сворачивания
                # SWP_FRAMECHANGED заставляет Unity перерисовать движок под новый размер
                win32gui.SetWindowPos(self.unity_hwnd, 0, 0, 0, w, h,
                                      win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW)

    def update_graphs(self, values):
        for i, key in enumerate(['r', 'p', 'y']):
            self.buffer[key] = np.roll(self.buffer[key], -1);
            self.buffer[key][-1] = values[i]
        self.curve_r.setData(self.buffer['r']);
        self.curve_p.setData(self.buffer['p']);
        self.curve_y.setData(self.buffer['y'])

    def update_labels(self, nav):
        self.ind_lat.value_label.setText(f"{nav[0]:.7f}");
        self.ind_lon.value_label.setText(f"{nav[1]:.7f}");
        self.ind_alt.value_label.setText(f"{nav[2]:.2f} m")

    def launch_exe(self):
        load_dotenv()
        target_title = os.getenv("MODEL_NAME", "My project")
        # Упрощенный поиск пути
        exe_path = os.path.join(os.getcwd(), "model", f"{target_title}.exe")
        if os.path.exists(exe_path):
            subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            for _ in range(40):
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
                time.sleep(0.5)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(50, self.resize_exe)

    def closeEvent(self, event):
        self.udp_thread.stop()
        os.system(f'taskkill /F /IM "{os.getenv("MODEL_NAME", "My project")}.exe" /T')
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = FlightControlApp()
    win.show()
    sys.exit(app.exec())