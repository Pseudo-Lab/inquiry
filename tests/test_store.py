import json
import os
import selectors
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from inquiry.store import (Store, StoreBusyError, StoreConflictError,
                           StoreCorruptionError, StoreError)


def event(seq=1, inquiry_id="inquiry-1"):
    return {"schema_version": 1, "event_id": f"event-{seq}", "seq": seq,
            "inquiry_id": inquiry_id, "actor": "user", "at": "2026-09-17T00:00:00Z",
            "type": "changes-committed", "changes": [
                {"kind": "FramingStarted", "session_id": f"session-{seq}", "seed": "test"}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.store = Store(self.root)

    def subprocess(self, code):
        return subprocess.run([sys.executable, "-c", code, str(self.root)],
                              capture_output=True, text=True, timeout=10)

    def test_missing_read_creates_nothing_and_append_requires_writer(self):
        self.assertEqual(self.store.read_all(), [])
        self.assertFalse(self.root.exists())
        with self.assertRaises(StoreError):
            self.store.append(event(), expected_seq=0)
        self.assertFalse(self.root.exists())

    def test_relative_root_stays_bound_after_working_directory_changes(self):
        original_cwd = Path.cwd()
        try:
            other_directory = Path(self.temp.name) / "elsewhere"
            other_directory.mkdir()
            os.chdir(self.temp.name)
            relative = Store("project")
            os.chdir(other_directory)
            with relative:
                relative.append(event(), expected_seq=0)
                os.chdir(self.temp.name)
                self.assertEqual(relative.read_all(), [event()])
            self.assertEqual(relative.path, self.store.path)
            self.assertEqual(self.store.read_all(), [event()])
        finally:
            os.chdir(original_cwd)

    def test_roundtrip_fresh_process_and_second_writer(self):
        with self.store:
            self.store.append(event(), expected_seq=0)
            self.assertEqual(self.store.read_all(), [event()])
        self.assertEqual(Store(self.root).read_all(), [event()])
        result = self.subprocess("import sys; from inquiry.store import Store; assert len(Store(sys.argv[1]).read_all()) == 1")
        self.assertEqual(result.returncode, 0, result.stderr)
        with Store(self.root) as second:
            second.append(event(2), expected_seq=1)
        self.assertEqual(len(self.store.read_all()), 2)

    def test_rejections_preserve_bytes(self):
        with self.store:
            self.store.append(event(), expected_seq=0)
            original = self.store.path.read_bytes()
            duplicate = event(2)
            duplicate["event_id"] = event()["event_id"]
            for candidate, expected in [(event(2), 0), (duplicate, 1), (event(2, "other"), 1)]:
                with self.subTest(candidate=candidate), self.assertRaises(StoreConflictError):
                    self.store.append(candidate, expected_seq=expected)
                self.assertEqual(self.store.path.read_bytes(), original)
            invalid = event(2)
            invalid["changes"].append({"kind": "unknown"})
            with self.assertRaises(ValueError):
                self.store.append(invalid, expected_seq=1)
            self.assertEqual(self.store.path.read_bytes(), original)
            invalid_batch = event(2)
            invalid_batch["changes"].append(event()["changes"][0])
            with self.assertRaises(ValueError):
                self.store.append(invalid_batch, expected_seq=1)
            self.assertEqual(self.store.path.read_bytes(), original)

    def test_corruption_is_line_numbered_and_preserved(self):
        valid = json.dumps(event()).encode() + b"\n"
        bad_version = event(2)
        bad_version["schema_version"] = 99
        duplicate = event(2)
        duplicate["event_id"] = event()["event_id"]
        cases = [b"{", b"\xff\n", b"\n", b"[]\n", b'{"a":1,"a":2}\n',
                 b'{"a":NaN}\n']
        cases.extend(json.dumps(row).encode() + b"\n" for row in
                     [bad_version, duplicate, event(1), event(2, "other")])
        self.store.path.parent.mkdir(parents=True)
        for suffix in cases:
            with self.subTest(suffix=suffix):
                raw = valid + suffix
                self.store.path.write_bytes(raw)
                with self.assertRaises(StoreCorruptionError) as raised:
                    self.store.read_all()
                self.assertEqual(raised.exception.line, 2)
                with self.assertRaises(StoreCorruptionError):
                    with self.store:
                        self.store.append(event(2), expected_seq=1)
                self.assertEqual(self.store.path.read_bytes(), raw)
        raw = valid + b"broken\n" + json.dumps(event(3)).encode() + b"\n"
        self.store.path.write_bytes(raw)
        with self.assertRaises(StoreCorruptionError) as raised:
            self.store.read_all()
        self.assertEqual(raised.exception.line, 2)

    def test_writer_and_reader_contention_and_exception_release(self):
        with self.assertRaisesRegex(RuntimeError, "exit"):
            with self.store:
                with self.assertRaises(StoreBusyError):
                    with Store(self.root):
                        pass
                with self.assertRaises(StoreBusyError):
                    Store(self.root).read_all()
                result = self.subprocess("import sys; from inquiry.store import Store, StoreBusyError\ntry:\n with Store(sys.argv[1]): pass\nexcept StoreBusyError: sys.exit(0)\nsys.exit(1)")
                self.assertEqual(result.returncode, 0, result.stderr)
                raise RuntimeError("exit")
        with Store(self.root):
            pass
        self.store.close()
        self.store.close()

    def test_interrupted_entry_releases_lock_and_preserves_exception(self):
        interruption = KeyboardInterrupt("entry interrupted")
        with patch.object(self.store, "_read_unlocked", side_effect=interruption):
            with self.assertRaises(KeyboardInterrupt) as raised:
                with self.store:
                    pass
        self.assertIs(raised.exception, interruption)
        with Store(self.root):
            pass

    def test_killed_writer_releases_lock(self):
        proc = subprocess.Popen([sys.executable, "-c",
            "import sys,time; from inquiry.store import Store\nwith Store(sys.argv[1]):\n print('locked', flush=True)\n time.sleep(30)", str(self.root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=5), "writer did not become ready")
                self.assertEqual(proc.stdout.readline().strip(), "locked")
            with self.assertRaises(StoreBusyError):
                with Store(self.root):
                    pass
        finally:
            proc.kill()
            proc.communicate(timeout=5)
        with Store(self.root):
            pass

    def test_fsync_failure_reports_uncertain_outcome(self):
        with self.store:
            with patch("inquiry.store.os.fsync", side_effect=OSError("disk")):
                with self.assertRaises(StoreError):
                    self.store.append(event(), expected_seq=0)
            self.assertEqual(self.store.read_all(), [event()])
            with self.assertRaises(StoreConflictError):
                self.store.append(event(), expected_seq=0)

    def test_partial_write_is_preserved_and_blocks_later_writes(self):
        path_open = Path.open
        path = self.store.path

        class PartialWrite:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def write(self, record):
                with path_open(path, "ab") as target:
                    target.write(record[:20])
                raise OSError("partial write")

        def open_with_failure(target, mode="r", *args, **kwargs):
            if target == path and mode == "ab":
                return PartialWrite()
            return path_open(target, mode, *args, **kwargs)

        with self.store:
            with patch.object(Path, "open", open_with_failure):
                with self.assertRaises(StoreError):
                    self.store.append(event(), expected_seq=0)
            original = path.read_bytes()
            self.assertTrue(original)
            with self.assertRaises(StoreCorruptionError):
                self.store.append(event(), expected_seq=0)
            self.assertEqual(path.read_bytes(), original)

    def test_forked_child_cannot_reuse_or_release_parent_lock(self):
        code = """
import os, sys
from inquiry.store import Store, StoreError, StoreBusyError
with Store(sys.argv[1]) as store:
    pid = os.fork()
    if pid == 0:
        try:
            store.read_all()
        except StoreError:
            store.close()
            os._exit(0)
        os._exit(1)
    _, status = os.waitpid(pid, 0)
    assert status == 0
    try:
        with Store(sys.argv[1]): pass
    except StoreBusyError:
        pass
    else:
        raise AssertionError('child released parent lock')
"""
        result = self.subprocess(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_other_thread_cannot_use_or_close_writer(self):
        errors = []
        with self.store:
            def intrude():
                for operation in [lambda: self.store.append(event(), expected_seq=0),
                                  self.store.read_all, self.store.close]:
                    try:
                        operation()
                    except StoreError:
                        errors.append(True)
                    else:
                        errors.append(False)
            thread = threading.Thread(target=intrude, daemon=True)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [True, True, True])
            self.store.append(event(), expected_seq=0)
        self.assertEqual(self.store.read_all(), [event()])

    def test_new_directory_and_log_entries_are_synced(self):
        synced = []
        real_fsync = os.fsync

        def record_sync(fd):
            info = os.fstat(fd)
            synced.append((info.st_ino, stat.S_ISDIR(info.st_mode)))
            real_fsync(fd)

        with patch("inquiry.store.os.fsync", side_effect=record_sync):
            with self.store:
                self.store.append(event(), expected_seq=0)
        self.assertIn((self.root.parent.stat().st_ino, True), synced)
        self.assertIn((self.root.stat().st_ino, True), synced)
        self.assertIn((self.store.path.parent.stat().st_ino, True), synced)
        self.assertIn((self.store.path.stat().st_ino, False), synced)


if __name__ == "__main__":
    unittest.main()
