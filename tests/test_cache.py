import unittest
from concurrent.futures import ThreadPoolExecutor
import gzip
from tests.support import RunningServer, request_bytes
from src.file_cache import FileCache


class CacheTests(unittest.TestCase):
    def test_zero_size_entry_limit_and_disabled_storage(self):
        cache = FileCache(10, 10, 2)
        for name in ("a", "b", "c"):
            cache.get(name, 1, lambda: b"")
        self.assertEqual(len(cache.entries), 2)
        disabled = FileCache(0)
        disabled.get("empty", 1, lambda: b"")
        self.assertEqual(len(disabled.entries), 0)

    def test_concurrent_fill_accounting(self):
        cache = FileCache(100)
        calls = []
        def load():
            calls.append(1)
            return b"payload"
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: cache.get("key", 1, load), range(100)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.bytes, 7)
        self.assertTrue(all(r == b"payload" for r in replies))

    def test_gzip_invalidation_deletion_and_large_stream(self):
        with RunningServer("--cache-bytes", "64") as server:
            path = server.root / "index.html"
            request = request_bytes(headers="Accept-Encoding: gzip\r\n")
            first = server.exchange(request)
            self.assertEqual(gzip.decompress(first.split(b"\r\n\r\n", 1)[1]), b"hello")
            path.write_bytes(b"new content")
            second = server.exchange(request)
            self.assertEqual(gzip.decompress(second.split(b"\r\n\r\n", 1)[1]), b"new content")
            path.unlink()
            self.assertIn(b"404 Not Found", server.exchange(request))
            large = b"x" * (2 * 1048576)
            (server.root / "large.png").write_bytes(large)
            result = server.exchange(request_bytes("/large.png"))
            self.assertEqual(result.split(b"\r\n\r\n", 1)[1], large)
            self.assertIn(b"406 Not Acceptable", server.exchange(request_bytes("/large.png", headers="Accept-Encoding: gzip, identity;q=0\r\n")))

    def test_hit_invalidation_and_lru_budget(self):
        cache = FileCache(6, 4)
        def unexpected():
            self.fail("cache hit must avoid a load")
        cache.get("a", 1, lambda: b"aaa")
        cache.get("b", 1, lambda: b"bbb")
        self.assertEqual(cache.get("a", 1, unexpected), b"aaa")
        cache.get("c", 1, lambda: b"ccc")
        self.assertNotIn("b", cache.entries)
        self.assertEqual(cache.bytes, 6)
        self.assertEqual(cache.get("a", 2, lambda: b"new"), b"new")
        cache.get("large", 1, lambda: b"large")
        self.assertNotIn("large", cache.entries)
        self.assertLessEqual(cache.bytes, cache.budget)
