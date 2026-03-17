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
                             QTabWidget, QVBoxLayout, QHBoxLayout, QSizePolicy)
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
                    pitch = parts[1]
                    yaw = parts[2]
                    roll = parts[0]
                    out_sock.sendto(f"{pitch:.2f},{yaw:.2f},{roll:.2f}".encode(), unity_addr)
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
        self.traj_x, self.traj_y = [], []
        self.speed_data, self.accel_data, self.alt_history = [], [], []
        self.r_buf = []
        self.virtual_dist = 0.0
        self.last_update_t = time.time()
        self.is_flying = False
        self.last_raw_data = [0.0] * 10
        self.max_pts = 150
        self.buffer = {'r': np.zeros(self.max_pts), 'p': np.zeros(self.max_pts), 'y': np.zeros(self.max_pts)}
        self.battery = 98.0
        self.unity_hwnd = None

        # Параметры цели
        self.target_x = 16000
        self.start_time = time.time() # Фиксируем время старта для прогресса
        self.start_deviation = 100.0

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        pg.setConfigOption('background', '#1e1e1e')
        pg.setConfigOption('foreground', '#dcdcdc')

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
        m_layout.setContentsMargins(5, 5, 5, 5)
        m_layout.setSpacing(10)

        m_left = QVBoxLayout()
        m_ind_row = QHBoxLayout()
        self.rt_lat = self.create_indicator("LATITUDE", "#FF4444")
        self.rt_lon = self.create_indicator("LONGITUDE", "#44FF44")
        self.rt_alt = self.create_indicator("ALTITUDE", "#4444FF")

        m_ind_row.addWidget(self.rt_lat)
        m_ind_row.addWidget(self.rt_lon)
        m_ind_row.addWidget(self.rt_alt)
        m_left.addLayout(m_ind_row)

        self.pw_r, self.curve_r = self.create_plot("ROLL", "#FF4444")
        self.pw_p, self.curve_p = self.create_plot("PITCH", "#44FF44")
        self.pw_y, self.curve_y = self.create_plot("YAW", "#4444FF")

        m_left.addWidget(self.pw_r)
        m_left.addWidget(self.pw_p)
        m_left.addWidget(self.pw_y)

        m_layout.addLayout(m_left, stretch=3)

        self.exe_container = QWidget()
        self.exe_container.setStyleSheet("background: #000; border: 1px solid #444;")
        self.exe_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        m_layout.addWidget(self.exe_container, stretch=7)

        self.tabs.addTab(self.mission_tab, "Mission")

    def init_rt_data_tab(self):
        self.rt_data_tab = QWidget()
        rd_layout = QHBoxLayout(self.rt_data_tab)
        rd_left = QVBoxLayout()
        self.pw_traj = pg.PlotWidget(title="Trajectory Analysis")
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
        self.target_dot_main = self.pw_an_traj.plot(pen=None, symbol='o', symbolBrush='r', symbolSize=12)
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

        an_right_col = QVBoxLayout()
        self.pw_corr_zoom = pg.PlotWidget(title="Коррекция траектории (активный участок + GPS)")
        self.pw_corr_zoom.showGrid(x=True, y=True, alpha=0.3)
        self.curve_corr_zoom = self.pw_corr_zoom.plot(pen=pg.mkPen(color='#00FF00', width=2))
        an_right_col.addWidget(self.pw_corr_zoom)

        self.pw_rudders_zoom = pg.PlotWidget(title="Работа рулей при коррекции (зум)")
        self.pw_rudders_zoom.showGrid(x=True, y=True, alpha=0.3)
        self.pw_rudders_zoom.setYRange(-10, 10)
        self.pw_rudders_zoom.addLine(y=7.5, pen=limit_pen)
        self.pw_rudders_zoom.addLine(y=-7.5, pen=limit_pen)
        self.curve_rudders_zoom = self.pw_rudders_zoom.plot(pen=pg.mkPen(color='#44FF44', width=1.5))
        an_right_col.addWidget(self.pw_rudders_zoom)

        self.pw_precision = pg.PlotWidget(title="Точность достижения цели (зум)")
        self.pw_precision.showGrid(x=True, y=True, alpha=0.3)
        self.pw_precision.setXRange(0, 18000)
        self.pw_precision.setYRange(-10, 150)
        self.pw_precision.addLine(y=0, pen=pg.mkPen(color='#555', style=Qt.PenStyle.DashLine))
        self.curve_precision = self.pw_precision.plot(pen=pg.mkPen(color='#0078d7', width=2))
        self.precision_dot = self.pw_precision.plot(pen=None, symbol='o', symbolBrush='g', symbolSize=12)
        self.precision_dot.setData([self.target_x], [0])

        an_right_col.addWidget(self.pw_precision)
        an_layout.addLayout(an_right_col, stretch=2)
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
    def calculate_horizontal_dist(self, lat, lon):
        if not hasattr(self, 'home_lat'):
            if lat != 0 and lon != 0:
                self.home_lat, self.home_lon = lat, lon
            return 0.0

        # 1 градус широты ~ 111139 метров
        dx = (lat - self.home_lat) * 111139.0
        # Длина градуса долготы зависит от широты
        dy = (lon - self.home_lon) * 111139.0 * math.cos(math.radians(lat))

        return math.sqrt(dx**2 + dy**2)
    def update_all(self):
        d = self.last_raw_data
        if not d: return

        # 1. Извлекаем данные
        # d[0,1,2] - RPY, d[3,4] - GPS, d[5] - Alt, d[6] - Rudder
        r, p, y = d[0], d[1], d[2]
        lat, lon, alt = d[3], d[4], d[5]

        # 2. Обновляем Mission (Roll/Pitch/Yaw) — работает ВСЕГДА
        self.refresh_mission_charts(r, p, y)

        # 3. Честный расчет траектории (метры от старта)
        dist = self.calculate_horizontal_dist(lat, lon)

        # Добавляем точку, только если есть реальные данные (не нули)
        if lat != 0 and lon != 0:
            self.traj_x.append(dist)
            self.traj_y.append(alt)
            # Ограничиваем историю для производительности
            if len(self.traj_x) > 5000:
                self.traj_x.pop(0)
                self.traj_y.pop(0)

        # 4. Обновляем данные симуляции (синусоиды)
        self.update_simulated_data()

        # 5. Отрисовка активной вкладки
        idx = self.tabs.currentIndex()
        if idx == 1:
            self.draw_realtime_trajectory()
        elif idx == 2:
            self.draw_analyze_trajectory(d[6] if len(d) > 6 else 0.0)

        # 6. Обновление текста (тот самый метод)
        self.update_labels(lat, lon, alt)
    def update_labels(self, lat, lon, alt):
        """Обновление текстовых индикаторов координат и высоты"""
        self.rt_lat.val_label.setText(f"{lat:.7f}")
        self.rt_lon.val_label.setText(f"{lon:.7f}")
        self.rt_alt.val_label.setText(f"{alt:.2f} m")

    def update_simulated_data(self):
        """Расчет синусоид скорости и ускорения (по ТЗ)"""
        t = time.time()
        self.speed_data.append(120 + 15 * math.sin(t * 0.5))
        self.accel_data.append(2 + 0.5 * math.cos(t * 0.8))

        # Держим размер буфера
        self.speed_data = self.speed_data[-self.max_pts:]
        self.accel_data = self.accel_data[-self.max_pts:]

    def refresh_mission_charts(self, r, p, y):
        """Графики на первой вкладке, которые нельзя прерывать"""
        for key, val in zip(['r', 'p', 'y'], [r, p, y]):
            self.buffer[key] = np.roll(self.buffer[key], -1)
            self.buffer[key][-1] = val

        self.curve_r.setData(self.buffer['r'])
        self.curve_p.setData(self.buffer['p'])
        self.curve_y.setData(self.buffer['y'])

    def draw_realtime_trajectory(self):
        """Вкладка Real-Time Data: профиль полета + синусоиды"""
        # Траектория: X - метры, Y - высота
        self.curve_raw.setData(self.traj_x, self.traj_y)

        # Синусоиды (имитация скорости/ускорения для ТЗ)
        t = time.time()
        self.speed_data.append(120 + 15 * math.sin(t * 0.5))
        self.accel_data.append(2 + 0.5 * math.cos(t * 0.8))
        self.curve_speed.setData(self.speed_data[-self.max_pts:])
        self.curve_accel.setData(self.accel_data[-self.max_pts:])

    def draw_analyze_trajectory(self, rudder_val):
        """Вкладка Analyze: прямая линия под углом к цели"""
        # 1. Основной график и зум траектории (реальные данные)
        self.curve_an_traj.setData(self.traj_x, self.traj_y)
        if len(self.traj_x) > 0:
            self.curve_corr_zoom.setData(self.traj_x[-100:], self.traj_y[-100:])

        # 2. Работа рулей (дублируем на оба графика)
        self.r_buf.append(rudder_val)
        self.r_buf = self.r_buf[-self.max_pts:]
        self.curve_rudders.setData(self.r_buf)
        self.curve_rudders_zoom.setData(self.r_buf)

        # 3. ЛОГИКА ДОСТИЖЕНИЯ ЦЕЛИ (Синяя линия под углом)
        # Параметры: 10 минут (600 сек), цель на 16000м, старт на высоте 100м
        elapsed = time.time() - self.start_time
        duration = 600.0
        start_alt = 100.0

        # Текущий прогресс (от 0.0 до 1.0)
        progress = min(elapsed / duration, 1.0)

        # Текущие координаты "носа" синей линии
        current_x = progress * self.target_x
        current_y = start_alt * (1 - progress) # Снижение со 100 до 0

        # Рисуем прямую линию от точки старта (0, 100) до текущей позиции
        line_x = [0, current_x]
        line_y = [start_alt, current_y]

        self.curve_precision.setData(line_x, line_y)

        # (Опционально) Если хочешь, чтобы точка текущего положения тоже двигалась:
        # self.precision_dot_dynamic.setData([current_x], [current_y])

    def update_simulated_plots(self):
        """Метод для синусоид Speed/Accel по твоему ТЗ"""
        t = time.time()
        self.speed_data.append(120 + 15 * math.sin(t * 0.5))
        self.accel_data.append(2 + 0.5 * math.cos(t * 0.8))
        self.speed_data = self.speed_data[-self.max_pts:]
        self.accel_data = self.accel_data[-self.max_pts:]
        self.curve_speed.setData(self.speed_data)
        self.curve_accel.setData(self.accel_data)

    def on_tab_changed(self, i):
        if self.unity_hwnd:
            if i == 0:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_SHOW)
                QTimer.singleShot(150, self.resize_exe)
            else:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_HIDE)

    def resize_exe(self):
        if self.unity_hwnd and self.exe_container.isVisible():
            rect = self.exe_container.rect()
            w, h = rect.width(), rect.height()
            win32gui.SetWindowPos(self.unity_hwnd, win32con.HWND_TOP, 0, 0, w, h,
                                  win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW)

    def launch_exe(self):
        load_dotenv()
        t = os.getenv("MODEL_NAME", "My project")
        p = os.path.join(os.getcwd(), "model", f"{t}.exe")
        if os.path.exists(p):
            subprocess.Popen([p, "-parentHWND", str(int(self.exe_container.winId())), "-screen-fullscreen", "0"],
                             cwd=os.path.dirname(p))
            for _ in range(60):
                QApplication.processEvents()
                h = win32gui.FindWindow(None, t)
                if h:
                    self.unity_hwnd = h
                    style = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
                    win32gui.SetWindowLong(h, win32con.GWL_STYLE, style & ~win32con.WS_OVERLAPPEDWINDOW)
                    win32gui.SetParent(h, int(self.exe_container.winId()))
                    self.resize_exe(); break
                time.sleep(0.5)

    def resizeEvent(self, e): super().resizeEvent(e); QTimer.singleShot(50, self.resize_exe)
    def closeEvent(self, e):
        if hasattr(self, 'udp'): self.udp.stop(); self.udp.wait()
        os.system(f'taskkill /F /IM "My project.exe" /T')
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("Fusion")
    win = FlightControlApp(); win.show(); sys.exit(app.exec())