import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import curl_main_hook as hook


class CurlMainHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='curl-main-tests-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.old_hash = hook.sha(ROOT / 'src/elf_lab.py')
        cls.source = cls.folder / 'program with spaces.c'
        cls.source.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
static int initialized;
__attribute__((constructor)) static void before_main(void) { initialized = 1; }
__attribute__((destructor)) static void after_main(void) { puts("destructor"); }
static void at_end(void) { puts("atexit"); }
int main(int argc, char **argv) {
    char buf[4096];
    struct sigaction action;
    if (argc > 1 && !strcmp(argv[1], "--signal")) { raise(SIGTERM); return 99; }
    if (argc > 1 && !strcmp(argv[1], "--identity")) {
        ssize_t n = readlink("/proc/self/exe", buf, sizeof(buf)-1);
        if (n < 0) return 99;
        buf[n] = 0;
        printf("pid=%ld\nexe=%s\n", (long)getpid(), buf);
        return 0;
    }
    atexit(at_end);
    printf("constructor=%d\n", initialized);
    sigaction(SIGPIPE, NULL, &action);
    printf("sigpipe_default=%d\n", action.sa_handler == SIG_DFL);
    printf("stdin_closed=%d\n", fcntl(0, F_GETFD) == -1);
    for (int i = 0; i < argc; ++i) printf("arg%d=%s\n", i, argv[i]);
    printf("env=%s\n", getenv("HOOK_TEST_VALUE"));
    printf("cwd=%s\n", getcwd(buf, sizeof(buf)));
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), stdin))) fwrite(buf, 1, n, stdout);
    fputs("stderr retained\n", stderr);
    return 37;
}
''')
        cls.direct = cls.folder / 'original'
        cls.obj = cls.folder / 'program.o'
        cls.archive = cls.folder / 'program.a'
        hook.command(['gcc', '-g', cls.source, '-o', cls.direct])
        hook.command(['gcc', '-c', '-fPIC', '-g', cls.source, '-o', cls.obj])
        hook.command(['ar', 'rcs', cls.archive, cls.obj])
        cls.variants = {}
        cls.reports = {}
        for kind, source in [('source', cls.source), ('object', cls.obj), ('archive', cls.archive)]:
            out = cls.folder / kind
            cls.reports[kind] = hook.build(hook.DEFAULT_TREE, [source], out)
            cls.variants[kind] = out / 'curl'
        cls.echo_original = cls.folder / 'echo-original'
        echo_source = ROOT / 'examples/main_hook/echo.c'
        hook.command(['gcc', echo_source, '-o', cls.echo_original])
        hook.build(hook.DEFAULT_TREE, [echo_source], cls.folder / 'echo')
        cls.echo_hooked = cls.folder / 'echo/curl'

    def invoke(self, binary, args=(), data=b'', **kwargs):
        # A common argv[0] permits exact comparison of the main arguments.
        p = subprocess.run(['same-argv-zero', *args], executable=str(binary),
                           input=data, capture_output=True, timeout=5, cwd=self.folder,
                           env=dict(os.environ, HOOK_TEST_VALUE='value / 한글'), **kwargs)
        return p.returncode, p.stdout, p.stderr

    def test_source_object_archive_match_original(self):
        for args, data in [((), b''), (('hello world', '', '한글', '--version'), bytes(range(256))),
                           (('--signal',), b'')]:
            expected = self.invoke(self.direct, args, data)
            for kind, binary in self.variants.items():
                with self.subTest(kind=kind, args=args):
                    self.assertEqual(self.invoke(binary, args, data), expected)
        output = self.invoke(self.variants['source'])[1]
        self.assertIn(b'constructor=1', output)
        self.assertIn(b'sigpipe_default=1', output)
        self.assertTrue(output.endswith(b'atexit\ndestructor\n'))

    def test_hook_runs_before_curl_fd_repair(self):
        def close_stdin():
            os.close(0)
        expected = self.invoke(self.direct, preexec_fn=close_stdin)
        result = self.invoke(self.variants['source'], preexec_fn=close_stdin)
        self.assertEqual(result, expected)
        self.assertIn(b'stdin_closed=1', result[1])

    def test_stays_in_same_executable_and_process(self):
        binary = self.variants['source']
        p = subprocess.Popen([str(binary), '--identity'], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout, stderr = p.communicate(timeout=3)
        self.assertEqual(p.returncode, 0, stderr)
        self.assertIn(f'pid={p.pid}\n'.encode(), stdout)
        self.assertIn(os.fsencode('exe=' + str(binary) + '\n'), stdout)

    def test_first_call_macro_and_symbols(self):
        original_names = {n for n, _ in hook.symbols(ROOT / 'output/curl-symbols/curl')}
        names = {n for n, _ in hook.symbols(self.variants['source'])}
        self.assertLessEqual(original_names, names)
        for kind, report in self.reports.items():
            with self.subTest(kind=kind):
                self.assertEqual(report['hook_calls'], [hook.ENTRY, 'exit@plt'])
                self.assertTrue(report['first_main_call_verified'])
                self.assertTrue(report['original_curl_tree_unchanged'])
        generated = self.variants['source'].parent / 'sources'
        self.assertIn('#define CURL_DISPATCH_REAL_MAIN',
                      (generated / 'curl_main_dispatch.h').read_text())
        self.assertEqual(hook.sha(ROOT / 'src/elf_lab.py'), self.old_hash)
        sections = hook.command(['readelf', '-SW', self.variants['source']])
        self.assertIn('.debug_info', sections)
        self.assertIn('.symtab', sections)

    def test_main_arities_zero_and_three(self):
        for arity, source in [(0, 'int main(void) { return 19; }\n'),
                              (3, '#include <stdio.h>\nint main(int c,char **v,char **e) '
                               '{ (void)c; (void)v; for(;*e;++e) puts(*e); return 23; }\n')]:
            path = self.folder / f'arity{arity}.c'
            path.write_text(source)
            direct = self.folder / f'arity{arity}-original'
            hook.command(['gcc', path, '-o', direct])
            output = self.folder / f'arity{arity}'
            hook.build(hook.DEFAULT_TREE, [path], output, arity=arity)
            self.assertEqual(self.invoke(output / 'curl'), self.invoke(direct))

    def test_multiple_sources_compiler_and_library_options(self):
        main = self.folder / 'multi-main.c'
        helper = self.folder / 'multi-helper.c'
        main.write_text('#include <stdlib.h>\nextern int calculate(double);\n'
                        'int main(int argc,char **argv) { return argc > 1 ? '
                        'calculate(strtod(argv[1],0)) + TEST_FEATURE : 1; }\n')
        helper.write_text('#include <math.h>\nint calculate(double x) { return (int)sqrt(x); }\n')
        direct = self.folder / 'multi-original'
        hook.command(['gcc', '-DTEST_FEATURE=11', main, helper, '-lm', '-o', direct])
        out = self.folder / 'multi'
        hook.command([sys.executable, ROOT / 'src/curl_main_hook.py', '--payload', main, helper,
                      '--payload-cflag=-DTEST_FEATURE=11', '--payload-ldflag=-lm', '-o', out])
        self.assertEqual(self.invoke(out / 'curl', ['49']), self.invoke(direct, ['49']))
        self.assertEqual(self.invoke(out / 'curl', ['49'])[0], 18)

    def test_input_and_overwrite_errors(self):
        with self.assertRaisesRegex(ValueError, 'already exists'):
            hook.build(hook.DEFAULT_TREE, [self.source], self.folder / 'source')
        with self.assertRaisesRegex(ValueError, 'C source'):
            hook.build(hook.DEFAULT_TREE, [self.direct], self.folder / 'bad-elf')
        source = self.folder / 'no-main.c'
        source.write_text('int some_function(void) { return 0; }\n')
        with self.assertRaisesRegex(ValueError, 'exactly one global main'):
            hook.build(hook.DEFAULT_TREE, [source], self.folder / 'no-main')

    def test_binary_runs_without_build_inputs(self):
        copy = self.folder / 'standalone-result'
        shutil.copy2(self.variants['source'], copy)
        expected = self.invoke(self.direct)
        hidden = self.source.with_suffix('.hidden')
        self.source.rename(hidden)
        try:
            self.assertEqual(self.invoke(copy), expected)
        finally:
            hidden.rename(self.source)

    @unittest.skipUnless(os.environ.get('ELF_LAB_NETWORK_TESTS') == '1',
                         'set ELF_LAB_NETWORK_TESTS=1 for local echo integration')
    def test_echo_original_and_hooked(self):
        for payload in [b'', 'hello / 테스트\n'.encode(), bytes(range(256)) * 512]:
            results = []
            for binary in (self.echo_original, self.echo_hooked):
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    port = reservation.getsockname()[1]
                p = subprocess.Popen([str(binary)], env=dict(os.environ, HOOK_ECHO_PORT=str(port)),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic() + 3
                    while True:
                        try:
                            client = socket.create_connection(('127.0.0.1', port), timeout=3)
                            break
                        except ConnectionRefusedError:
                            if p.poll() is not None or time.monotonic() > deadline:
                                raise
                            time.sleep(.02)
                    with client:
                        client.sendall(payload)
                        client.shutdown(socket.SHUT_WR)
                        received = bytearray()
                        while part := client.recv(65536):
                            received.extend(part)
                    stdout, stderr = p.communicate(timeout=3)
                    results.append((p.returncode, stdout, stderr, bytes(received)))
                finally:
                    if p.poll() is None:
                        p.kill()
                    p.communicate()
            self.assertEqual(results[0], (0, b'', b'', payload))
            self.assertEqual(results[1], results[0])


if __name__ == '__main__':
    unittest.main()
