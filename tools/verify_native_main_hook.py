#!/usr/bin/env python3
"""Verify the three built-in echo demonstrations, including same-process execution."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

from native_main_hook import ROOT, HOSTS, DEBUG, sha, require, verify_structure


def run_echo(binary, payload, *, terminate=False):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen([str(binary), '--version'],
                               env=dict(os.environ, HOOK_ECHO_PORT=str(port)),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                client = socket.create_connection(('127.0.0.1', port), timeout=5)
                break
            except ConnectionRefusedError:
                require(process.poll() is None, f'{binary} exited before accept')
                require(time.monotonic() < deadline, f'{binary} did not listen')
                time.sleep(.02)
        with client:
            exe = Path(f'/proc/{process.pid}/exe').resolve()
            require(exe == binary.resolve(), f'executable was replaced: {exe}')
            children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().strip()
            require(not children, f'unexpected child processes: {children}')
            if terminate:
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                require(process.returncode == -signal.SIGTERM, 'SIGTERM disposition changed')
                require(stdout == stderr == b'', 'unexpected termination output')
                return {'sigterm_exit': process.returncode, 'same_executable': True, 'no_children': True}
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
            received = bytearray()
            while chunk := client.recv(65536):
                received.extend(chunk)
        stdout, stderr = process.communicate(timeout=5)
        require(bytes(received) == payload, f'{binary} echo differs')
        require(process.returncode == 0 and stdout == stderr == b'',
                f'{binary} has different output or exit status')
        return {'echo_bytes': len(payload), 'exit_code': 0, 'same_executable': True, 'no_children': True}
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def verify(base, network):
    reports = []
    source = ROOT / 'programs/main_hook/echo.c'
    with tempfile.TemporaryDirectory(prefix='native-echo-check-') as folder:
        direct = Path(folder) / 'original-echo'
        subprocess.run(['gcc', *DEBUG, str(source), '-o', str(direct)], check=True, capture_output=True)
        for host, spec in HOSTS.items():
            out = base / host
            manifest = json.loads((out / 'manifest.json').read_text())
            binary = out / spec['binary']
            original = out / (spec['binary'] + '.original')
            require(sha(binary) == manifest['sha256'], f'{host}: result hash mismatch')
            require(sha(original) == manifest['original_sha256'], f'{host}: baseline hash mismatch')
            require(len(manifest['payloads']) == 1 and
                    manifest['payloads'][0]['sha256'] == sha(source),
                    f'{host}: this verifier is for the bundled echo example only')
            structural = verify_structure(host, original, binary, out)
            errors = []
            for value in ['', '0', '-1', '65536', 'abc', '9' * 100]:
                env = dict(os.environ, HOOK_ECHO_PORT=value)
                expected = subprocess.run([str(direct), '--version'], env=env,
                                          capture_output=True, timeout=3)
                actual = subprocess.run([str(binary), '--version'], env=env,
                                        capture_output=True, timeout=3)
                require((actual.returncode, actual.stdout, actual.stderr) ==
                        (expected.returncode, expected.stdout, expected.stderr),
                        f'{host}: invalid port behavior differs')
                require(actual.returncode == 1, 'expected echo parser failure')
                errors.append(value)
            report = {'host': host, 'binary': str(binary), 'sha256': sha(binary),
                      'structure': structural, 'invalid_port_cases_passed': len(errors)}
            if network:
                cases = []
                for payload in [b'', b'hello\n', '테스트\n'.encode(), bytes(range(256)) * 512]:
                    expected = run_echo(direct, payload)
                    actual = run_echo(binary, payload)
                    require(actual == expected, f'{host}: runtime comparison failed')
                    cases.append(actual)
                report['network'] = {'status': 'passed', 'echo_cases': cases,
                                     'termination': run_echo(binary, b'', terminate=True)}
                with socket.socket() as occupied:
                    occupied.bind(('127.0.0.1', 0))
                    occupied.listen(1)
                    env = dict(os.environ, HOOK_ECHO_PORT=str(occupied.getsockname()[1]))
                    result = subprocess.run([str(binary)], env=env, capture_output=True, timeout=3)
                    require(result.returncode == 1 and result.stdout == result.stderr == b'',
                            f'{host}: bind conflict handling differs')
                report['network']['bind_conflict_passed'] = True
            else:
                report['network'] = {'status': 'not_run', 'reason': 'use --network for local TCP tests'}
            reports.append(report)
            print(f'{host}: structural and runtime checks passed; network={report["network"]["status"]}')
    result = {'schema': 'native-main-hook-verification/v1', 'hosts': reports,
              'scope': 'provided echo sample; no claim of full upstream project test coverage'}
    (base / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=ROOT / 'output/native-main-hook')
    parser.add_argument('--network', action='store_true')
    args = parser.parse_args()
    try:
        verify(args.base.resolve(), args.network)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
