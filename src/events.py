"""Optional JSON-line logs; serialize writes across worker threads."""
import json
import threading
from datetime import datetime, timezone


class Events:
    def __init__(self, access=None, error=None):
        self.lock = threading.Lock()
        self.files = {}
        try:
            for kind, path in (("access", access), ("error", error)):
                if path:
                    self.files[kind] = open(path, "a", encoding="utf-8")
        except BaseException:
            self.close()
            raise
    def emit(self, kind, **fields):
        if kind not in self.files:
            return
        record = {"time": datetime.now(timezone.utc).isoformat(), "kind": kind, **fields}
        with self.lock:
            self.files[kind].write(json.dumps(record) + "\n")
            self.files[kind].flush()
    def close(self):
        for file in self.files.values():
            file.close()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
