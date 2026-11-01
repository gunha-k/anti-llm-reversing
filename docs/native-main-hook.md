# SQLite, Vim, and Git main hooks

`tools/native_main_hook.py` builds a pinned open-source host, then links an original C program into it. An early host function directly calls the original main in the same process.

| Cover | Version | Output | Dispatch path |
|---|---|---|---|
| SQLite | 3.50.4 | `output/native-main-hook/sqlite/sqlite3` | `main -> main_init -> original main` |
| Vim | 9.1.0000 | `output/native-main-hook/vim/vim` | `main -> mch_early_init -> original main` |
| Git | 2.50.1 | `output/native-main-hook/git/git` | `main -> init_git -> original main` |

The SQLite main_init call is moved before setvbuf. Vim and Git use their existing first-call positions. argc/argv are saved in dedicated globals immediately before dispatch, without an additional function call or constructor. Existing host function signatures are retained.

```c
#define NATIVE_MAIN_DISPATCH() \
  do { (exit)(native_hook_real_main(native_hook_argc, native_hook_argv)); } while (0)
```

`(exit)(...)` bypasses Git's exit macro, avoiding uninitialized trace/common-exit paths. The hook function's actual calls are checked for the original main and exit. Existing host process-execution code remains in the binary.

## Build and inputs

Requires Linux x86-64, Python 3.12+, GCC, make, binutils, and ncurses development files for Vim. Fetch archives first:

```sh
python3 scripts/reproduce.py fetch
python3 tools/native_main_hook.py --host sqlite \
  --payload programs/main_hook/echo.c -o output/my-sqlite
python3 tools/native_main_hook.py --host vim \
  --payload /path/program.o --payload-ldflag=-lm -o output/my-vim
python3 tools/native_main_hook.py --host git \
  --payload /path/program.a --main-arity 3 -o output/my-git
```

Input `.c/.o/.a` files combined must define exactly one global main. `--main-arity 0`, `2` (default), and `3` select the signature; arity 3 passes `environ`. Use repeated `--payload-cflag` and `--payload-ldflag` for compiler/linker options, `--jobs` for make concurrency (default 2), `--downloads` for a different archive directory, and `--deps` for a development-package root (default `/`). The local extracted setup uses `--deps "$PWD/.local/sysroot"` after activation.

Archives are checksum-verified against pinned versions. The default downloads directory is `covers/native-hosts/downloads`. Each output uses a separate extracted `work/` tree, leaving cover archives untouched. Static payload archives are merged with whole-archive semantics, so unused archive members can add dependencies; use linker flags for normal external dependencies. Full ELF executables, LTO, C++/other language runtimes, and inferred main signatures are unsupported.

Output paths must be new and contain no spaces or shell metacharacters. Failed builds retain their logs. The final executable needs no original input files but still needs linked shared libraries and external resources.

## Build configuration and products

All hosts use `-O0 -g3 -fno-inline -fno-omit-frame-pointer -fno-lto` and `--no-gc-sections`. SQLite directly compiles shell.c/sqlite3.c without readline. Vim uses huge terminal features with GUI/X11/NLS/GPM/SELinux/XSMP disabled. Git omits optional curl/OpenSSL/expat/gettext/Perl/TclTk support. These configurations are not distribution-default builds.

Each output directory contains the executable, its `.original` baseline, `manifest.json`, `symbols.txt`, `main-hook.patch`, patched `sources/`, compiled `payload/`, extracted `work/`, build logs, and disassemblies. Copyright/license files remain in the source trees. Original public symbol names and debug information are preserved, but relinking can change addresses and bytes. Consult current manifests for sizes, counts, hashes, and version smoke-test output.

## Verify the supplied echo original

```sh
HOOK_ECHO_PORT=19090 ./output/native-main-hook/git/git
python3 tools/verify_native_main_hook.py --network
```

The sample binds `127.0.0.1:18080` unless `HOOK_ECHO_PORT` overrides it, serves one client until EOF, and exits. Even `--version` is forwarded to the echo original rather than invoking the host's ordinary version path.

The verifier checks the sample's input hash, first-call structure, direct dispatch, symbols/debug information, six invalid ports, empty/ASCII/UTF-8/128 KiB echo, executable identity without children, SIGTERM, and port conflicts. Results go to `output/native-main-hook/verification.json`. Without `--network`, TCP checks are recorded as `not_run`.

These checks are specific to the supplied echo program and do not run the full upstream suites. Loaders and constructors still run before main. Symbol collisions, initialization interference, argv[0], executable-relative resources, and stack traces may require integration changes for other originals.
