"""Byte-budgeted LRU entries, checked against filesystem metadata on every use."""
from collections import OrderedDict
import threading


class FileCache:
    def __init__(self, budget=8388608, max_entry=1048576, max_entries=256):
        if budget < 0 or max_entry < 1 or max_entries < 1:
            raise ValueError("Cache budget must be nonnegative and entry limit positive")
        self.budget, self.max_entry = budget, max_entry
        self.max_entries = max_entries
        self.entries = OrderedDict()
        self.bytes = 0
        self.lock = threading.Lock()

    def get(self, key, signature, loader):
        with self.lock:
            old = self.entries.pop(key, None)
            if old:
                self.bytes -= len(old[1])
                if old[0] == signature:
                    self.entries[key] = old
                    self.bytes += len(old[1])
                    return old[1]
            body = loader()
            if self.budget and len(body) <= min(self.max_entry, self.budget):
                while self.entries and (self.bytes + len(body) > self.budget or len(self.entries) >= self.max_entries):
                    _, evicted = self.entries.popitem(last=False)
                    self.bytes -= len(evicted[1])
                self.entries[key] = (signature, body)
                self.bytes += len(body)
            return body
