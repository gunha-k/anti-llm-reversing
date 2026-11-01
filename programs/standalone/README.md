# Standalone C originals

These three programs are independent originals with no cover transformation applied. Each object exports a normal `main(int, char **)`. Build with `make -C programs/standalone`; Linux/POSIX, GCC, and libc are required. Default objects contain debug information and PIC.

## Notes

```sh
./programs/standalone/note write memo.txt 'first note'
./programs/standalone/note append memo.txt 'another line'
./programs/standalone/note read memo.txt
```

`write` overwrites the file; `append` adds a line. Text arguments are joined with spaces and end with a newline.

## Small shell

```sh
./programs/standalone/minish
./programs/standalone/minish -c 'printf "%s\n" "hello world" > message.txt'
./programs/standalone/minish -c 'cat < message.txt'
```

Supports cd, pwd, exit with status 0–255, PATH-based external commands, quotes, backslash escapes, and external-command input/output/append redirection. One command per line and at most 256 tokens are supported. Variable expansion, globbing, pipes, semicolons, job control, and built-in redirection are unsupported. Quoting is simpler than full POSIX shell syntax. External commands use fork/execvp.

## RLE compression

```sh
./programs/standalone/rle compress memo.txt memo.rle
./programs/standalone/rle decompress memo.rle restored.txt
cmp memo.txt restored.txt
```

The private format starts with ASCII RLE1 followed by count (1–255)/byte pairs. Empty and arbitrary binary files are supported; low repetition can increase size. Existing outputs are rejected, and partial outputs are removed on invalid data or I/O errors. There is no checksum, so not every corruption is detectable.
