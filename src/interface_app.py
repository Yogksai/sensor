import sys
import socket
import subprocess
import time
import os
import numpy as np
import win32gui
import win32con
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                             QTabWidget, QVBoxLayout, QHBoxLayout)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont
import pyqtgraph as pg
from dotenv import load_dotenv

# --- МОДУЛЬ СЕТИ ---
class UDPBridge(QThread):
    data_received = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def stop(self): self._run_flag = False

    def run(self):
        load_dotenv()
        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.bind(('127.0.0.1', int(os.getenv("UI_PORT", "5006"))))
        in_sock.settimeout(0.5)

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unity_addr = ('127.0.0.1', int(os.getenv("UNITY_PORT", "5005")))

        while self._run_flag:
            try:
                data, _ = in_sock.recvfrom(1024)
                parts = [float(x) for x in data.decode('utf-8').strip().split(',')]
                if len(parts) >= 6:
                    out_sock.sendto(f"{parts[0]:.2f},{parts[1]:.2f},{parts[2]:.2f}".encode(), unity_addr)
                    self.data_received.emit(parts)
            except: continue

# --- ОСНОВНОЕ ПРИЛОЖЕНИЕ ---
class FlightControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FCS - Integrated Monitor")
        self.resize(1600, 950)

        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QTabWidget::pane { border: 1px solid #444; background: #2b2b2b; }
            QTabBar::tab { background: #3c3f41; color: #bbb; padding: 12px 30px; border: 1px solid #444; }
            QTabBar::tab:selected { background: #4e5254; color: #fff; border-bottom: 2px solid #0078d7; }
            QLabel { color: #eee; }
        """)

        # Данные
        self.traj_x, self.traj_y, self.traj_y_smooth = [], [], []
        self.speed_data, self.accel_data, self.alt_history = [], [], []

        # --- ФИКС: Переменные для автономного графика ---
        self.virtual_dist = 0.0
        self.last_update_t = time.time()
        self.is_flying = False
        self.last_raw_data = [0.0] * 6

        self.max_pts = 150
        self.buffer = {'r': np.zeros(self.max_pts), 'p': np.zeros(self.max_pts), 'y': np.zeros(self.max_pts)}
        self.start_gps = None
        self.battery = 98.0
        self.unity_hwnd = None

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        pg.setConfigOption('background', '#1e1e1e')
        pg.setConfigOption('foreground', '#dcdcdc')

        # --- ВКЛАДКА 1: REAL-TIME DATA ---
        self.rt_tab = QWidget()
        rt_layout = QHBoxLayout(self.rt_tab)
        rt_left = QVBoxLayout()

        rt_ind_row = QHBoxLayout()
        self.rt_lat = self.create_rt_indicator("LATITUDE", "#FF4444")
        self.rt_lon = self.create_rt_indicator("LONGITUDE", "#44FF44")
        self.rt_alt = self.create_rt_indicator("ALTITUDE", "#4444FF")
        rt_ind_row.addWidget(self.rt_lat); rt_ind_row.addWidget(self.rt_lon); rt_ind_row.addWidget(self.rt_alt)
        rt_left.addLayout(rt_ind_row)

        self.pw_r, self.curve_r = self.create_rt_plot("ROLL", "#FF4444")
        self.pw_p, self.curve_p = self.create_rt_plot("PITCH", "#44FF44")
        self.pw_y, self.curve_y = self.create_rt_plot("YAW", "#4444FF")
        rt_left.addWidget(self.pw_r); rt_left.addWidget(self.pw_p); rt_left.addWidget(self.pw_y)
        rt_layout.addLayout(rt_left, stretch=1)

        self.exe_container = QWidget()
        self.exe_container.setMinimumWidth(800)
        self.exe_container.setStyleSheet("background: #000; border: 1px solid #444;")
        rt_layout.addWidget(self.exe_container, stretch=2)

        # --- ВКЛАДКА 2: ANALYZE ---
        self.analyze_tab = QWidget()
        an_layout = QHBoxLayout(self.analyze_tab)
        an_left = QVBoxLayout()

        self.pw_traj = pg.PlotWidget(title="Trajectory Analysis (Yellow: Raw, Blue: Filtered)")
        self.pw_traj.showGrid(x=True, y=True, alpha=0.3)
        # Оптимизация: не рисуем лишние детали
        self.pw_traj.setDownsampling(auto=True, mode='mean')
        self.pw_traj.setClipToView(True)

        self.curve_raw = self.pw_traj.plot(pen=pg.mkPen(color='#FFFF00', width=1))
        self.curve_smooth = self.pw_traj.plot(pen=pg.mkPen(color='#0000FF', width=3))
        an_left.addWidget(self.pw_traj, stretch=3)

        an_bot_row = QHBoxLayout()
        self.ind_temp = self.create_digi_ind("Temperature", "25", "°C")
        self.ind_bat = self.create_digi_ind("Battery", "98", "%")
        self.ind_rssi = self.create_digi_ind("RSSI", "75", "")
        an_bot_row.addWidget(self.ind_temp); an_bot_row.addWidget(self.ind_bat); an_bot_row.addWidget(self.ind_rssi)
        an_left.addLayout(an_bot_row, stretch=1)
        an_layout.addLayout(an_left, stretch=3)

        an_right = QVBoxLayout()
        self.pw_speed, self.curve_speed = self.create_small_plot("Speed Plot")
        self.pw_accel, self.curve_accel = self.create_small_plot("Acceleration Rate")
        self.pw_alt_plot, self.curve_alt_plot = self.create_small_plot("Altitude Plot")
        an_right.addWidget(self.pw_speed); an_right.addWidget(self.pw_accel); an_right.addWidget(self.pw_alt_plot)
        an_layout.addLayout(an_right, stretch=1)

        self.tabs.addTab(QWidget(), "Mission")
        self.tabs.addTab(self.rt_tab, "Real-Time Data")
        self.tabs.addTab(self.analyze_tab, "Analyze")
        self.tabs.setCurrentIndex(2)

        # --- ФИКС: Работа через таймер вместо прямого вызова (разгрузка CPU) ---
        self.udp = UDPBridge()
        self.udp.data_received.connect(self.store_data)
        self.udp.start()

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_all)
        self.ui_timer.start(33) # 30 FPS

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QTimer.singleShot(2000, self.launch_exe)

    def store_data(self, data):
        self.last_raw_data = data

    def create_rt_indicator(self, txt, col):
        w = QWidget(); v = QVBoxLayout(w)
        val = QLabel("0.000000")
        val.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {col}; background: #1e1e1e; padding: 5px; border: 1px solid #444;")
        v.addWidget(QLabel(txt)); v.addWidget(val)
        w.val_label = val
        return w

    def create_rt_plot(self, title, col):
        pw = pg.PlotWidget(title=title); pw.setFixedHeight(200)
        return pw, pw.plot(pen=pg.mkPen(color=col, width=2))

    def create_small_plot(self, title):
        pw = pg.PlotWidget(title=title)
        return pw, pw.plot(pen=pg.mkPen(color="#4682B4", width=2))

    def create_digi_ind(self, title, start, unit):
        w = QWidget(); v = QVBoxLayout(w)
        l = QLabel(title); l.setStyleSheet("color: #aaa; font-weight: bold;")
        val = QLabel(f"{start}{unit}")
        val.setFont(QFont("Consolas", 45, QFont.Weight.Bold))
        val.setStyleSheet("color: #00ff00; background: #121212; padding: 10px; border: 2px solid #444;")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(l); v.addWidget(val)
        w.val_label = val
        return w

    def update_all(self):
        data = self.last_raw_data
        r, p, y, lat, lon, alt = data
        t_now = time.time()
        dt = t_now - self.last_update_t
        self.last_update_t = t_now

        # Автономное движение графика по X
        if alt > 1.0:
            self.is_flying = True
            self.virtual_dist += 150.0 * dt

        if alt < 0.5 and self.is_flying and len(self.traj_y) > 10:
            self.traj_x, self.traj_y, self.traj_y_smooth = [], [], []
            self.speed_data, self.accel_data, self.alt_history = [], [], []
            self.virtual_dist = 0.0
            self.is_flying = False

        if self.is_flying or alt > 0.5:
            self.traj_x.append(self.virtual_dist)
            self.traj_y.append(alt)
            # Сглаживание
            window = 10
            avg_y = sum(self.traj_y[-window:]) / len(self.traj_y[-window:])
            self.traj_y_smooth.append(avg_y)

        # Update RT Text
        self.rt_lat.val_label.setText(f"{lat:.7f}")
        self.rt_lon.val_label.setText(f"{lon:.7f}")
        self.rt_alt.val_label.setText(f"{alt:.1f} m")

        curr_tab = self.tabs.currentIndex()
        if curr_tab == 1:
            for i, key in enumerate(['r', 'p', 'y']):
                self.buffer[key] = np.roll(self.buffer[key], -1)
                self.buffer[key][-1] = data[i]
            self.curve_r.setData(self.buffer['r'])
            self.curve_p.setData(self.buffer['p'])
            self.curve_y.setData(self.buffer['y'])

        elif curr_tab == 2:
            # --- ФИКС: Безопасная отрисовка только последних 2000 точек ---
            disp_x = self.traj_x[-2000:]
            count = len(disp_x)
            disp_y_raw = self.traj_y[-count:]

            self.curve_raw.setData(disp_x, disp_y_raw)
            if len(self.traj_y_smooth) >= count:
                self.curve_smooth.setData(disp_x, self.traj_y_smooth[-count:])

            self.speed_data.append(40 * np.sin(t_now * 1.5) + 100)
            self.accel_data.append(10 * np.sin(t_now * 4.0) + np.random.normal(0, 0.5))
            self.alt_history.append(alt)

            self.curve_speed.setData(self.speed_data[-100:])
            self.curve_accel.setData(self.accel_data[-100:])
            self.curve_alt_plot.setData(self.alt_history[-100:])

            # Индикаторы
            tmp = max(18, min(25, 25 - int((alt/8000)*7)))
            if tmp % 2 != 0: tmp -= 1
            self.ind_temp.val_label.setText(f"{tmp}°C")
            if self.battery > 5: self.battery -= 0.001
            self.ind_bat.val_label.setText(f"{int(self.battery)}%")
            self.ind_rssi.val_label.setText(str(74 + np.random.randint(-1, 3)))

    def on_tab_changed(self, i):
        if self.unity_hwnd:
            if i == 1:  # Вкладка Real-Time
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_SHOW)
                # Даем Qt время отрисовать вкладку, прежде чем подгонять Unity
                QTimer.singleShot(150, self.resize_exe)
            else:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_HIDE)

    def resize_exe(self):
        if self.unity_hwnd and self.exe_container.isVisible():
            # Получаем реальные размеры контейнера в пикселях
            rect = self.exe_container.rect()
            point = self.exe_container.mapToGlobal(rect.topLeft())

            # Насильно втискиваем Unity в рамки
            win32gui.SetWindowPos(
                self.unity_hwnd,
                win32con.HWND_TOP,
                0, 0,
                self.exe_container.width(),
                self.exe_container.height(),
                win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW
            )

    def launch_exe(self):
        load_dotenv()
        t = os.getenv("MODEL_NAME", "My project")
        p = os.path.join(os.getcwd(), "model", f"{t}.exe")
        if os.path.exists(p):
            subprocess.Popen([p], cwd=os.path.dirname(p))
            for _ in range(40):
                QApplication.processEvents()
                h = win32gui.FindWindow(None, t) or win32gui.FindWindow("UnityWndClass", None)
                if h:
                    self.unity_hwnd = h
                    win32gui.SetParent(h, int(self.exe_container.winId()))
                    s = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
                    win32gui.SetWindowLong(h, win32con.GWL_STYLE, s & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME)
                    self.resize_exe(); break
                time.sleep(0.5)

    def resizeEvent(self, e): super().resizeEvent(e); QTimer.singleShot(50, self.resize_exe)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("Fusion")
    win = FlightControlApp(); win.show(); sys.exit(app.exec())