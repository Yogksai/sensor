# src/parser.py
import re

class TelemetryParser:
    def __init__(self):
        self.re_quat = r"quat=\[([-?0-9.]+) ([-?0-9.]+) ([-?0-9.]+) ([-?0-9.]+)\]"
        self.re_coords = r"lat=([-?0-9.]+) lon=([-?0-9.]+)"
        self.re_alt = r"alt=([-?0-9.]+)m"
        # НОВОЕ: Регулярка для рулей S1-S4
        self.re_servos = r"S\(deg\): S1=([-?0-9.]+) S2=([-?0-9.]+) S3=([-?0-9.]+) S4=([-?0-9.]+)"

        self.state = {
            'quat': [1.0, 0.0, 0.0, 0.0],
            'lat': 0.0, 'lon': 0.0, 'alt': 0.0,
            'servos': [0.0, 0.0, 0.0, 0.0] # Начальное состояние рулей
        }

    def parse(self, text):
        updated = False
        q = re.search(self.re_quat, text)
        c = re.search(self.re_coords, text)
        a = re.search(self.re_alt, text)
        s = re.search(self.re_servos, text)

        if q:
            self.state['quat'] = [float(q.group(i)) for i in range(1, 5)]
            updated = True
        if c:
            self.state['lat'] = float(c.group(1)); self.state['lon'] = float(c.group(2))
            updated = True
        if a:
            self.state['alt'] = float(a.group(1))
            updated = True
        if s:
            self.state['servos'] = [float(s.group(i)) for i in range(1, 5)]
            updated = True

        return self.state if updated else None