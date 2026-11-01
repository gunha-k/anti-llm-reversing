#!/usr/bin/env python3
"""Preserve a Linux x86-64 ELF host while delegating execution to another program."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

EH = struct.Struct('<16sHHIQQQIHHHHHH')
PH = struct.Struct('<IIQQQQQQ')
SH = struct.Struct('<IIQQQQIIQQ')
PAGE = 4096


def require(condition, message):
    if not condition:
        raise ValueError(message)


def align(value, alignment=PAGE):
    return (value + alignment - 1) // alignment * alignment


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ELF:
    def __init__(self, data):
        self.data = data
        require(len(data) >= EH.size, 'truncated ELF header')
        self.h = list(EH.unpack_from(data))
        h = self.h
        require(data[:7] == b'\x7fELF\x02\x01\x01',
                'only little-endian ELF64 is supported')
        require(h[1] in (2, 3) and h[2] == 62 and h[3] == 1,
                'only x86-64 ET_EXEC / ET_DYN executables are supported')
        require(data[7] in (0, 3), 'only System V / Linux ELF ABI is supported')
        require(h[8] == EH.size and h[9] == PH.size,
                'unexpected ELF / program header size')
        require(0 < h[10] < 0xffff, 'missing or extended program headers unsupported')
        require(h[5] >= EH.size and h[10] * PH.size <= 65536,
                'invalid program header table')
        self.ph = self.table(h[5], h[10], PH)
        self.sh = []
        if h[6]:
            require(0 < h[12] < 0xff00 and h[11] == SH.size,
                    'extended / invalid section headers unsupported')
            self.sh = self.table(h[6], h[12], SH)
            require(h[13] < len(self.sh), 'invalid section name table index')
            for s in self.sh[1:]:
                if s[1] != 8:
                    self.span(s[4], s[5])
        else:
            require(h[12] == 0 and h[13] == 0, 'inconsistent absent section table')
        self.loads = [p for p in self.ph if p[0] == 1]
        require(self.loads, 'no LOAD segments')
        require([p[3] for p in self.loads] == sorted(p[3] for p in self.loads),
                'LOAD segments must be ordered by virtual address')
        for p in self.ph:
            self.span(p[2], p[5])
            if p[0] == 1:
                require(p[5] <= p[6], 'LOAD file size exceeds memory size')
                require(p[3] + p[6] < 2**47, 'unsupported virtual address range')
                require(p[7] in (0, 1) or
                        (p[7] & (p[7] - 1) == 0 and p[2] % p[7] == p[3] % p[7]),
                        'invalid LOAD alignment')
                require(p[2] % PAGE == p[3] % PAGE, 'invalid LOAD page alignment')
        require(any(p[1] & 1 and p[3] <= h[4] < p[3] + p[5] for p in self.loads),
                'entry point is not in executable file-backed LOAD data')
        interpreters = [p for p in self.ph if p[0] == 3]
        require(len(interpreters) <= 1, 'multiple ELF interpreters unsupported')
        self.interpreter = None
        if interpreters:
            p = interpreters[0]
            raw = self.span(p[2], p[5])
            require(raw.endswith(b'\0') and raw.startswith(b'/'), 'invalid interpreter')
            self.interpreter = os.fsdecode(bytes(raw[:-1]))
        self.names = b'\0'
        if self.sh and h[13]:
            s = self.sh[h[13]]
            require(s[1] == 3, 'section names must use a string table')
            self.names = self.span(s[4], s[5])
            require(self.names.startswith(b'\0') and self.names.endswith(b'\0'),
                    'invalid section name string table')
            for s in self.sh:
                require(s[0] < len(self.names), 'section name offset out of range')

    def span(self, offset, size):
        require(0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset,
                'ELF range extends beyond file')
        return self.data[offset:offset + size]

    def table(self, offset, count, record):
        self.span(offset, count * record.size)
        return [list(record.unpack_from(self.data, offset + i * record.size))
                for i in range(count)]

    def describe(self):
        return {'format': 'ELF64-x86-64', 'type': 'ET_EXEC' if self.h[1] == 2 else 'ET_DYN',
                'entry': hex(self.h[4]), 'interpreter': self.interpreter,
                'load_segments': len(self.loads), 'sections': len(self.sh),
                'has_symtab': any(s[1] == 2 for s in self.sh),
                'sha256': digest(self.data), 'bytes': len(self.data)}


def compile_payload(source, entry, flags=()):
    for tool in ('gcc', 'ld', 'objcopy'):
        require(shutil.which(tool), f'required build tool not found: {tool}')
    with tempfile.TemporaryDirectory(prefix='elf-echo-build-') as folder:
        folder = Path(folder)
        obj, elf, binary = (folder / n for n in ('echo.o', 'echo.elf', 'echo.bin'))
        script = folder / 'echo.ld'
        script.write_text(f'ENTRY({entry})\n' + '''
PHDRS { payload PT_LOAD FLAGS(5); }
SECTIONS {
  . = 0;
  .payload : { *(.text.entry) *(.text*) *(.rodata*) } :payload
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
''')
        commands = [
            ['gcc', '-c', '-Os', '-Wall', '-Wextra', '-Werror', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fPIC', '-fno-jump-tables',
             '-fno-asynchronous-unwind-tables', '-fno-unwind-tables',
             *flags, str(source),
             '-o', str(obj)],
            ['ld', '-nostdlib', '--no-undefined', '-T', str(script), str(obj), '-o', str(elf)],
            ['objcopy', '-O', 'binary', '--only-section=.payload', str(elf), str(binary)],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            require(result.returncode == 0, f'{command[0]} failed: {result.stderr.strip()}')
        built = ELF(elf.read_bytes())
        require(built.h[4] == 0, 'adapter entry must be at payload offset zero')
        require(not any(s[1] in (4, 9) and s[5] for s in built.sh),
                'echo payload has unresolved relocations')
        require(not any(s[2] & 2 and s[2] & 1 and s[5] for s in built.sh),
                'echo payload requires unsupported writable global data')
        return binary.read_bytes()


def compile_echo(port):
    return compile_payload(Path(__file__).with_name('echo_lab.c'), 'echo_lab_entry',
                           [f'-DDEFAULT_PORT={port}'])


def compile_exec(target):
    # Encode the filesystem path as byte values, never as assembly / shell syntax.
    path_bytes = os.fsencode(target) + b'\0'
    byte_list = ','.join(str(b) for b in path_bytes)
    assembly = '''.section .text.entry,"ax",@progbits
.global exec_lab_entry
.type exec_lab_entry,@function
exec_lab_entry:
    endbr64
    mov (%rsp), %rax
    lea 16(%rsp,%rax,8), %rdx
    lea 8(%rsp), %rsi
    lea target_path(%rip), %rdi
    mov %rdi, (%rsi)
    mov $59, %eax
    syscall
    mov $126, %r12d
    cmp $-2, %rax
    jne 1f
    mov $127, %r12d
1:
    mov $1, %eax
    mov $2, %edi
    lea error_message(%rip), %rsi
    mov $error_end-error_message, %edx
    syscall
    mov %r12d, %edi
    mov $231, %eax
    syscall
    hlt
.size exec_lab_entry,.-exec_lab_entry
.section .rodata
error_message: .ascii "elf-lab: execve failed\\n"
error_end:
target_path:
    .byte ''' + byte_list + '\n.section .note.GNU-stack,"",@progbits\n'
    with tempfile.TemporaryDirectory(prefix='elf-exec-source-') as folder:
        source = Path(folder) / 'exec.S'
        source.write_text(assembly)
        return compile_payload(source, 'exec_lab_entry')


def transform(raw, payload, *, exec_mode=False):
    source = ELF(raw)
    h = source.h.copy()
    # An exec adapter needs no host runtime. Omitting PT_INTERP prevents host
    # dependency loading / library constructors from changing target behavior.
    removed = (3, 6) if exec_mode else (6,)
    ph = [p.copy() for p in source.ph if p[0] not in removed]
    count = len(ph) + 2
    require(count * PH.size <= 65536, 'new program header table exceeds Linux limit')
    offset = align(len(raw))
    base = align(max(p[3] + p[6] for p in source.loads))
    code_delta = align(count * PH.size, 16)
    size = code_delta + len(payload)
    require(base + size < 2**47, 'no supported virtual address space for payload')
    ph = [[6, 4, offset, base, base, count * PH.size, count * PH.size, 8]] + ph
    ph.append([1, 5, offset, base, base, size, size, PAGE])
    data = bytearray(raw)
    data.extend(b'\0' * (offset - len(data)))
    data.extend(b''.join(PH.pack(*p) for p in ph))
    data.extend(b'\0' * (offset + code_delta - len(data)))
    data.extend(payload)
    h[4], h[5], h[10] = base + code_delta, offset, len(ph)
    if not source.sh:
        # Keep sectionless executables sectionless. A partial section table
        # would misrepresent existing dynamic segments to inspection tools.
        EH.pack_into(data, 0, *h)
        ELF(data)
        return bytes(data)

    def append(blob, alignment=8):
        data.extend(b'\0' * (align(len(data), alignment) - len(data)))
        start = len(data)
        data.extend(blob)
        return start

    sh = [s.copy() for s in source.sh] or [[0] * 10]
    require(len(sh) + 2 < 0xff00, 'new section table would require extended numbering')
    names = bytearray(source.names)
    name_offset = len(names)
    names.extend(b'.text.exec_lab\0' if exec_mode else b'.text.echo_lab\0')
    sh.append([name_offset, 1, 6, base + code_delta, offset + code_delta,
               len(payload), 0, 0, 16, 0])
    names_idx = h[13]
    if not names_idx:
        names_idx = len(sh)
        name_offset = len(names)
        names.extend(b'.shstrtab\0')
        sh.append([name_offset, 3, 0, 0, 0, 0, 0, 0, 1, 0])
    # A loaded string table cannot be moved without changing runtime semantics.
    require(not sh[names_idx][2] & 2, 'allocated section name table unsupported')
    sh[names_idx][4] = append(names, 1)
    sh[names_idx][5] = len(names)
    h[6], h[11], h[12], h[13] = append(b''.join(SH.pack(*s) for s in sh)), SH.size, len(sh), names_idx
    EH.pack_into(data, 0, *h)
    ELF(data)
    require(data[EH.size:len(raw)] == raw[EH.size:], 'original bytes changed')
    return bytes(data)


def verify_bytes(raw, result, manifest):
    source, target = ELF(raw), ELF(result)
    require(isinstance(manifest, dict) and manifest.get('schema') in
            ('elf-echo-lab/v1', 'elf-exec-lab/v1'), 'unsupported manifest schema')
    exec_mode = manifest['schema'] == 'elf-exec-lab/v1'
    require(digest(raw) == manifest['source']['sha256'], 'source hash mismatch')
    require(digest(result) == manifest['result']['sha256'], 'result hash mismatch')
    require(result[EH.size:len(raw)] == raw[EH.size:], 'original file bytes changed')
    for i, (a, b) in enumerate(zip(source.h, target.h)):
        if i not in (4, 5, 6, 10, 11, 12, 13):
            require(a == b, f'unexpected ELF header change at field {i}')
    require(target.loads[:-1] == source.loads, 'original LOAD mappings changed')
    removed = (3, 6) if exec_mode else (6,)
    require(target.ph[1:-1] == [p for p in source.ph if p[0] not in removed],
            'original program headers changed')
    if exec_mode:
        require(target.interpreter is None, 'exec adapter must bypass the host interpreter')
    p = target.loads[-1]
    require(p[1] == 5 and p[2] >= len(raw), 'invalid appended RX LOAD')
    require(p[3] >= max(q[3] + q[6] for q in source.loads), 'new LOAD overlaps host')
    table = target.ph[0]
    require(table[0] == 6 and table[2] == target.h[5] == p[2]
            and table[3] == p[3] and table[5] == target.h[10] * PH.size,
            'program header table is not mapped correctly')
    require(target.h[4] == p[3] + align(table[5], 16), 'incorrect new entry point')
    for i, s in enumerate(source.sh):
        if i != source.h[13]:
            require(target.sh[i] == s, 'original section metadata changed')
    report = {'passed': True, 'original_bytes_after_header_preserved': True,
              'original_load_mappings_preserved': True,
              'original_sections_preserved_except_name_table': True,
              'source_sha256': digest(raw), 'result_sha256': digest(result)}
    if exec_mode:
        execution = manifest['execution_target']
        path = Path(execution['path'])
        require(path.is_file() and os.access(path, os.X_OK), 'execution target unavailable')
        require(digest(path.read_bytes()) == execution['sha256_at_build'],
                'execution target hash mismatch')
        report['execution_target_hash_matches'] = True
    return report


def build(source_path, output, port=18080, payload_path=None):
    source_path, output = Path(source_path).resolve(), Path(output).absolute()
    manifest_path = Path(str(output) + '.manifest.json')
    require(source_path.is_file(), 'input must be a regular file')
    require(not output.exists() and not output.is_symlink(), 'output already exists')
    require(not manifest_path.exists() and not manifest_path.is_symlink(), 'manifest already exists')
    raw = source_path.read_bytes()
    source = ELF(raw)
    exec_mode = payload_path is not None
    if exec_mode:
        # Preserve symlink names: argv[0] may select behavior (e.g. multicall tools).
        payload_path = Path(payload_path).absolute()
        require(payload_path.is_file() and os.access(payload_path, os.X_OK),
                'execution target must be an executable regular file')
        payload = compile_exec(payload_path)
    else:
        payload = compile_echo(port)
    result = transform(raw, payload, exec_mode=exec_mode)
    manifest = {
        'schema': 'elf-exec-lab/v1' if exec_mode else 'elf-echo-lab/v1',
        'source': dict(source.describe(), path=str(source_path)),
        'result': dict(ELF(result).describe(), path=str(output)),
        'behavior': {'service': 'single-client TCP echo', 'bind': '127.0.0.1',
                     'default_port': port, 'port_environment': 'ELF_ECHO_PORT',
                     'exit_after_client_eof': True, 'original_entry_executed': False},
        'payload_sha256': digest(payload),
        'limitations': ['Linux x86-64 only; original dynamic dependencies still required',
                        'loader initialization may run before the new entry',
                        'original build-id is retained; use SHA-256 to identify the result'],
    }
    if exec_mode:
        manifest['execution_target'] = {
            'path': str(payload_path), 'sha256_at_build': digest(payload_path.read_bytes()),
            'storage': 'external-original-file',
        }
        manifest['behavior'] = {
            'operation': 'execve', 'argv0': str(payload_path),
            'remaining_arguments': 'forwarded unchanged',
            'environment_cwd_stdio_fds': 'inherited',
            'exit_status_and_signals': 'execution target replaces the launcher process',
            'original_host_entry_executed': False, 'host_interpreter_executed': False,
        }
        manifest['limitations'] = [
            'execution target must remain at its recorded absolute path',
            'process identity after execve is the actual execution target',
            'original host build-id is retained; identify result by SHA-256',
        ]
    manifest['verification'] = verify_bytes(raw, result, manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        # Exclusive creation also protects against races and dangling symlinks.
        with output.open('xb') as stream:
            created.append(output)
            stream.write(result)
            os.fchmod(stream.fileno(), 0o755)
        with manifest_path.open('x') as stream:
            created.append(manifest_path)
            stream.write(json.dumps(manifest, indent=2) + '\n')
    except BaseException:
        for path in reversed(created):
            path.unlink()
        raise
    return manifest


def port_number(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('port must be an integer') from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('port must be between 1 and 65535')
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='check a host without executing it')
    inspect.add_argument('input', type=Path)
    make = commands.add_parser('build', help='preserve a host and select its runtime behavior')
    make.add_argument('input', type=Path)
    make.add_argument('-o', '--output', type=Path, required=True)
    behavior = make.add_mutually_exclusive_group()
    behavior.add_argument('--payload', type=Path,
                          help='execute this original file with forwarded arguments and environment')
    behavior.add_argument('--port', type=port_number,
                          help='built-in echo mode: default port (default: 18080)')
    verify = commands.add_parser('verify', help='verify bytes and layout without executing the result')
    verify.add_argument('input', type=Path)
    verify.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            report = ELF(args.input.read_bytes()).describe()
        elif args.command == 'build':
            report = build(args.input, args.output, args.port or 18080, args.payload)
        else:
            manifest = json.loads(Path(str(args.output) + '.manifest.json').read_text())
            report = verify_bytes(args.input.read_bytes(), args.output.read_bytes(), manifest)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'error: {exc}\n')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
