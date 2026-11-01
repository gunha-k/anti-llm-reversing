"""Behavior checks for the three unmodified standalone C programs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

APPS = Path(__file__).resolve().parents[1] / 'examples/standalone'


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)

    def invoke(self, app, *args, code=0, data=None):
        result = subprocess.run([str(APPS / app), *args], cwd=self.cwd,
                                input=data, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, code, result.stderr)
        return result.stdout

    def test_note(self):
        self.invoke('note', 'write', 'memo', '첫 메모')
        self.invoke('note', 'append', 'memo', 'second', 'line')
        self.assertEqual(self.invoke('note', 'read', 'memo'), '첫 메모\nsecond line\n'.encode())
        self.invoke('note', 'read', 'missing', code=1)

    def test_shell(self):
        self.assertEqual(self.invoke('minish', '-c', "printf '%s|%s' 'hello world' ''"), b'hello world|')
        self.invoke('minish', '-c', 'printf abc>msg')
        self.invoke('minish', '-c', 'printf def>>msg')
        self.assertEqual(self.invoke('minish', '-c', 'cat<msg'), b'abcdef')
        self.assertEqual(self.invoke('minish', data=b'cd /\npwd\nexit 7\n', code=7), b'/\n')
        self.invoke('minish', '-c', 'nonexistent_command_987654321', code=127)
        self.invoke('minish', '-c', "echo 'unclosed", code=2)
        self.invoke('minish', '-c', 'cat >', code=2)

    def test_rle(self):
        for i, content in enumerate((b'', b'A', b'A' * 255, b'A' * 256,
                                     b'A' * 65536, bytes(range(256)) * 512)):
            with self.subTest(case=i):
                (self.cwd / f'in{i}').write_bytes(content)
                self.invoke('rle', 'compress', f'in{i}', f'packed{i}')
                self.invoke('rle', 'decompress', f'packed{i}', f'out{i}')
                self.assertEqual((self.cwd / f'out{i}').read_bytes(), content)
        self.invoke('rle', 'compress', 'in0', 'in0', code=1)
        for i, content in enumerate((b'', b'BAD!', b'RLE1\x00a', b'RLE1\x01')):
            (self.cwd / 'bad').write_bytes(content)
            self.invoke('rle', 'decompress', 'bad', f'badout{i}', code=1)
            self.assertFalse((self.cwd / f'badout{i}').exists())
