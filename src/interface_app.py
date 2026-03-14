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
        self.start_deviation = 100.0 # Начальное отклонение для отрисовки прямой

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
        # Минимальные отступы, чтобы использовать всё пространство
        m_layout.setContentsMargins(5, 5, 5, 5)
        m_layout.setSpacing(10)

        # --- ЛЕВАЯ ПАНЕЛЬ (Индикаторы и Графики) ---
        m_left = QVBoxLayout()

        # Создаем индикаторы (теперь они точно будут существовать для update_all)
        m_ind_row = QHBoxLayout()
        self.rt_lat = self.create_indicator("LATITUDE", "#FF4444")
        self.rt_lon = self.create_indicator("LONGITUDE", "#44FF44")
        self.rt_alt = self.create_indicator("ALTITUDE", "#4444FF")

        m_ind_row.addWidget(self.rt_lat)
        m_ind_row.addWidget(self.rt_lon)
        m_ind_row.addWidget(self.rt_alt)
        m_left.addLayout(m_ind_row)

        # Создаем графики углов
        self.pw_r, self.curve_r = self.create_plot("ROLL", "#FF4444")
        self.pw_p, self.curve_p = self.create_plot("PITCH", "#44FF44")
        self.pw_y, self.curve_y = self.create_plot("YAW", "#4444FF")

        m_left.addWidget(self.pw_r)
        m_left.addWidget(self.pw_p)
        m_left.addWidget(self.pw_y)

        # Добавляем левую панель в основной лейаут (30% ширины)
        m_layout.addLayout(m_left, stretch=3)

        # --- ПРАВАЯ ПАНЕЛЬ (Unity) ---
        self.exe_container = QWidget()
        self.exe_container.setStyleSheet("background: #000; border: 1px solid #444;")

        # Важно: устанавливаем политику расширения
        self.exe_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Добавляем контейнер напрямую (70% ширины)
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

        # 3 График: Точность (Прямая линия)
        self.pw_precision = pg.PlotWidget(title="Точность достижения цели (зум)")
        self.pw_precision.showGrid(x=True, y=True, alpha=0.3)
        self.pw_precision.setXRange(0, 18000)
        self.pw_precision.setYRange(-10, 150)
        # Уровень цели
        self.pw_precision.addLine(y=0, pen=pg.mkPen(color='#555', style=Qt.PenStyle.DashLine))
        self.curve_precision = self.pw_precision.plot(pen=pg.mkPen(color='#0078d7', width=2))
        # Зеленая точка (Постоянно видна на 16000, 0)
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

    def update_all(self):
        d = self.last_raw_data
        if len(d) < 6: return
        r, p, y, lat, lon, alt = d[0:6]
        t_now = time.time()
        dt = t_now - self.last_update_t
        self.last_update_t = t_now

        if alt > 1.0:
            self.is_flying = True
            self.virtual_dist += 150.0 * dt
        if alt < 0.5 and self.is_flying:
            self.traj_x, self.traj_y, self.r_buf = [], [], []
            self.virtual_dist = 0.0
            self.is_flying = False

        if self.is_flying or alt > 0.5:
            self.traj_x.append(self.virtual_dist)
            self.traj_y.append(alt)
            if len(d) >= 7:
                if not hasattr(self, 'r_buf'): self.r_buf = []
                self.r_buf.append(d[6])

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

        elif idx == 1:
            self.curve_raw.setData(self.traj_x, self.traj_y)
            self.speed_data.append(120 + 10 * math.sin(t_now * 0.5))
            self.accel_data.append(2 * math.sin(t_now * 0.3))
            self.alt_history.append(alt)
            self.curve_speed.setData(self.speed_data[-100:])
            self.curve_accel.setData(self.accel_data[-100:])
            self.curve_alt_plot.setData(self.alt_history[-100:])
            self.ind_bat.val_label.setText(f"{int(self.battery)}%")
            self.ind_rssi.val_label.setText("85")

        elif idx == 2:
            if len(self.traj_y) > 0:
                self.curve_an_traj.setData(self.traj_x, self.traj_y)
                self.curve_corr_zoom.setData(self.traj_x[-100:], self.traj_y[-100:])

                if hasattr(self, 'r_buf') and self.r_buf:
                    self.curve_rudders.setData(self.r_buf[-150:])
                    self.curve_rudders_zoom.setData(self.r_buf[-50:])

                # Прямая линия точности
                curr_x = self.traj_x[-1]
                # Рассчитываем текущее отклонение по прямой: от start_deviation до 0 в точке target_x
                if curr_x < self.target_x:
                    ratio = (self.target_x - curr_x) / self.target_x
                    curr_dev = self.start_deviation * ratio
                else:
                    curr_dev = 0

                # Рисуем линию от начала (0, start_deviation) до текущей точки
                # Это создает эффект "прямого наведения"
                self.curve_precision.setData([0, curr_x], [self.start_deviation, curr_dev])

                if alt < 1.0: self.target_dot_main.setData([curr_x], [0])

    def on_tab_changed(self, i):
        if self.unity_hwnd:
            if i == 0:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_SHOW)
                QTimer.singleShot(150, self.resize_exe)
            else:
                win32gui.ShowWindow(self.unity_hwnd, win32con.SW_HIDE)


    def resize_exe(self):
        if self.unity_hwnd and self.exe_container.isVisible():
            # Получаем реальный размер, который PyQt выделил под виджет
            rect = self.exe_container.geometry()
            w, h = rect.width(), rect.height()

            # Коэффициент "перекрытия".
            # Если полоски по 5% с каждой стороны, увеличиваем ширину на 10%
            # Попробуй менять эти значения, пока полоски не уйдут
            zoom_factor = 1.05

            new_w = int(w * zoom_factor)
            new_h = int(h * zoom_factor)

            # Центрируем увеличенное окно Unity относительно контейнера
            off_x = (new_w - w) // 2
            off_y = (new_h - h) // 2

            win32gui.SetWindowPos(
                self.unity_hwnd,
                win32con.HWND_TOP,
                -off_x, -off_y,
                new_w, new_h,
                win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED
            )
            # Отправляем сообщение о новом размере
            win32gui.SendMessage(self.unity_hwnd, win32con.WM_SIZE, 0, (new_h << 16) | new_w)

    def launch_exe(self):
        load_dotenv()
        t = os.getenv("MODEL_NAME", "My project")
        p = os.path.join(os.getcwd(), "model", f"{t}.exe")
        if os.path.exists(p):
            # Запускаем Unity с аргументами, запрещающими выбор разрешения и фиксированный Aspect Ratio
            # -screen-fullscreen 0 (в окне)
            # -parentHWND ... (можно пробовать передать сразу, но мы делаем через SetParent)
            subprocess.Popen([p, "-screen-fullscreen", "0"], cwd=os.path.dirname(p))

            for _ in range(40):
                QApplication.processEvents()
                h = win32gui.FindWindow(None, t) or win32gui.FindWindow("UnityWndClass", None)
                if h:
                    self.unity_hwnd = h
                    win32gui.SetParent(h, int(self.exe_container.winId()))

                    # Убираем рамки окна Unity
                    style = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
                    win32gui.SetWindowLong(h, win32con.GWL_STYLE, style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME)

                    # Вызываем resize сразу после захвата
                    self.resize_exe()
                    break
                time.sleep(0.5)

    def resizeEvent(self, e): super().resizeEvent(e); QTimer.singleShot(50, self.resize_exe)
    def closeEvent(self, e):
        """Вызывается при закрытии окна"""
        print("Завершение работы системы...")

        # Останавливаем сетевой мост
        if hasattr(self, 'udp'):
            self.udp.stop()
            self.udp.wait() # Ждем завершения потока

        # Убиваем процесс Unity
        try:
            # /F - принудительно, /T - со всеми дочерними (handler), /IM - по имени
            os.system(f'taskkill /F /IM "My project.exe" /T')
        except:
            pass

        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("Fusion")
    win = FlightControlApp(); win.show(); sys.exit(app.exec())