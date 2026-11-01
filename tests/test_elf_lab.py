import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import elf_lab as lab


class ElfLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='elf-lab-tests-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.folder = Path(cls.temporary.name)
        cls.payload = lab.compile_echo(18080)
        cls.hosts = {'jq-static': ROOT / 'jq',
                     'curl-debug-pie': ROOT / 'output/curl-symbols/curl',
                     'ls-stripped-pie': Path('/usr/bin/ls')}
        source = cls.folder / 'host.c'
        source.write_text('#include <stdio.h>\nint main(void) { puts("original main"); return 37; }\n')
        for name, flags in [('dynamic-exec', ['-no-pie']),
                            ('static-pie', ['-static-pie'])]:
            target = cls.folder / name
            subprocess.run(['gcc', '-g', *flags, str(source), '-o', str(target)],
                           check=True, capture_output=True)
            cls.hosts[name] = target
        raw = bytearray(Path('/usr/bin/true').read_bytes())
        h = list(lab.EH.unpack_from(raw))
        h[6], h[11], h[12], h[13] = 0, 0, 0, 0
        lab.EH.pack_into(raw, 0, *h)
        sectionless = cls.folder / 'sectionless'
        sectionless.write_bytes(raw)
        cls.hosts['sectionless'] = sectionless
        cls.outputs = {}
        for name, host in cls.hosts.items():
            raw = host.read_bytes()
            result = lab.transform(raw, cls.payload)
            target = cls.folder / (name + '-echo')
            target.write_bytes(result)
            target.chmod(0o755)
            cls.outputs[name] = target

        observer_source = cls.folder / 'observer.c'
        observer_source.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
int main(int argc, char **argv) {
    char buffer[4096];
    if (argc > 1 && !strcmp(argv[1], "--signal")) { raise(SIGTERM); return 99; }
    for (int i = 0; i < argc; ++i) printf("argv[%d]=%s\n", i, argv[i]);
    printf("env=%s\n", getenv("LAB_VALUE"));
    printf("cwd=%s\n", getcwd(buffer, sizeof(buffer)));
    ssize_t n = readlink("/proc/self/exe", buffer, sizeof(buffer)-1);
    if (n >= 0) { buffer[n] = 0; printf("exe=%s\n", buffer); }
    if (getenv("LAB_FD")) {
        n = read(atoi(getenv("LAB_FD")), buffer, sizeof(buffer));
        if (n > 0) fwrite(buffer, 1, n, stdout);
    }
    while ((n = fread(buffer, 1, sizeof(buffer), stdin)) > 0)
        fwrite(buffer, 1, n, stdout);
    fputs("stderr from original\n", stderr);
    return 37;
}
''')
        cls.observer = cls.folder / 'program with spaces \' " $ ( )'
        subprocess.run(['gcc', str(observer_source), '-o', str(cls.observer)],
                       check=True, capture_output=True)
        adapter = lab.compile_exec(cls.observer)
        cls.exec_outputs = {}
        for name, host in cls.hosts.items():
            result = lab.transform(host.read_bytes(), adapter, exec_mode=True)
            target = cls.folder / (name + '-exec')
            target.write_bytes(result)
            target.chmod(0o755)
            cls.exec_outputs[name] = target
        original_server = ROOT / 'output/curl-socket/curl'
        cls.echo_exec = cls.folder / 'curl-original-echo'
        lab.build(cls.hosts['curl-debug-pie'], cls.echo_exec, payload_path=original_server)

    def test_exec_matches_original(self):
        env = dict(os.environ, LAB_VALUE='value with spaces / 한글')
        for args in [[], ['space argument', '', '한글', '--version'], ['--signal']]:
            original = subprocess.run([str(self.observer), *args], input=bytes(range(256)),
                                      cwd=self.folder, env=env, capture_output=True, timeout=3)
            for name, target in self.exec_outputs.items():
                with self.subTest(host=name, args=args):
                    result = subprocess.run([str(target), *args], input=bytes(range(256)),
                                            cwd=self.folder, env=env, capture_output=True, timeout=3)
                    self.assertEqual((result.stdout, result.stderr, result.returncode),
                                     (original.stdout, original.stderr, original.returncode))

    def test_exec_jq_and_script(self):
        target = self.folder / 'curl-jq'
        lab.build(self.hosts['curl-debug-pie'], target, payload_path=ROOT / 'jq')
        for args, data in [(['--version'], b''), (['.items | add'], b'{"items":[1,2,3]}'),
                           (['-e', '.'], b'false'), (['.'], b'{invalid'),
                           (['-r', '.name'], '{"name":"테스트"}'.encode())]:
            original = subprocess.run([str(ROOT / 'jq'), *args], input=data,
                                      capture_output=True, timeout=3)
            actual = subprocess.run([str(target), *args], input=data,
                                    capture_output=True, timeout=3)
            self.assertEqual((actual.stdout, actual.stderr, actual.returncode),
                             (original.stdout, original.stderr, original.returncode))
        script = self.folder / 'script'
        script.write_text('#!/bin/sh\nprintf "%s\\n" "$0" "$@"\nexit 23\n')
        script.chmod(0o755)
        wrapper = self.folder / 'curl-script'
        lab.build(self.hosts['curl-debug-pie'], wrapper, payload_path=script)
        results = [subprocess.run([str(p), 'hello world', ''], capture_output=True, timeout=3)
                   for p in (script, wrapper)]
        self.assertEqual((results[0].stdout, results[0].stderr, results[0].returncode),
                         (results[1].stdout, results[1].stderr, results[1].returncode))

    def test_exec_inherits_open_file_descriptor(self):
        with tempfile.TemporaryFile() as stream:
            stream.write(b'inherited file descriptor contents\n')
            stream.flush()
            env = dict(os.environ, LAB_VALUE='fd test', LAB_FD=str(stream.fileno()))
            results = []
            for target in [self.observer, self.exec_outputs['curl-debug-pie']]:
                stream.seek(0)
                result = subprocess.run([str(target)], input=b'', env=env,
                                        pass_fds=(stream.fileno(),), capture_output=True, timeout=3)
                results.append((result.stdout, result.stderr, result.returncode))
            self.assertEqual(results[0], results[1])
            self.assertIn(b'inherited file descriptor contents', results[1][0])

    def test_exec_preserves_symbols_and_verifies_target(self):
        host = self.hosts['curl-debug-pie']
        target = self.folder / 'curl-observer'
        manifest = lab.build(host, target, payload_path=self.observer)
        self.assertTrue(manifest['verification']['execution_target_hash_matches'])
        before, after = lab.ELF(host.read_bytes()), lab.ELF(target.read_bytes())
        self.assertIsNone(after.interpreter)
        self.assertEqual(after.data[64:len(before.data)], before.data[64:])
        original_symbols = subprocess.check_output(['nm', '-a', str(host)])
        result_symbols = subprocess.check_output(['nm', '-a', str(target)])
        self.assertEqual(original_symbols, result_symbols)
        self.assertIn(b' T main\n', result_symbols)
        manifest['execution_target']['sha256_at_build'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'execution target hash mismatch'):
            lab.verify_bytes(before.data, after.data, manifest)

    def test_exec_missing_target_reports_failure(self):
        target = self.folder / 'missing-target-launcher'
        adapter = lab.compile_exec(self.folder / 'does-not-exist')
        target.write_bytes(lab.transform(self.hosts['curl-debug-pie'].read_bytes(),
                                         adapter, exec_mode=True))
        target.chmod(0o755)
        result = subprocess.run([str(target)], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 127)
        self.assertIn(b'execve failed', result.stderr)

    def test_exec_preserves_symlink_name(self):
        alias = self.folder / 'observer-alias'
        alias.symlink_to(self.observer)
        target = self.folder / 'curl-alias'
        lab.build(self.hosts['curl-debug-pie'], target, payload_path=alias)
        env = dict(os.environ, LAB_VALUE='alias')
        results = [subprocess.run([str(p)], input=b'', env=env, capture_output=True, timeout=3)
                   for p in (alias, target)]
        self.assertEqual(results[0].stdout, results[1].stdout)
        self.assertIn(os.fsencode(alias), results[1].stdout)

    def test_structure_and_symbols_across_hosts(self):
        for name, host in self.hosts.items():
            with self.subTest(host=name):
                raw, result = host.read_bytes(), self.outputs[name].read_bytes()
                manifest = {'schema': 'elf-echo-lab/v1',
                            'source': {'sha256': lab.digest(raw)},
                            'result': {'sha256': lab.digest(result)}}
                self.assertTrue(lab.verify_bytes(raw, result, manifest)['passed'])
                self.assertEqual(result[64:len(raw)], raw[64:])
                # Existing symbol sections and all their linked strings remain identical.
                before, after = lab.ELF(raw), lab.ELF(result)
                for i, s in enumerate(before.sh):
                    if s[1] in (2, 11):
                        self.assertEqual(after.sh[i], s)
                        self.assertEqual(after.span(s[4], s[5]), before.span(s[4], s[5]))
                check = subprocess.run(['readelf', '-lW', str(self.outputs[name])],
                                       capture_output=True)
                self.assertEqual(check.returncode, 0)
                self.assertEqual(check.stderr, b'')

    def test_reproducible(self):
        raw = self.hosts['jq-static'].read_bytes()
        self.assertEqual(lab.transform(raw, self.payload), lab.transform(raw, self.payload))
        self.assertEqual(self.payload, lab.compile_echo(18080))

    def test_rejects_malformed_and_unsupported(self):
        raw = self.hosts['ls-stripped-pie'].read_bytes()
        cases = [b'', raw[:63], raw[:100], b'MZ' + raw[2:]]
        for offset, value in [(4, 1), (5, 2)]:
            data = bytearray(raw)
            data[offset] = value
            cases.append(bytes(data))
        for field, value in [(1, 1), (2, 183), (4, 2**48), (5, len(raw)),
                             (9, 1), (10, 0xffff), (12, 0), (13, 0xffff)]:
            data = bytearray(raw)
            h = list(lab.EH.unpack_from(data))
            h[field] = value
            lab.EH.pack_into(data, 0, *h)
            cases.append(bytes(data))
        for i, data in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                lab.ELF(data)

    def test_build_cli_and_no_overwrite(self):
        host = self.hosts['ls-stripped-pie']
        target = self.folder / 'path with spaces' / 'ls'
        before = hashlib.sha256(host.read_bytes()).hexdigest()
        built = subprocess.run([sys.executable, str(ROOT / 'src/elf_lab.py'),
                                'build', str(host), '-o', str(target), '--port', '19090'],
                               capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        report = json.loads(built.stdout)
        self.assertEqual(report['behavior']['default_port'], 19090)
        check = subprocess.run([sys.executable, str(ROOT / 'src/elf_lab.py'),
                                'verify', str(host), str(target)], capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            lab.build(host, target, 18080)
        self.assertEqual(before, hashlib.sha256(host.read_bytes()).hexdigest())
        alias = self.folder / 'alias'
        alias.symlink_to(host)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            lab.build(host, alias, 18080)
        dangling = self.folder / 'dangling'
        dangling.symlink_to(self.folder / 'absent')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            lab.build(host, dangling, 18080)

    def test_detects_corruption(self):
        host = self.hosts['jq-static'].read_bytes()
        result = self.outputs['jq-static'].read_bytes()
        manifest = {'schema': 'elf-echo-lab/v1', 'source': {'sha256': lab.digest(host)},
                    'result': {'sha256': lab.digest(result)}}
        data = bytearray(result)
        data[1000] ^= 1
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            lab.verify_bytes(host, bytes(data), manifest)
        manifest['result']['sha256'] = lab.digest(data)
        with self.assertRaisesRegex(ValueError, 'original file bytes changed'):
            lab.verify_bytes(host, bytes(data), manifest)

    def test_invalid_runtime_port(self):
        # These exit before socket(), so also run within the default sandbox.
        for name, target in self.outputs.items():
            for port in ['', '0', '-1', '65536', '1a', '9' * 100]:
                with self.subTest(host=name, port=port):
                    result = subprocess.run([str(target), '--version'],
                                            env=dict(os.environ, ELF_ECHO_PORT=port),
                                            capture_output=True, timeout=3)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stdout, b'')

    @unittest.skipUnless(os.environ.get('ELF_LAB_NETWORK_TESTS') == '1',
                         'set ELF_LAB_NETWORK_TESTS=1 to test local TCP echo')
    def test_runtime_echo_all_hosts(self):
        targets = dict(self.outputs, original_server_exec=self.echo_exec)
        for name, target in targets.items():
            for payload in [b'', b'hello\n', '테스트\n'.encode(), bytes(range(256)) * 512]:
                with self.subTest(host=name, bytes=len(payload)):
                    with socket.socket() as reservation:
                        reservation.bind(('127.0.0.1', 0))
                        port = reservation.getsockname()[1]
                    env = dict(os.environ, ELF_ECHO_PORT=str(port), CURL_SOCKET_PORT=str(port),
                               HOOK_ECHO_PORT=str(port))
                    process = subprocess.Popen([str(target), '--version'], env=env,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        deadline = time.monotonic() + 3
                        while True:
                            try:
                                client = socket.create_connection(('127.0.0.1', port), timeout=3)
                                break
                            except ConnectionRefusedError:
                                self.assertIsNone(process.poll(), process.communicate()
                                                  if process.poll() is not None else '')
                                if time.monotonic() >= deadline:
                                    raise
                                time.sleep(.02)
                        with client:
                            client.sendall(payload)
                            client.shutdown(socket.SHUT_WR)
                            received = bytearray()
                            while True:
                                chunk = client.recv(65536)
                                if not chunk:
                                    break
                                received.extend(chunk)
                        self.assertEqual(received, payload)
                        stdout, stderr = process.communicate(timeout=3)
                        self.assertEqual(process.returncode, 0, stderr)
                        self.assertEqual(stdout, b'')
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.communicate()

    @unittest.skipUnless(os.environ.get('ELF_LAB_NETWORK_TESTS') == '1',
                         'set ELF_LAB_NETWORK_TESTS=1 to test local bind errors')
    def test_bind_conflict(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            env = dict(os.environ, ELF_ECHO_PORT=str(listener.getsockname()[1]))
            for name, target in self.outputs.items():
                with self.subTest(host=name):
                    result = subprocess.run([str(target)], env=env, capture_output=True, timeout=3)
                    self.assertEqual(result.returncode, 1, result.stderr)


if __name__ == '__main__':
    unittest.main()
