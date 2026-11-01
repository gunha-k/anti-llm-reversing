# Working original programs

Put the program whose behavior must be retained in this directory. Keep originals separate from cover projects and generated results.

- `standalone/`: independent note, shell, and RLE programs, with normal C main functions.
- `main_hook/hello.c`: argument-printing example for same-process integration.
- `main_hook/echo.c`: localhost TCP echo server using `HOOK_ECHO_PORT` (default 18080).
- `jq`: official jq 1.8.2 Linux amd64 executable, downloaded and verified by the reproduction script. It is not committed.

Custom source trees or executables can be placed in their own subdirectories. The tools also accept paths outside this directory. C main-hook tools accept `.c`, `.o`, and `.a`; the ELF delegation tool accepts an executable via `--payload`. Generated binaries belong in `output/`.
