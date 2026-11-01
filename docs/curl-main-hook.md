# curl early-main integration

`tools/curl_main_hook.py` links an original program into a new curl executable. It accepts C sources, relocatable objects, and static archives, while preserving original inputs and the configured baseline curl tree.

```text
ELF loader / C runtime
  -> curl main(argc, argv)
  -> tool_init_stderr(argc, argv), the first call in main
  -> CURL_DISPATCH_REAL_MAIN
  -> curl_hook_real_main(argc, argv)
  -> exit(original return value)
```

The hook runs before stderr assignment, descriptor repair, SIGPIPE changes, memory tracking, global configuration, and curl's normal operation. The macro compiles to a direct call to the original main and then `exit`, which flushes stdio and invokes atexit handlers/destructors. No new launcher, fork, execve, or dlopen path is added. The original program can itself use these functions.

## Build

First prepare curl using `python3 scripts/reproduce.py curl`. The default configured tree is `covers/curl-symbols/curl-8.22.0`, with its archive beside it. The tool does not download sources.

```sh
python3 tools/curl_main_hook.py \
  --payload programs/main_hook/hello.c -o output/my-hook
./output/my-hook/curl 'first argument' 'second argument'
python3 tools/curl_main_hook.py --payload /path/program.o -o output/object-hook
python3 tools/curl_main_hook.py --payload /path/program.a -o output/archive-hook
python3 tools/curl_main_hook.py \
  --payload /path/main.c /path/helper.c /path/support.a \
  --payload-cflag=-I/path/include --payload-ldflag=-lm -o output/multi-hook
```

Inputs combined must expose exactly one main definition. Copies are renamed with `objcopy --redefine-sym main=curl_hook_real_main`; cross-unit references are renamed too. `curl_hook_real_main` is reserved.

| Signature | Option |
|---|---|
| `int main(int, char **)` | `--main-arity 2` (default) |
| `int main(void)` | `--main-arity 0` |
| `int main(int, char **, char **)` | `--main-arity 3`; passes current `environ` |

The signature is explicit because object symbols do not describe argument types. Sources compile with debug information and PIC. Objects/archives must match the native ABI and linking model; recompile with `-fPIC` if needed. Complete ELF executable inputs, LTO, C++ runtimes, and arbitrary language runtimes are outside the supported scope.

Use `--curl-tree` for a different configured tree and `--source-archive` for its pristine archive. Separate tool_main/tool_stderr objects are required. Changed or previously hooked function structures fail with an error. Source files are read from the archive without overwriting the baseline tree.

## Echo example

```sh
python3 tools/curl_main_hook.py \
  --payload programs/main_hook/echo.c -o output/my-echo-hook
HOOK_ECHO_PORT=19090 ./output/my-echo-hook/curl
```

The example handles one connection on `127.0.0.1` and exits after EOF. Its default port is 18080. This behavior belongs to the original echo program rather than the integration tool.

## Products and checks

A new output directory contains `curl`, patched `sources/`, compiled `objects/`, `curl-main-hook.patch`, `manifest.json`, `build.log`, `symbols.txt`, and disassemblies. Failed builds retain diagnostics. The generated executable does not require the original `.c/.o/.a` files, but shared libraries and program resources remain necessary.

Build checks verify main's first call, direct dispatch/exit, retained public symbols, and unchanged baseline source/object hashes. Relinking can change addresses and machine-code bytes.

```sh
ELF_LAB_NETWORK_TESTS=1 python3 -m unittest discover -s tests -p test_curl_main_hook.py -v
```

Nine tests cover source/object/archive inputs, multiple sources and flags, all main arities, arguments/environment/cwd/binary streams/status/signals, atexit/destructors, SIGPIPE and closed stdin, PID/executable identity, and localhost echo including UTF-8 and 128 KiB data. Network tests require the environment flag.

ELF loaders, constructors, and library initialization precede main. Shared symbols, constructors, argv[0], executable paths, nearby resources, and stack traces can differ from standalone execution. Tested examples do not establish universal equivalence.
