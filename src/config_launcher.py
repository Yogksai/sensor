import sys
import os
import serial.tools.list_ports
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QPushButton, QFrame,
                             QApplication)
from PyQt6.QtCore import Qt
from dotenv import load_dotenv, set_key

ENV_PATH = "../.env"

class LauncherWindow(QDialog):
    def __init__(self):
        super().__init__()
        # Загружаем переменные, если файл существует
        if os.path.exists(ENV_PATH):
            load_dotenv(ENV_PATH)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FCS Startup Manager")
        self.setFixedSize(400, 350)
        # Убираем кнопку "?" из заголовка окна
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout()

        # --- СЕКЦИЯ ПОРТА ---
        layout.addWidget(QLabel("<b>Доступные COM-порты:</b>"))
        self.port_combo = QComboBox()
        # ВАЖНО: Мы НЕ вызываем здесь refresh_ports, пока не создана кнопка запуска
        layout.addWidget(self.port_combo)

        btn_refresh = QPushButton("Обновить список портов")
        btn_refresh.clicked.connect(self.refresh_ports)
        layout.addWidget(btn_refresh)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # --- СЕКЦИЯ UDP ПОРТОВ ---
        layout.addWidget(QLabel("<b>Сетевые настройки (UDP):</b>"))

        udp_layout = QHBoxLayout()

        # Unity Port
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("Unity Port:"))
        self.unity_in = QLineEdit(os.getenv("UNITY_PORT", "5005"))
        v1.addWidget(self.unity_in)
        udp_layout.addLayout(v1)

        # UI Port
        v2 = QVBoxLayout()
        v2.addWidget(QLabel("UI Port:"))
        self.ui_in = QLineEdit(os.getenv("UI_PORT", "5006"))
        v2.addWidget(self.ui_in)
        udp_layout.addLayout(v2)

        layout.addLayout(udp_layout)

        # --- МОДЕЛЬ ---
        layout.addWidget(QLabel("<b>Имя модели:</b>"))
        self.model_in = QLineEdit(os.getenv("MODEL_NAME", "Drone_v1"))
        layout.addWidget(self.model_in)

        layout.addStretch()

        # --- КНОПКА ЗАПУСКА ---
        # Теперь создаем кнопку ЗАДОЛГО до того, как refresh_ports к ней обратится
        self.btn_launch = QPushButton("ЗАПУСТИТЬ СИСТЕМУ")
        self.btn_launch.setFixedHeight(40)
        self.btn_launch.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.btn_launch.clicked.connect(self.accept_settings)
        layout.addWidget(self.btn_launch)

        self.setLayout(layout)

        # --- ФИНАЛЬНЫЙ ШАГ ---
        # Теперь, когда кнопка self.btn_launch существует, можно обновлять порты
        self.refresh_ports()

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()

        if not ports:
            self.port_combo.addItem("Порты не найдены")
            self.btn_launch.setEnabled(False) # Кнопка блокируется, если нет портов
            self.btn_launch.setStyleSheet("background-color: #95a5a6; color: white;")
        else:
            for p in ports:
                self.port_combo.addItem(f"{p.device} ({p.description})", p.device)
            self.btn_launch.setEnabled(True) # Кнопка активна
            self.btn_launch.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")

    def accept_settings(self):
        # Словарь дефолтных значений
        defaults = {
            "UNITY_PORT": "5005",
            "UI_PORT": "5006",
            "MODEL_NAME": "Myproject"
        }

        # Проверка и сохранение
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f: f.write("")

        # Для порта COM
        port_data = self.port_combo.currentData()
        if port_data:
            set_key(ENV_PATH, "SERIAL_PORT", str(port_data))

        # Для текстовых полей: если пусто, берем из defaults
        u_port = self.unity_in.text().strip() or defaults["UNITY_PORT"]
        ui_port = self.ui_in.text().strip() or defaults["UI_PORT"]
        m_name = self.model_in.text().strip() or defaults["MODEL_NAME"]

        set_key(ENV_PATH, "UNITY_PORT", u_port)
        set_key(ENV_PATH, "UI_PORT", ui_port)
        set_key(ENV_PATH, "MODEL_NAME", m_name)

        self.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    launcher = LauncherWindow()

    if launcher.exec() == QDialog.DialogCode.Accepted:
        print("--- Настройки успешно сохранены ---")
        load_dotenv(ENV_PATH)
        print(f"Выбран порт: {os.getenv('SERIAL_PORT')}")
        print(f"Unity Port: {os.getenv('UNITY_PORT')}")
    else:
        print("Выход без сохранения.")

    sys.exit()