#include <stdio.h>
#include <string.h>

static int encode(FILE *in, FILE *out)
{
    int current, next;
    unsigned count;
    if (fwrite("RLE1", 1, 4, out) != 4) return 1;
    current = fgetc(in);
    while (current != EOF) {
        count = 1;
        while ((next = fgetc(in)) == current && count < 255) ++count;
        if (fputc((int)count, out) == EOF || fputc(current, out) == EOF) return 1;
        current = next;
    }
    return ferror(in) != 0;
}

static int decode(FILE *in, FILE *out)
{
    char magic[4];
    int count, byte;
    if (fread(magic, 1, 4, in) != 4 || memcmp(magic, "RLE1", 4)) return 1;
    while ((count = fgetc(in)) != EOF) {
        byte = fgetc(in);
        if (!count || byte == EOF) return 1;
        for (int i = 0; i < count; ++i)
            if (fputc(byte, out) == EOF) return 1;
    }
    return ferror(in) != 0;
}

int main(int argc, char **argv)
{
    FILE *in, *out;
    int failed;
    if (argc != 4 || (strcmp(argv[1], "compress") && strcmp(argv[1], "decompress"))) {
        fprintf(stderr, "Usage: %s compress|decompress INPUT OUTPUT\n", argv[0]);
        return 2;
    }
    in = fopen(argv[2], "rb");
    if (!in) { perror(argv[2]); return 1; }
    /* Exclusive creation protects both existing output and the input file. */
    out = fopen(argv[3], "wbx");
    if (!out) { perror(argv[3]); fclose(in); return 1; }
    failed = !strcmp(argv[1], "compress") ? encode(in, out) : decode(in, out);
    if (fclose(in)) failed = 1;
    if (fclose(out)) failed = 1;
    if (failed) {
        fprintf(stderr, "Invalid RLE data or file I/O failure.\n");
        if (remove(argv[3])) perror("remove incomplete output");
    }
    return failed ? 1 : 0;
}
