"""Strict append-only JSONL persistence with a single POSIX writer."""

from __future__ import annotations

import fcntl
import json
import os
import threading
from pathlib import Path

from inquiry.events import validate_event
from inquiry.replay import ReplayError, replay


class StoreError(Exception):
    """Persistence operation failed."""


class StoreBusyError(StoreError):
    """Another process or store instance holds an incompatible lock."""


class StoreConflictError(StoreError):
    """The proposed append conflicts with the current history."""


class StoreCorruptionError(StoreError):
    """Existing history cannot safely be used or extended."""

    def __init__(self, line: int):
        self.line = line
        super().__init__(f"Invalid event log at line {line}; file preserved")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-finite JSON number")


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Store:
    def __init__(self, root: Path | str):
        self.path = Path(root).resolve() / ".inquiry" / "events.jsonl"
        self._lock = None
        self._pid = None
        self._thread = None

    def _check_pid(self):
        if self._lock is not None and self._pid != os.getpid():
            raise StoreError("An inherited writer context cannot be used after fork")
        if self._lock is not None and self._thread != threading.get_ident():
            raise StoreError("Writer context belongs to another thread")

    def __enter__(self):
        self._check_pid()
        if self._lock is not None:
            raise StoreError("Writer context is already active")
        lock = None
        try:
            missing = []
            directory = self.path.parent
            while not directory.exists():
                missing.append(directory)
                directory = directory.parent
            self.path.parent.mkdir(parents=True, exist_ok=True)
            for directory in reversed(missing):
                _sync_directory(directory.parent)
            lock = (self.path.parent / "writer.lock").open("a+b")
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock = lock
            self._pid = os.getpid()
            self._thread = threading.get_ident()
            self._read_unlocked()
            return self
        except BlockingIOError:
            if lock is not None:
                lock.close()
            raise StoreBusyError("Event store is busy") from None
        except BaseException as error:
            if self._lock is not None:
                self.close()
            elif lock is not None:
                lock.close()
            if isinstance(error, OSError):
                raise StoreError("Cannot open event store") from None
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self._lock is not None and self._pid == os.getpid():
            self._check_pid()
        lock, owner = self._lock, self._pid
        self._lock = self._pid = self._thread = None
        if lock is not None:
            try:
                # A child must not unlock its parent's shared open-file description.
                if owner == os.getpid():
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            finally:
                lock.close()

    def _read_unlocked(self):
        try:
            source = self.path.open("rb")
        except FileNotFoundError:
            return []
        events = []
        with source:
            for line, raw in enumerate(source, 1):
                try:
                    if not raw.endswith(b"\n"):
                        raise ValueError("Unterminated record")
                    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                       parse_constant=_invalid_constant)
                    events.append(validate_event(value))
                except (ValueError, TypeError, RecursionError):
                    raise StoreCorruptionError(line) from None
        try:
            replay(events)
        except ReplayError as error:
            raise StoreCorruptionError(error.line) from None
        return events

    def read_all(self) -> list[dict]:
        self._check_pid()
        reader = None
        try:
            if self._lock is None:
                try:
                    reader = (self.path.parent / "writer.lock").open("rb")
                except FileNotFoundError:
                    pass
                if reader is not None:
                    fcntl.flock(reader.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            return self._read_unlocked()
        except BlockingIOError:
            raise StoreBusyError("Event store is busy") from None
        except OSError:
            raise StoreError("Cannot read event store") from None
        finally:
            if reader is not None:
                reader.close()

    def append(self, event: dict, expected_seq: int):
        self._check_pid()
        if self._lock is None:
            raise StoreError("Append requires an active writer context")
        if type(expected_seq) is not int or expected_seq < 0:
            raise ValueError("expected_seq must be a nonnegative integer")
        candidate = validate_event(event)
        try:
            existing = self._read_unlocked()
            if expected_seq != len(existing) or candidate["seq"] != expected_seq + 1:
                raise StoreConflictError("Event sequence conflicts with current head")
            if any(row["event_id"] == candidate["event_id"] for row in existing):
                raise StoreConflictError("Event identifier already exists")
            if existing and candidate["inquiry_id"] != existing[0]["inquiry_id"]:
                raise StoreConflictError("Inquiry identifier conflicts with current history")
            replay([*existing, candidate])
            record = (json.dumps(candidate, ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":")) + "\n").encode("utf-8")
            with self.path.open("ab") as target:
                if target.write(record) != len(record):
                    raise OSError("Incomplete write")
                target.flush()
                os.fsync(target.fileno())
            # Sync even on later appends, so a prior uncertain directory sync
            # cannot be silently accepted as durable on a successful retry.
            _sync_directory(self.path.parent)
        except OSError:
            # The disk may already contain all or part of the record. Never retry
            # blindly, truncate, or promise rollback after an I/O failure.
            raise StoreError("Append I/O failed; outcome uncertain; inspect history before retrying") from None
