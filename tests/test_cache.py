import unittest
from src.file_cache import FileCache


class CacheTests(unittest.TestCase):
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
