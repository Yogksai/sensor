import sys
import math
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
        # Ожидаем данные от конвертера (Bridge)
        in_sock.bind(('127.0.0.1', int(os.getenv("UI_PORT", "5006"))))
        in_sock.settimeout(0.5)

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        unity_addr = ('127.0.0.1', int(os.getenv("UNITY_PORT", "5005")))

        while self._run_flag:
            try:
                data, _ = in_sock.recvfrom(1024)
                # Теперь ожидаем 10 параметров: r,p,y,lat,lon,alt,s1,s2,s3,s4
                parts = [float(x) for x in data.decode('utf-8').strip().split(',')]
                if len(parts) >= 6:
                    # В Unity шлем только углы
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
        self.virtual_dist = 0.0
        self.last_update_t = time.time()
        self.is_flying = False
        self.last_raw_data = [0.0] * 10  # Расширено до 10
        self.max_pts = 150
        self.buffer = {'r': np.zeros(self.max_pts), 'p': np.zeros(self.max_pts), 'y': np.zeros(self.max_pts)}
        self.battery = 98.0
        self.unity_hwnd = None

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        pg.setConfigOption('background', '#1e1e1e')
        pg.setConfigOption('foreground', '#dcdcdc')

        # --- ВКЛАДКИ ---
        self.init_mission_tab()
        self.init_rt_data_tab()
        self.init_analyze_tab()

        self.tabs.setCurrentIndex(0)

        self.udp = UDPBridge()
        self.udp.data_received.connect(self.store_data)
        self.udp.start()

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_all)
        self.ui_timer.start(33)

        self.tabs.currentChanged.connect(self.on_tab_changed)
        QTimer.singleShot(2000, self.launch_exe)

    def store_data(self, data): self.last_raw_data = data

    def init_mission_tab(self):
        self.mission_tab = QWidget()
        m_layout = QHBoxLayout(self.mission_tab)
        m_left = QVBoxLayout()
        m_ind_row = QHBoxLayout()
        self.rt_lat = self.create_indicator("LATITUDE", "#FF4444")
        self.rt_lon = self.create_indicator("LONGITUDE", "#44FF44")
        self.rt_alt = self.create_indicator("ALTITUDE", "#4444FF")
        m_ind_row.addWidget(self.rt_lat); m_ind_row.addWidget(self.rt_lon); m_ind_row.addWidget(self.rt_alt)
        m_left.addLayout(m_ind_row)
        self.pw_r, self.curve_r = self.create_plot("ROLL", "#FF4444")
        self.pw_p, self.curve_p = self.create_plot("PITCH", "#44FF44")
        self.pw_y, self.curve_y = self.create_plot("YAW", "#4444FF")
        m_left.addWidget(self.pw_r); m_left.addWidget(self.pw_p); m_left.addWidget(self.pw_y)
        m_layout.addLayout(m_left, stretch=1)
        self.exe_container = QWidget()
        self.exe_container.setMinimumWidth(800)
        self.exe_container.setStyleSheet("background: #000; border: 1px solid #444;")
        m_layout.addWidget(self.exe_container, stretch=2)
        self.tabs.addTab(self.mission_tab, "Mission")

    def init_rt_data_tab(self):
        self.rt_data_tab = QWidget()
        rd_layout = QHBoxLayout(self.rt_data_tab)
        rd_left = QVBoxLayout()
        self.pw_traj = pg.PlotWidget(title="Trajectory Analysis (Yellow: Raw, Blue: Filtered)")
        self.pw_traj.showGrid(x=True, y=True, alpha=0.3)
        self.curve_raw = self.pw_traj.plot(pen=pg.mkPen(color='#FFFF00', width=1))
        self.curve_smooth = self.pw_traj.plot(pen=pg.mkPen(color='#0000FF', width=3))
        rd_left.addWidget(self.pw_traj, stretch=3)
        rd_bot_row = QHBoxLayout()
        self.ind_temp = self.create_digi_ind("Temperature", "25", "°C")
        self.ind_bat = self.create_digi_ind("Battery", "98", "%")
        self.ind_rssi = self.create_digi_ind("RSSI", "75", "")
        rd_bot_row.addWidget(self.ind_temp); rd_bot_row.addWidget(self.ind_bat); rd_bot_row.addWidget(self.ind_rssi)
        rd_left.addLayout(rd_bot_row, stretch=1)
        rd_layout.addLayout(rd_left, stretch=3)
        rd_right = QVBoxLayout()
        self.pw_speed, self.curve_speed = self.create_small_plot("Speed Plot")
        self.pw_accel, self.curve_accel = self.create_small_plot("Acceleration Rate")
        self.pw_alt_plot, self.curve_alt_plot = self.create_small_plot("Altitude Plot")
        rd_right.addWidget(self.pw_speed); rd_right.addWidget(self.pw_accel); rd_right.addWidget(self.pw_alt_plot)
        rd_layout.addLayout(rd_right, stretch=1)
        self.tabs.addTab(self.rt_data_tab, "Real-Time Data")

    def init_analyze_tab(self):
        self.analyze_tab = QWidget()
        an_layout = QHBoxLayout(self.analyze_tab)
        an_left_col = QVBoxLayout()
        self.pw_an_traj = pg.PlotWidget(title="Trajectory Correction (Active Segment)")
        self.pw_an_traj.showGrid(x=True, y=True, alpha=0.3)
        self.curve_an_traj = self.pw_an_traj.plot(pen=pg.mkPen(color='#0078d7', width=2))
        self.target_dot = self.pw_an_traj.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=12)
        an_left_col.addWidget(self.pw_an_traj)
        self.pw_rudders = pg.PlotWidget(title="Aerodynamic Rudders Control")
        self.pw_rudders.showGrid(x=True, y=True, alpha=0.3)
        self.pw_rudders.setYRange(-10, 10)
        limit_pen = pg.mkPen(color='#FF4444', width=1, style=Qt.PenStyle.DashLine)
        self.pw_rudders.addLine(y=7.5, pen=limit_pen, label="MAX +7.5°")
        self.pw_rudders.addLine(y=-7.5, pen=limit_pen, label="MIN -7.5°")
        self.curve_rudders = self.pw_rudders.plot(pen=pg.mkPen(color='#44FF44', width=1.5))
        an_left_col.addWidget(self.pw_rudders)
        an_layout.addLayout(an_left_col, stretch=2)
        an_layout.addWidget(QWidget(), stretch=1)
        self.tabs.addTab(self.analyze_tab, "Analyze")

    def create_indicator(self, txt, col):
        w = QWidget(); v = QVBoxLayout(w)
        val = QLabel("0.000000")
        val.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {col}; background: #1e1e1e; padding: 5px; border: 1px solid #444;")
        v.addWidget(QLabel(txt)); v.addWidget(val)
        w.val_label = val
        return w

    def create_plot(self, title, col):
        pw = pg.PlotWidget(title=title); pw.setFixedHeight(200)
        return pw, pw.plot(pen=pg.mkPen(color=col, width=2))

    def create_small_plot(self, title):
        pw = pg.PlotWidget(title=title)
        return pw, pw.plot(pen=pg.mkPen(color="#4682B4", width=2))

    def create_digi_ind(self, title, start, unit):
        w = QWidget(); v = QVBoxLayout(w)
        val = QLabel(f"{start}{unit}")
        val.setFont(QFont("Consolas", 45, QFont.Weight.Bold))
        val.setStyleSheet("color: #00ff00; background: #121212; padding: 10px; border: 2px solid #444;")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(QLabel(title)); v.addWidget(val)
        w.val_label = val
        return w

    def update_all(self):
        d = self.last_raw_data # [r,p,y,lat,lon,alt,s1,s2,s3,s4]
        if len(d) < 6: return

        r, p, y, lat, lon, alt = d[0:6]
        t_now = time.time()
        dt = t_now - self.last_update_t
        self.last_update_t = t_now

        # Траектория
        if alt > 1.0:
            self.is_flying = True
            self.virtual_dist += 150.0 * dt
        if alt < 0.5 and self.is_flying:
            self.traj_x, self.traj_y, self.traj_y_smooth = [], [], []
            self.virtual_dist = 0.0
            self.is_flying = False

        if self.is_flying or alt > 0.5:
            self.traj_x.append(self.virtual_dist)
            self.traj_y.append(alt)
            window = 10
            avg_y = sum(self.traj_y[-window:]) / len(self.traj_y[-window:])
            self.traj_y_smooth.append(avg_y)

        self.rt_lat.val_label.setText(f"{lat:.7f}")
        self.rt_lon.val_label.setText(f"{lon:.7f}")
        self.rt_alt.val_label.setText(f"{alt:.1f} m")

        idx = self.tabs.currentIndex()
        if idx == 0:
            for i, key in enumerate(['r', 'p', 'y']):
                self.buffer[key] = np.roll(self.buffer[key], -1)
                self.buffer[key][-1] = d[i]
            self.curve_r.setData(self.buffer['r'])
            self.curve_p.setData(self.buffer['p'])
            self.curve_y.setData(self.buffer['y'])

        elif idx == 1: # Real-Time Data
            disp_x = self.traj_x[-2000:]; count = len(disp_x)
            self.curve_raw.setData(disp_x, self.traj_y[-count:])
            if len(self.traj_y_smooth) >= count:
                self.curve_smooth.setData(disp_x, self.traj_y_smooth[-count:])

            # ПЛАВНЫЕ ГРАФИКИ БЕЗ ШУМА
            # Скорость: плавная волна вокруг 120 м/с
            self.speed_data.append(120 + 10 * math.sin(t_now * 0.5))
            # Ускорение: очень плавная синусоида
            self.accel_data.append(2 * math.sin(t_now * 0.3))

            self.alt_history.append(alt)

            # Отрисовка последних 100 точек
            self.curve_speed.setData(self.speed_data[-100:])
            self.curve_accel.setData(self.accel_data[-100:])
            self.curve_alt_plot.setData(self.alt_history[-100:])

            # Обновление текста
            self.ind_bat.val_label.setText(f"{int(self.battery)}%")
            # Убираем рандом из RSSI, делаем стабильным
            self.ind_rssi.val_label.setText("85")

        elif idx == 2:
            if len(self.traj_y) > 0:
                self.curve_an_traj.setData(self.traj_x, self.traj_y)
                if alt < 1.0: self.target_dot.setData([self.traj_x[-1]], [0])
                else: self.target_dot.setData([], [])

            # РЕАЛЬНЫЕ ДАННЫЕ РУЛЕЙ (S1)
            if len(d) >= 7:
                s1_val = d[6]
                if not hasattr(self, 'r_buf'): self.r_buf = []
                self.r_buf.append(s1_val)
                self.curve_rudders.setData(self.r_buf[-150:])

    def on_tab_changed(self, i):
        if self.unity_hwnd:
            if i == 0:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_SHOW)
                QTimer.singleShot(150, self.resize_exe)
            else:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_HIDE)

    def resize_exe(self):
        if self.unity_hwnd and self.exe_container.isVisible():
            win32gui.SetWindowPos(self.unity_hwnd, win32con.HWND_TOP, 0, 0,
                                  self.exe_container.width(), self.exe_container.height(),
                                  win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)

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