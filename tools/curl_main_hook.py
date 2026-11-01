#!/usr/bin/env python3
"""Link a C program into curl and call its main from curl's first initialization function."""

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / 'covers/curl-symbols/curl-8.22.0'
ENTRY = 'curl_hook_real_main'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(argv, *, cwd=None, log=None):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True,
                            text=True, timeout=120)
    if log is not None:
        with Path(log).open('a') as stream:
            stream.write('$ ' + shlex.join([str(x) for x in argv]) + '\n')
            stream.write(result.stdout + result.stderr)
    require(result.returncode == 0,
            f'{argv[0]} failed ({result.returncode}):\n{result.stderr[-6000:]}')
    return result.stdout


def build_variables(tree):
    keys = ('CC', 'DEFS', 'CPPFLAGS', 'curl_CPPFLAGS', 'AM_CFLAGS', 'CFLAGS',
            'curl_CFLAGS', 'curl_LDFLAGS', 'LDFLAGS', 'curl_LDADD', 'LIBS', 'curl_OBJECTS')
    # GNU make expands its own variables. No shell interpolation of those values.
    with tempfile.TemporaryDirectory(prefix='curl-hook-vars-') as folder:
        folder = Path(folder)
        query = folder / 'query.mk'
        query.write_text('.PHONY: hook_export_variables\nhook_export_variables:\n' +
                         ''.join(f'\t$(file >{folder / key},$({key}))\n' for key in keys))
        command(['make', '--no-print-directory', '-s', '-C', tree / 'src',
                 '-f', 'Makefile', '-f', query, 'hook_export_variables'])
        return {key: shlex.split((folder / key).read_text()) for key in keys}


def original_sources(tree, archive=None):
    names = ('tool_main.c', 'tool_stderr.c', 'tool_stderr.h')
    if archive is None:
        candidate = tree.parent / (tree.name + '.tar.xz')
        archive = candidate if candidate.is_file() else None
    if archive is None:
        return {name: (tree / 'src' / name).read_text() for name in names}
    with tarfile.open(archive) as bundle:
        sources = {}
        for name in names:
            members = [m for m in bundle.getmembers()
                       if m.isfile() and m.name.endswith('/src/' + name)]
            require(len(members) == 1, f'archive must contain exactly one src/{name}')
            with bundle.extractfile(members[0]) as stream:
                sources[name] = stream.read().decode()
    # Only tool_stderr.c may have the earlier echo experiment modifications.
    for name in ('tool_main.c', 'tool_stderr.h'):
        require(sources[name] == (tree / 'src' / name).read_text(),
                f'archive does not match configured tree: {name}')
    return sources


def patched_sources(original, arity):
    main = original['tool_main.c']
    prelude = re.compile(r'(\{\s*CURLcode result = CURLE_OK;\s*)tool_init_stderr\(\);')
    require(len(prelude.findall(main)) == 1,
            'unsupported curl main: tool_init_stderr must be the first call')
    main = prelude.sub(r'\1tool_init_stderr(argc, argv);', main)
    header = original['tool_stderr.h']
    require(header.count('void tool_init_stderr(void);') == 1, 'unexpected stderr declaration')
    header = header.replace('void tool_init_stderr(void);',
                            'void tool_init_stderr(int argc, char **argv);')
    stderr = original['tool_stderr.c']
    function = re.compile(r'void tool_init_stderr\(void\)\s*\{([^{}]*)\}')
    match = function.search(stderr)
    require(match is not None, 'cannot find original tool_init_stderr')
    body = re.sub(r'/\*.*?\*/', '', match[1], flags=re.S).strip()
    require(body == 'tool_stderr = stderr;',
            'tool_init_stderr is already modified; provide a matching pristine source archive')
    require('#include "tool_stderr.h"' in stderr, 'missing stderr header include')
    stderr = stderr.replace('#include "tool_stderr.h"',
                            '#include "tool_stderr.h"\n#include "curl_main_dispatch.h"')
    stderr = function.sub('void tool_init_stderr(int argc, char **argv)\n{\n'
                          '  CURL_DISPATCH_REAL_MAIN(argc, argv);\n}', stderr, count=1)
    signature = {0: 'void', 2: 'int argc, char **argv',
                 3: 'int argc, char **argv, char **envp'}[arity]
    arguments = {0: '', 2: '(argc), (argv)', 3: '(argc), (argv), environ'}[arity]
    dispatch = ('/* Generated: same-process transfer before curl initialization. */\n'
                '#ifndef CURL_MAIN_DISPATCH_H\n#define CURL_MAIN_DISPATCH_H\n'
                '#include <stdlib.h>\n' +
                ('extern char **environ;\n' if arity == 3 else '') +
                f'extern int {ENTRY}({signature});\n'
                '#define CURL_DISPATCH_REAL_MAIN(argc, argv) \\\n'
                f'  do {{ exit({ENTRY}({arguments})); }} while(0)\n'
                '#endif\n')
    return {'tool_main.c': main, 'tool_stderr.c': stderr, 'tool_stderr.h': header,
            'curl_main_dispatch.h': dispatch}


def symbols(path):
    result = []
    for line in command(['nm', '--defined-only', '--extern-only', '--format=posix', path]).splitlines():
        parts = line.split()
        if len(parts) >= 3 and len(parts[1]) == 1:
            result.append((parts[0], parts[1]))
    return result


def resolve_libraries(tokens, cwd):
    result = []
    for token in tokens:
        if token.endswith('.la'):
            archive = (cwd / token).resolve()
            match = re.search(r"^old_library='([^']+)'$", archive.read_text(), re.M)
            require(match, f'no static library recorded in {archive}')
            actual = archive.parent / '.libs' / match[1]
            require(actual.is_file(), f'static library missing: {actual}')
            result.append(str(actual))
        else:
            result.append(token)
    return result


def build(tree, payloads, output, *, arity=2, cflags=(), ldflags=(), archive=None):
    tree, output = Path(tree).resolve(), Path(output).absolute()
    payloads = [Path(p).resolve() for p in payloads]
    require(arity in (0, 2, 3), 'main arity must be 0, 2, or 3')
    require(payloads, 'at least one payload source/object/archive is required')
    require(not output.exists() and not output.is_symlink(), 'output directory already exists')
    for tool in ('make', 'gcc', 'nm', 'objcopy', 'objdump'):
        require(shutil.which(tool), f'required tool missing: {tool}')
    for path in payloads:
        require(path.is_file() and path.suffix in ('.c', '.o', '.a'),
                f'expected a C source, relocatable .o, or static .a: {path}')
    require((tree / 'src/Makefile').is_file(), 'provide a configured and built curl tree')
    config = build_variables(tree)
    require(config['CC'], 'missing curl compiler')
    sources = original_sources(tree, archive)
    patched = patched_sources(sources, arity)
    cwd = tree / 'src'
    objects = [(cwd / p).resolve() for p in config['curl_OBJECTS']]
    require(objects and all(p.is_file() for p in objects), 'curl object files are missing')
    replacements = {name: [p for p in objects if p.name == 'curl-' + name + '.o']
                    for name in ('tool_main', 'tool_stderr')}
    require(all(len(paths) == 1 for paths in replacements.values()),
            'requires separate curl-tool_main.o and curl-tool_stderr.o (non-unity build)')
    libraries = resolve_libraries(config['curl_LDADD'], cwd)
    baseline = {str(p): sha(p) for p in objects}
    baseline.update({str(tree / 'src' / name): sha(tree / 'src' / name) for name in sources})
    output.mkdir(parents=True)
    generated, compiled = output / 'sources', output / 'objects'
    generated.mkdir()
    compiled.mkdir()
    log = output / 'build.log'
    for name, text in patched.items():
        (generated / name).write_text(text)
    patch = ''.join(''.join(difflib.unified_diff(sources[name].splitlines(True),
                                               patched[name].splitlines(True),
                                               fromfile='a/src/' + name, tofile='b/src/' + name))
                    for name in sources)
    (output / 'curl-main-hook.patch').write_text(patch)
    inputs = []
    for index, path in enumerate(payloads):
        # Rename only symbols in copies, leaving source macros and original inputs intact.
        target = compiled / f'program-{index}{".a" if path.suffix == ".a" else ".o"}'
        if path.suffix == '.c':
            raw_object = compiled / f'program-{index}-original.o'
            command([*config['CC'], '-c', '-O0', '-g3', '-fPIC', '-fno-lto',
                     *cflags, path, '-o', raw_object], log=log)
        else:
            raw_object = path
        require(not any(n == ENTRY for n, _ in symbols(raw_object)),
                f'reserved symbol already present: {ENTRY}')
        command(['objcopy', '--redefine-sym', f'main={ENTRY}', raw_object, target], log=log)
        inputs.append(target)
    entries = [(p, kind) for p in inputs for name, kind in symbols(p) if name == ENTRY]
    require(len(entries) == 1 and entries[0][1] in ('T', 'W'),
            'payload inputs must define exactly one global main function')
    compile_flags = sum((config[key] for key in ('DEFS', 'curl_CPPFLAGS', 'CPPFLAGS',
                                                'AM_CFLAGS', 'CFLAGS', 'curl_CFLAGS')), [])
    rewritten = {}
    for name in ('tool_main', 'tool_stderr'):
        target = compiled / ('curl-' + name + '.o')
        command([*config['CC'], *compile_flags, '-I' + str(generated),
                 '-O0', '-g3', '-fno-lto', '-c', generated / (name + '.c'), '-o', target],
                cwd=cwd, log=log)
        rewritten[replacements[name][0]] = target
    binary = output / 'curl'
    command([*config['CC'], *config['AM_CFLAGS'], *config['CFLAGS'],
             *config['curl_LDFLAGS'], *config['LDFLAGS'], '-fno-lto', '-Wl,--no-gc-sections',
             '-o', binary, *(rewritten.get(p, p) for p in objects),
             '-Wl,--start-group', *inputs, *libraries, *ldflags, *config['LIBS'],
             '-Wl,--end-group'], cwd=cwd, log=log)
    require(all(sha(p) == value for p, value in baseline.items()), 'original curl tree changed')
    actual_symbols = symbols(binary)
    names = {name for name, _ in actual_symbols}
    require({'main', 'tool_init_stderr', ENTRY} <= names, 'required function symbols missing')
    functions = {}
    for name in ('main', 'tool_init_stderr', ENTRY):
        dis = command(['objdump', '-d', '--disassemble=' + name, binary])
        (output / (name + '.disassembly.txt')).write_text(dis)
        functions[name] = dis
    calls = re.findall(r'\bcall\s+[^<\n]*<([^>]+)>', functions['main'])
    require(calls and calls[0] == 'tool_init_stderr', 'hook is not the first call in curl main')
    hook_calls = re.findall(r'\bcall\s+[^<\n]*<([^>]+)>', functions['tool_init_stderr'])
    require(hook_calls and hook_calls[0] == ENTRY and 'exit@plt' in hook_calls,
            'hook must directly call payload main and exit with its return value')
    require(not any(re.search(r'(exec|fork|spawn|dlopen|system)', name) for name in hook_calls),
            'hook contains an unexpected process / loader call')
    original_names = {name for path in objects if path not in rewritten
                      for name, kind in symbols(path) if kind.isupper()}
    require(original_names <= names, 'original curl object symbols were lost')
    (output / 'symbols.txt').write_text(command(['nm', '-a', binary]))
    manifest = {
        'schema': 'curl-main-hook/v1', 'curl_tree': str(tree), 'output': str(binary),
        'sha256': sha(binary), 'main_arity': arity,
        'payloads': [{'path': str(p), 'sha256': sha(p)} for p in payloads],
        'call_path': ['main', 'tool_init_stderr', ENTRY, 'exit(payload_return_code)'],
        'macro': 'CURL_DISPATCH_REAL_MAIN', 'first_main_call_verified': True,
        'hook_calls': hook_calls, 'new_process_or_exec_in_hook': False,
        'original_curl_tree_unchanged': True, 'original_object_symbols_preserved': True,
        'payload_compiler_flags': list(cflags), 'payload_linker_flags': list(ldflags),
        'limitations': ['relinking changes addresses; original main bytes are not identical',
                        'ELF constructors run before main; shared dependencies still initialize',
                        'argv[0], /proc/self/exe, and executable-relative resources identify the combined file',
                        'matching native C ABI and declared main arity required'],
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl-tree', type=Path, default=DEFAULT_TREE)
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--payload', type=Path, nargs='+', required=True)
    parser.add_argument('-o', '--output-dir', type=Path, required=True)
    parser.add_argument('--main-arity', type=int, choices=(0, 2, 3), default=2)
    parser.add_argument('--payload-cflag', action='append', default=[])
    parser.add_argument('--payload-ldflag', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        result = build(args.curl_tree, args.payload, args.output_dir,
                       arity=args.main_arity, cflags=args.payload_cflag,
                       ldflags=args.payload_ldflag, archive=args.source_archive)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f'error: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
