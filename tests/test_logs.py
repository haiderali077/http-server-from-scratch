import json
import tempfile
import unittest
from pathlib import Path
from tests.support import RunningServer, request_bytes
from tests.upstream_support import RawUpstream


class LogTests(unittest.TestCase):
    def test_success_and_upstream_error_records(self):
        with tempfile.TemporaryDirectory() as directory:
            access, error = Path(directory) / "access.jsonl", Path(directory) / "error.jsonl"
            with RawUpstream(b"bad\r\n\r\n") as backend, RunningServer("--upstream", backend.url, "--access-log", str(access), "--error-log", str(error)) as server:
                server.exchange(request_bytes("/health?private=value"))
                server.exchange(request_bytes("/api/x"))
            records = [json.loads(line) for line in access.read_text().splitlines()]
            self.assertEqual([r["status"] for r in records], [200, 502])
            self.assertGreaterEqual(records[1]["upstream_seconds"], 0)
            self.assertNotIn("private=value", access.read_text())
            self.assertEqual(json.loads(error.read_text().splitlines()[-1])["status"], 502)
