"""Terminal editing regressions; subprocesses read only synthetic input."""
import importlib.util
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from inquiry.interactive import _Console


class InputRoutingTests(unittest.TestCase):
    def test_real_terminal_enables_readline_before_input(self):
        with patch('sys.stdin.isatty', return_value=True), \
             patch('sys.stdout.isatty', return_value=True), \
             patch('builtins.input', return_value='답변') as read, \
             patch('importlib.import_module') as load:
            def assert_ready(prompt):
                load.assert_called_once_with('readline')
                return '답변'
            read.side_effect = assert_ready
            self.assertEqual(_Console(None, None).text('입력 > '), '답변')

    def test_redirected_streams_keep_plain_input(self):
        for stdin_tty, stdout_tty in ((False, False), (False, True), (True, False)):
            with self.subTest(stdin_tty=stdin_tty, stdout_tty=stdout_tty), \
                 patch('sys.stdin.isatty', return_value=stdin_tty), \
                 patch('sys.stdout.isatty', return_value=stdout_tty), \
                 patch('builtins.input', return_value='piped answer'), \
                 patch('importlib.import_module') as load:
                self.assertEqual(_Console(None, None).text('입력 > '), 'piped answer')
                load.assert_not_called()

    def test_injected_reader_is_unchanged(self):
        with patch('sys.stdin.isatty', return_value=True), \
             patch('sys.stdout.isatty', return_value=True), \
             patch('importlib.import_module') as load:
            self.assertEqual(_Console(lambda prompt: 'fake answer', None).text('> '), 'fake answer')
            load.assert_not_called()

    def test_missing_readline_does_not_silently_use_broken_terminal_input(self):
        with patch('sys.stdin.isatty', return_value=True), \
             patch('sys.stdout.isatty', return_value=True), \
             patch('builtins.input') as read, \
             patch('importlib.import_module', side_effect=ImportError('private detail')):
            with self.assertRaisesRegex(ValueError, 'readline') as caught:
                _Console(None, None).text('> ')
            self.assertNotIn('private detail', str(caught.exception))
            read.assert_not_called()


@unittest.skipUnless(os.name == 'posix' and importlib.util.find_spec('readline'),
                     'POSIX terminal and Python readline are required')
class TerminalEraseTests(unittest.TestCase):
    def _erase_and_retype(self, text, columns=80):
        import fcntl
        import pty
        import termios
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, columns, 0, 0))
        # Isolate line-editor configuration without reading user inputrc files.
        env = dict(os.environ, TERM='xterm-256color', INPUTRC='/dev/null', PYTHONIOENCODING='utf-8')
        script = ('import json; from inquiry.interactive import _Console; '
                  'value = _Console(None, None).text("입력 > "); '
                  'print("RESULT=" + json.dumps(value, ensure_ascii=True), flush=True)')
        try:
            process = subprocess.Popen([sys.executable, '-S', '-c', script],
                                       stdin=slave, stdout=slave, stderr=slave,
                                       cwd=Path(__file__).resolve().parents[1], env=env)
        finally:
            os.close(slave)
        received = bytearray()
        def receive_until(marker, complete_line=False):
            def ready():
                return marker in received and (not complete_line or b'\n' in received.partition(marker)[2])
            deadline = time.monotonic() + 5
            while not ready() and time.monotonic() < deadline:
                readable, _, _ = select.select([master], [], [], 0.1)
                if readable:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        break
                    if not chunk:
                        break
                    received.extend(chunk)
            self.assertTrue(ready(), repr(bytes(received)))
        try:
            receive_until('입력 > '.encode())
            os.write(master, text.encode('utf-8') + b'\x7f' * len(text) + '끝\n'.encode())
            receive_until(b'RESULT=', complete_line=True)
            process.wait(timeout=5)
            self.assertEqual(process.returncode, 0, repr(bytes(received)))
            result = bytes(received).split(b'RESULT=', 1)[1].splitlines()[0]
            return json.loads(result)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_backspace_erases_hangul_and_ascii_by_character(self):
        self.assertEqual(self._erase_and_retype('가나다abc'), '끝')

    def test_hangul_erase_across_wrapped_input(self):
        self.assertEqual(self._erase_and_retype('한글' * 20 + 'abc', columns=24), '끝')
