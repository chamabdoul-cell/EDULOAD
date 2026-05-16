from datetime import datetime


class ResponseCache:
    def __init__(self, ttl: int = 300):
        self._store: dict = {}
        self.ttl = ttl

    def get(self, key: str):
        entry = self._store.get(key)
        if entry:
            cached_at, result = entry
            if (datetime.now() - cached_at).seconds < self.ttl:
                return result
        return None

    def set(self, key: str, value):
        self._store[key] = (datetime.now(), value)

    def clear(self):
        self._store.clear()
