import re

class TelemetryParser:
    def __init__(self):
        # Регулярки под твой формат
        self.re_quat = r"quat=\[([-?0-9.]+) ([-?0-9.]+) ([-?0-9.]+) ([-?0-9.]+)\]"
        self.re_coords = r"lat=([-?0-9.]+) lon=([-?0-9.]+)"
        self.re_alt = r"alt=([-?0-9.]+)m"

        # Внутреннее состояние (последние известные значения)
        self.state = {
            'quat': [1.0, 0.0, 0.0, 0.0],
            'lat': 0.0,
            'lon': 0.0,
            'alt': 0.0
        }

    def parse(self, text):
        updated = False

        # Проверяем, есть ли в текущей строке что-то полезное
        q = re.search(self.re_quat, text)
        c = re.search(self.re_coords, text)
        a = re.search(self.re_alt, text)

        if q:
            self.state['quat'] = [float(q.group(i)) for i in range(1, 5)]
            updated = True
        if c:
            self.state['lat'] = float(c.group(1))
            self.state['lon'] = float(c.group(2))
            updated = True
        if a:
            self.state['alt'] = float(a.group(1))
            updated = True

        # Если в строке был хоть один из наших параметров — отдаем весь словарь
        if updated:
            return self.state

        return None