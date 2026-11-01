#!/usr/bin/env python3
"""Build pinned SQLite/Vim/Git main-hook experiments from their native C sources."""

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

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'covers/native-hosts'
ENTRY = 'native_hook_real_main'
DEBUG = ['-O0', '-g3', '-fno-inline', '-fno-omit-frame-pointer', '-fno-lto']
HOSTS = {
    'sqlite': {
        'version': '3.50.4', 'archive': 'sqlite-autoconf-3500400.tar.gz',
        'sha256': 'a3db587a1b92ee5ddac2f66b3edb41b26f9c867275782d46c3a088977d6a5b18',
        'url': 'https://www.sqlite.org/2025/sqlite-autoconf-3500400.tar.gz',
        'root': 'sqlite-autoconf-3500400', 'binary': 'sqlite3', 'hook': 'main_init',
        'files': ['shell.c'], 'markers': ['sqlite3_open', 'sqlite3_step', 'sqlite3_prepare_v2'],
    },
    'vim': {
        'version': '9.1.0000', 'archive': 'vim-9.1.0000.tar.gz',
        'sha256': '8d2a74e358be9cf260174e15e2e29dba4773f2670718b5bf728db6f54b90e25d',
        'url': 'https://codeload.github.com/vim/vim/tar.gz/refs/tags/v9.1.0000',
        'root': 'vim-9.1.0000', 'binary': 'vim', 'hook': 'mch_early_init',
        'files': ['src/main.c', 'src/os_unix.c'],
        'markers': ['do_cmdline', 'main_loop', 'mch_call_shell'],
    },
    'git': {
        'version': '2.50.1', 'archive': 'git-2.50.1.tar.xz',
        'sha256': '7e3e6c36decbd8f1eedd14d42db6674be03671c2204864befa2a41756c5c8fc4',
        'url': 'https://www.kernel.org/pub/software/scm/git/git-2.50.1.tar.xz',
        'root': 'git-2.50.1', 'binary': 'git', 'hook': 'init_git',
        'files': ['common-main.c', 'common-init.c'],
        'markers': ['cmd_main', 'cmd_log', 'cmd_commit', 'start_command'],
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv, cwd, log, env=None):
    with Path(log).open('a') as stream:
        stream.write('$ ' + shlex.join([str(a) for a in argv]) + '\n')
        stream.flush()
        result = subprocess.run([str(a) for a in argv], cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, env=env, timeout=1200)
    require(result.returncode == 0,
            f'{argv[0]} failed ({result.returncode}); see {log}')


def capture(argv):
    return subprocess.check_output([str(x) for x in argv], text=True, timeout=60)


def defined(path):
    result = set()
    for line in capture(['nm', '--defined-only', '--format=posix', path]).splitlines():
        parts = line.split()
        if len(parts) >= 3 and len(parts[1]) == 1:
            result.add((parts[0], parts[1]))
    return result


def extract(host, output, downloads):
    spec = HOSTS[host]
    archive = downloads / spec['archive']
    require(archive.is_file(), f'download {spec["url"]} to {archive}')
    require(sha(archive) == spec['sha256'], f'archive SHA-256 mismatch: {archive}')
    work = output / 'work'
    work.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(work, filter='data')
    return work / spec['root']


def compile_payload(payloads, out, arity, cflags):
    objects = out / 'payload'
    objects.mkdir()
    inputs = []
    for i, path in enumerate(payloads):
        require(path.is_file() and path.suffix in ('.c', '.o', '.a'),
                f'expected C source / relocatable .o / static .a: {path}')
        target = objects / f'input-{i}.o'
        if path.suffix == '.c':
            run(['gcc', *DEBUG, '-fPIC', *cflags, '-c', path, '-o', target], out, out / 'build.log')
        else:
            target = path
        inputs.append(target)
    context = objects / 'context.c'
    context.write_text('int native_hook_argc;\nchar **native_hook_argv;\n')
    run(['gcc', *DEBUG, '-fPIC', '-c', context, '-o', objects / 'context.o'], out, out / 'build.log')
    combined = objects / 'combined.o'
    run(['ld', '-r', '-o', combined, objects / 'context.o', '--whole-archive',
         *inputs, '--no-whole-archive'], out, out / 'build.log')
    names = defined(combined)
    require(('main', 'T') in names or ('main', 'W') in names, 'payload must define main')
    require(not any(n == ENTRY for n, _ in names), f'reserved symbol: {ENTRY}')
    target = objects / 'program.o'
    run(['objcopy', '--redefine-sym', 'main=' + ENTRY, combined, target], out, out / 'build.log')
    signature = {0: 'void', 2: 'int, char **', 3: 'int, char **, char **'}[arity]
    args = {0: '', 2: 'native_hook_argc, native_hook_argv',
            3: 'native_hook_argc, native_hook_argv, environ'}[arity]
    header = (
        '/* Generated, explicit same-process main hook for a local experiment. */\n'
        '#ifndef NATIVE_MAIN_DISPATCH_H\n#define NATIVE_MAIN_DISPATCH_H\n'
        '#include <stdlib.h>\nextern int native_hook_argc;\nextern char **native_hook_argv;\n'
        + ('extern char **environ;\n' if arity == 3 else '')
        + f'extern int {ENTRY}({signature});\n'
        '#define NATIVE_MAIN_CONTEXT(argc, argv) \\\n'
        '  do { native_hook_argc = (argc); native_hook_argv = (char **)(argv); } while (0)\n'
        '#define NATIVE_MAIN_DISPATCH() \\\n'
        f'  do {{ (exit)({ENTRY}({args})); }} while (0)\n'
        '#endif\n'
    )
    return target, header


def replace_once(text, old, new):
    require(text.count(old) == 1, f'expected one source anchor: {old[:90]!r}')
    return text.replace(old, new, 1)


def patch_sources(host, tree, header, out):
    spec = HOSTS[host]
    source = {name: (tree / name).read_text() for name in spec['files']}
    patched = source.copy()
    if host == 'sqlite':
        text = patched['shell.c']
        text = replace_once(text, 'static void main_init(ShellState *data) {',
                            '#include "native_main_dispatch.h"\n'
                            'static void main_init(ShellState *data) {\n  NATIVE_MAIN_DISPATCH();')
        text = replace_once(text, '  main_init(&data);',
                            '  /* main_init was moved before stdio and signal initialization. */')
        text = replace_once(text, '  setvbuf(stderr, 0, _IONBF, 0);',
                            '  NATIVE_MAIN_CONTEXT(argc, argv);\n  main_init(&data);\n'
                            '  setvbuf(stderr, 0, _IONBF, 0);')
        patched['shell.c'] = text
    elif host == 'vim':
        patched['src/main.c'] = replace_once(patched['src/main.c'],
            '    mch_early_init();',
            '    NATIVE_MAIN_CONTEXT(argc, argv);\n    mch_early_init();')
        patched['src/main.c'] = replace_once(patched['src/main.c'], '#include "vim.h"',
            '#include "vim.h"\n#include "native_main_dispatch.h"')
        patched['src/os_unix.c'] = replace_once(patched['src/os_unix.c'],
            'mch_early_init(void)\n{', 'mch_early_init(void)\n{\n    NATIVE_MAIN_DISPATCH();')
        patched['src/os_unix.c'] = replace_once(patched['src/os_unix.c'], '#include "vim.h"',
            '#include "vim.h"\n#include "native_main_dispatch.h"')
    else:
        patched['common-main.c'] = replace_once(patched['common-main.c'],
            '\tinit_git(argv);', '\tNATIVE_MAIN_CONTEXT(argc, argv);\n\tinit_git(argv);')
        patched['common-init.c'] = replace_once(patched['common-init.c'],
            'void init_git(const char **argv)\n{',
            'void init_git(const char **argv)\n{\n\tNATIVE_MAIN_DISPATCH();')
        for name in spec['files']:
            patched[name] = replace_once(patched[name], '#include "common-init.h"',
                '#include "common-init.h"\n#include "native_main_dispatch.h"')
    patch = ''
    snapshots = out / 'sources'
    snapshots.mkdir()
    for name, text in patched.items():
        patch += ''.join(difflib.unified_diff(source[name].splitlines(True), text.splitlines(True),
                                            fromfile='a/' + name, tofile='b/' + name))
        (tree / name).write_text(text)
        copy = snapshots / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(text)
    header_dir = tree / 'src' if host == 'vim' else tree
    (header_dir / 'native_main_dispatch.h').write_text(header)
    (snapshots / 'native_main_dispatch.h').write_text(header)
    (out / 'main-hook.patch').write_text(patch)


def recipe(host, tree, out, jobs, deps):
    log = out / 'build.log'
    debug = ' '.join(DEBUG)
    if host == 'sqlite':
        commands = [['gcc', *DEBUG, '-c', 'sqlite3.c', '-o', 'sqlite3.o'],
                    ['gcc', *DEBUG, '-c', 'shell.c', '-o', 'shell.o']]
        for cmd in commands:
            run(cmd, tree, log)
        link = ['gcc', *DEBUG, '-Wl,--no-gc-sections', '-o', 'sqlite3',
                'shell.o', 'sqlite3.o', '-lm', '-ldl', '-lpthread']
        run(link, tree, log)
        return tree / 'sqlite3', {'cwd': str(tree), 'link': link,
                                 'recompile': commands[1]}
    if host == 'vim':
        include = deps / 'usr/include'
        lib = deps / 'usr/lib/x86_64-linux-gnu'
        require((include / 'ncurses.h').is_file(), 'ncurses headers missing; see docs/native-main-hook.md')
        # The development package expects the runtime SONAME next to its linker symlink.
        soname = lib / 'libtinfo.so.6'
        if not soname.exists():
            soname.symlink_to('/usr/lib/x86_64-linux-gnu/libtinfo.so.6')
        env = dict(os.environ, CFLAGS=debug, CPPFLAGS='-I' + str(include),
                   LDFLAGS='-L' + str(lib) + ' -Wl,--no-gc-sections')
        run(['./configure', '--with-features=huge', '--enable-gui=no', '--without-x',
             '--disable-nls', '--disable-gpm', '--disable-selinux', '--disable-xsmp',
             '--with-tlib=tinfo'], tree, log, env)
        cwd = tree / 'src'
        args = ['make', '-j' + str(jobs), 'LINK_AS_NEEDED=no', 'vim']
        run(args, cwd, log)
        return cwd / 'vim', {'cwd': str(cwd), 'make': args,
                            'ldflags': env['LDFLAGS']}
    args = ['make', '-j' + str(jobs), 'V=1', 'NO_GETTEXT=YesPlease', 'NO_CURL=YesPlease',
            'NO_OPENSSL=YesPlease', 'NO_EXPAT=YesPlease', 'NO_PERL=YesPlease', 'NO_TCLTK=YesPlease',
            'CFLAGS=' + debug, 'LDFLAGS=-Wl,--no-gc-sections', 'git']
    run(args, tree, log)
    return tree / 'git', {'cwd': str(tree), 'make': args,
                         'ldflags': '-Wl,--no-gc-sections'}


def relink(host, recipe, program, ldflags, out):
    cwd = Path(recipe['cwd'])
    log = out / 'build.log'
    if host == 'sqlite':
        run(recipe['recompile'], cwd, log)
        command = [*recipe['link'], str(program), *ldflags]
    else:
        flags = recipe['ldflags'] + ' ' + shlex.join([str(program), *ldflags])
        command = [x for x in recipe['make'] if not x.startswith('LDFLAGS=')]
        command.insert(-1, 'LDFLAGS=' + flags)
    run(command, cwd, log)
    recipe['hook_build'] = command


def verify_structure(host, original, final, out):
    spec = HOSTS[host]
    disassembly = {}
    for name in ('main', spec['hook'], ENTRY):
        text = capture(['objdump', '-d', '--disassemble=' + name, final])
        (out / (name + '.disassembly.txt')).write_text(text)
        disassembly[name] = text
    calls = lambda name: re.findall(r'\bcall\s+[^<\n]*<([^>]+)>', disassembly[name])
    main_calls, hook_calls = calls('main'), calls(spec['hook'])
    require(main_calls and main_calls[0] == spec['hook'], 'hook is not main\'s first function call')
    require(hook_calls == [ENTRY, 'exit@plt'],
            f'unexpected transfer calls (expected direct main + libc exit): {hook_calls}')
    before, after = defined(original), defined(final)
    # Compare external definitions; file-local compiler labels are not a stable ABI.
    public_before = {n for n, t in before if t.isupper() and t not in ('A',)}
    public_after = {n for n, t in after if t.isupper() and t not in ('A',)}
    missing = public_before - public_after
    require(not missing, f'original public symbols lost: {sorted(missing)[:20]}')
    require(set(spec['markers']) <= {n for n, _ in after}, 'host functionality symbols missing')
    sections = capture(['readelf', '-SW', final])
    require('.symtab' in sections and '.debug_info' in sections, 'missing symbols / debug info')
    (out / 'symbols.txt').write_text(capture(['nm', '-a', final]))
    return {'first_main_call': main_calls[0], 'transfer_calls': hook_calls,
            'no_exec_or_subprocess_in_transfer': True, 'original_public_symbols_preserved': True,
            'original_public_symbol_count': len(public_before),
            'final_public_symbol_count': len(public_after), 'host_markers': spec['markers'],
            'symtab_and_debug_info': True}


def build(host, payloads, out, *, arity=2, cflags=(), ldflags=(), jobs=2,
          downloads=CACHE / 'downloads', deps=Path('/')):
    out = Path(out).absolute()
    require(not out.exists() and not out.is_symlink(), 'output directory already exists')
    require(re.fullmatch(r'[A-Za-z0-9_./-]+', str(out)),
            'native Makefiles require an output path without spaces or shell metacharacters')
    require(arity in (0, 2, 3) and jobs > 0, 'invalid main arity / job count')
    payloads = [Path(p).resolve() for p in payloads]
    require(payloads, 'at least one payload input required')
    for tool in ('gcc', 'ld', 'make', 'nm', 'objcopy', 'objdump', 'readelf'):
        require(shutil.which(tool), f'missing build tool: {tool}')
    out.mkdir(parents=True)
    spec = HOSTS[host]
    print(f'[{host}] extracting pinned source and compiling payload', flush=True)
    tree = extract(host, out, Path(downloads).resolve())
    program, header = compile_payload(payloads, out, arity, cflags)
    print(f'[{host}] building original debug executable (see {out / "build.log"})', flush=True)
    built, instructions = recipe(host, tree, out, jobs, Path(deps).resolve())
    original = out / (spec['binary'] + '.original')
    shutil.copy2(built, original)
    original_version = subprocess.run([str(original), '--version' if host != 'sqlite' else '-version'],
                                      capture_output=True, text=True, timeout=10)
    require(original_version.returncode == 0, 'original version smoke test failed')
    print(f'[{host}] patching early function and linking same-process main', flush=True)
    patch_sources(host, tree, header, out)
    relink(host, instructions, program, ldflags, out)
    final = out / spec['binary']
    shutil.copy2(built, final)
    checks = verify_structure(host, original, final, out)
    manifest = {
        'schema': 'native-main-hook/v1', 'host': host, 'version': spec['version'],
        'source_url': spec['url'], 'archive_sha256': spec['sha256'],
        'binary': str(final), 'sha256': sha(final), 'original_sha256': sha(original),
        'original_version_output': original_version.stdout.splitlines()[:3],
        'main_arity': arity, 'macro': 'NATIVE_MAIN_DISPATCH',
        'call_path': ['main', spec['hook'], ENTRY, 'exit(payload_return_code)'],
        'payloads': [{'path': str(p), 'sha256': sha(p)} for p in payloads],
        'compiler_flags': DEBUG, 'payload_cflags': list(cflags), 'payload_ldflags': list(ldflags),
        'verification': checks, 'build_recipe': instructions,
        'limitations': ['ELF/shared-library constructors still run before main',
                        'argv[0] and executable-relative resources refer to the combined file',
                        'relinking changes function addresses and main machine code',
                        'native C ABI only; input archives are included with --whole-archive'],
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'[{host}] built and structurally verified: {final}', flush=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=HOSTS, required=True)
    parser.add_argument('--payload', type=Path, nargs='+', required=True)
    parser.add_argument('-o', '--output-dir', type=Path, required=True)
    parser.add_argument('--main-arity', type=int, choices=(0, 2, 3), default=2)
    parser.add_argument('--payload-cflag', action='append', default=[])
    parser.add_argument('--payload-ldflag', action='append', default=[])
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--downloads', type=Path, default=CACHE / 'downloads')
    parser.add_argument('--deps', type=Path, default=Path('/'))
    args = parser.parse_args(argv)
    try:
        build(args.host, args.payload, args.output_dir, arity=args.main_arity,
              cflags=args.payload_cflag, ldflags=args.payload_ldflag, jobs=args.jobs,
              downloads=args.downloads, deps=args.deps)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
