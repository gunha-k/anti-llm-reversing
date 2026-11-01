#!/usr/bin/env python3
"""Prepare pinned external inputs and reproduce the documented local experiments."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INPUTS = json.loads((ROOT / 'scripts/downloads.json').read_text())


def run(*args, cwd=ROOT, env=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(name):
    spec = INPUTS[name]
    dest = ROOT / spec['path']
    if dest.exists():
        if digest(dest) != spec['sha256']:
            raise ValueError(f'{dest}: checksum mismatch; existing file left untouched')
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.download-') as folder:
            partial = Path(folder) / 'download'
            run('curl', '--fail', '--location', '--show-error', '--retry', '3',
                '--connect-timeout', '30', '--max-time', '600',
                '--proto', '=https', '--proto-redir', '=https',
                '--output', partial, spec['url'])
            if digest(partial) != spec['sha256']:
                raise ValueError(f'{name}: downloaded checksum mismatch')
            partial.replace(dest)
    if name == 'jq':
        dest.chmod(0o755)
    print(f'{name}: verified SHA-256', flush=True)
    return dest


def prepare_curl(jobs):
    archive = fetch('curl')
    tree = archive.parent / 'curl-8.22.0'
    if tree.exists():
        # Never reuse an old, potentially modified source tree silently.
        raise ValueError(f'{tree} already exists; use a clean clone for reproduction')
    with tarfile.open(archive) as bundle:
        bundle.extractall(archive.parent, filter='data')
    env = dict(os.environ, CFLAGS='-O0 -g3 -fno-inline -fno-omit-frame-pointer -fno-lto',
               LDFLAGS='-Wl,--no-gc-sections')
    run('./configure', '--disable-shared', '--enable-static', '--disable-optimize',
        '--enable-debug', '--disable-werror', '--with-openssl', '--without-libpsl',
        '--without-libidn2', '--without-libssh2', '--without-nghttp2', '--without-brotli',
        '--without-zstd', cwd=tree, env=env)
    run('make', f'-j{jobs}', cwd=tree)
    out = ROOT / 'output/curl-symbols'
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tree / 'src/curl', out / 'curl')
    shutil.copy2(tree / 'COPYING', out / 'COPYING')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['standalone', 'fetch', 'curl', 'native', 'legacy', 'all'])
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--deps', type=Path, default=Path('/'),
                        help='development package root for Vim (default: system /usr)')
    args = parser.parse_args()
    if sys.version_info < (3, 12) or platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('Linux x86-64 and Python >=3.12 required; see Dockerfile')
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', str(ROOT)):
        parser.error('clone path must not contain spaces or shell metacharacters')
    needed = ['gcc', 'make', 'nm', 'objcopy', 'objdump', 'readelf', 'ld', 'ar']
    if args.target != 'standalone':
        needed.append('curl')
    missing = [name for name in needed if not shutil.which(name)]
    if missing:
        parser.error('missing tools: ' + ', '.join(missing) + '; see docs/reproduction.md')
    py = sys.executable
    target = args.target
    if target in ('standalone', 'all'):
        run('make', '-C', 'examples/standalone', f'-j{args.jobs}')
        run(py, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_standalone.py', '-v')
    if target == 'fetch':
        for name in INPUTS:
            fetch(name)
    if target in ('curl', 'all'):
        prepare_curl(args.jobs)
        run(py, 'src/curl_main_hook.py', '--payload', 'examples/main_hook/hello.c',
            '-o', 'output/curl-main-hook/hello')
        run(ROOT / 'output/curl-main-hook/hello/curl', 'reproduction-check')
        run(py, 'src/curl_main_hook.py', '--payload', 'examples/main_hook/echo.c',
            '-o', 'output/curl-socket')
        run(py, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_curl_main_hook.py', '-v',
            env=dict(os.environ, ELF_LAB_NETWORK_TESTS='1'))
    if target in ('native', 'all'):
        for host in ('sqlite', 'vim', 'git'):
            fetch(host)
            run(py, 'src/native_main_hook.py', '--host', host,
                '--payload', 'examples/main_hook/echo.c', '--jobs', args.jobs,
                '--deps', args.deps, '-o', f'output/native-main-hook/{host}')
        run(py, 'src/verify_native_main_hook.py', '--network')
    if target in ('legacy', 'all'):
        fetch('jq')
        for script in ('build', 'verify', 'mask_socket_strings', 'build_socket_mode', 'verify_socket_mode'):
            run(py, f'src/{script}.py')
    if target == 'all':
        run(py, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_elf_lab.py', '-v',
            env=dict(os.environ, ELF_LAB_NETWORK_TESTS='1'))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        sys.exit(f'Reproduction failed: {exc}')
