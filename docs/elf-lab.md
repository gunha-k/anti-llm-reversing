# Generic ELF execution tool

`tools/elf_lab.py` accepts a cover ELF and a separate original executable. The cover's code, strings, symbols, and debug information remain visible, while a new entry point determines the actual behavior. The inputs are preserved.

## Delegate to an original executable

```sh
python3 tools/elf_lab.py inspect covers/bin/curl
python3 tools/elf_lab.py build covers/bin/curl \
  --payload programs/jq -o output/my-experiment/curl
printf '{"items":[1,2,3]}\n' | ./output/my-experiment/curl '.items | add'
python3 tools/elf_lab.py verify covers/bin/curl output/my-experiment/curl
```

The adapter calls `execve` without creating a child. It sets `argv[0]` to the original's absolute path and forwards remaining arguments. The environment, working directory, standard streams, and inheritable file descriptors are preserved. Exit codes and signals come from the original. Symlink names are retained when selecting the original. Comparison is against direct execution at the same absolute path; values such as PID and time naturally differ.

Keep the original at its recorded path. This is not a single-file embedded package. `/proc/self/exe` identifies the executed original. Resources and `$ORIGIN` libraries are resolved beside that original. Its loader and libraries remain required.

The adapter omits the cover's interpreter from the new program headers, bypassing the cover loader initialization and original entry point. The adapter itself does not need libc. The manifest records cover, output, and original paths/hashes. `verify` checks that the original still exists with the recorded hash. Runtime dispatch executes the current file at that path; it does not authenticate or pin it. A missing target exits 127; other exec errors exit 126.

## Built-in echo mode

Without `--payload`, the tool embeds a single-connection localhost echo server:

```sh
python3 tools/elf_lab.py build /usr/bin/ls -o output/my-echo/ls --port 19090
ELF_ECHO_PORT=19091 ./output/my-echo/ls
```

The default port is 18080. `ELF_ECHO_PORT` overrides the build-time port. Valid ports are 1–65535; an empty override is invalid. It binds only to `127.0.0.1`, waits for one connection, echoes until EOF, and exits 0. Port, bind, socket, and I/O errors exit 1. Original command arguments are ignored. `--port` cannot be combined with `--payload`.

```sh
python3 - <<'PYCLIENT'
import socket
with socket.create_connection(('127.0.0.1', 19091), timeout=3) as client:
    client.sendall(b'hello\n')
    client.shutdown(socket.SHUT_WR)
    chunks = []
    while part := client.recv(4096):
        chunks.append(part)
    print(b''.join(chunks).decode(), end='')
PYCLIENT
```

In echo mode the cover's dynamic loader and library constructors can run before the new entry point. The cover's original main is bypassed in both modes.

## Structure and supported inputs

The adapter uses position-independent code in an added RX LOAD segment. The program-header table is mapped there and PT_PHDR is updated. Original LOAD addresses, instructions, symbols, and strings are preserved. Original file bytes other than the 64-byte ELF header are retained. Inputs with sections gain `.text.exec_lab` or `.text.echo_lab`. Existing build IDs are preserved; use manifest SHA-256 for output identity.

The tool supports Linux x86-64 little-endian ELF64 ET_EXEC/ET_DYN executables, including static/dynamic, PIE/static PIE, stripped/unstripped, and files without section tables. It does not support PE, Mach-O, ARM, ELF32, shared-library-only inputs, or extended ELF header counts. Special loaders, self-checking binaries, and initialization side effects may need separate work. `inspect` is structural inspection, not an execution test.

Outputs must be new paths. Paths with spaces should be shell-quoted. A sibling `NAME.manifest.json` records hashes, entry points, adapter details, and structure checks; it is not a digital signature. Neither debug-path replacement nor string/symbol rewriting is included.

## Verification

```sh
ELF_LAB_NETWORK_TESTS=1 python3 -m unittest discover -s tests -p test_elf_lab.py -v
```

Tests cover six host forms, execution inheritance, output/error/exit/signal behavior, symlink and special-character paths, preserved symbols, reproducibility, malformed inputs, overwrite protection, missing/changed targets, corruption detection, and localhost echo/port conflicts. Without the environment flag, two network tests are skipped. Temporary products and test servers are cleaned up.
