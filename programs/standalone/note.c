#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <string.h>

/* A note is an ordinary UTF-8 (or other text) file. */
int main(int argc, char **argv)
{
    FILE *fp;
    int failed = 0;
    if (argc < 3 || (strcmp(argv[1], "read") &&
                     strcmp(argv[1], "write") && strcmp(argv[1], "append"))) {
        fprintf(stderr, "Usage: %s read FILE | write FILE TEXT... | append FILE TEXT...\n", argv[0]);
        return 2;
    }
    if (!strcmp(argv[1], "read")) {
        unsigned char buf[4096];
        size_t n;
        if (argc != 3) return 2;
        fp = fopen(argv[2], "rb");
        if (!fp) { perror(argv[2]); return 1; }
        while ((n = fread(buf, 1, sizeof(buf), fp)) != 0)
            if (fwrite(buf, 1, n, stdout) != n) { failed = 1; break; }
        failed |= ferror(fp) != 0;
        if (fclose(fp)) failed = 1;
        if (fflush(stdout)) failed = 1;
    } else {
        if (argc < 4) { fprintf(stderr, "Text is required.\n"); return 2; }
        fp = fopen(argv[2], !strcmp(argv[1], "write") ? "wb" : "ab");
        if (!fp) { perror(argv[2]); return 1; }
        for (int i = 3; i < argc; ++i) {
            if (i > 3 && fputc(' ', fp) == EOF) failed = 1;
            if (fputs(argv[i], fp) == EOF) failed = 1;
        }
        if (fputc('\n', fp) == EOF) failed = 1;
        if (fclose(fp)) failed = 1;
    }
    if (failed) fprintf(stderr, "Note I/O failed.\n");
    return failed ? 1 : 0;
}
