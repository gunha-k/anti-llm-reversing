#define _POSIX_C_SOURCE 200809L
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

enum { WORD, INPUT, OUTPUT, APPEND };
struct token { char *text; int kind; };

/* Compact words in place; quotes and backslash protect literal characters. */
static int tokenize(char *line, struct token *tokens, size_t capacity)
{
    char *src = line, *dst = line;
    size_t n = 0;
    while (*src) {
        while (isspace((unsigned char)*src)) ++src;
        if (!*src) break;
        if (n == capacity) return -1;
        char *start = dst;
        tokens[n].kind = WORD;
        if (*src == '<' || *src == '>') {
            tokens[n].kind = *src++ == '<' ? INPUT : OUTPUT;
            if (tokens[n].kind == OUTPUT && *src == '>') {
                ++src;
                tokens[n].kind = APPEND;
            }
        } else {
            int quote = 0;
            while (*src) {
                unsigned char c = (unsigned char)*src;
                if (!quote && (isspace(c) || c == '<' || c == '>')) break;
                ++src;
                if (c == '\\' && quote != '\'') {
                    if (!*src) return -1;
                    *dst++ = *src++;
                } else if (!quote && (c == '\'' || c == '"')) quote = c;
                else if (quote && c == quote) quote = 0;
                else *dst++ = (char)c;
            }
            if (quote) return -1;
        }
        ++n;
        tokens[n - 1].text = tokens[n - 1].kind == WORD
            ? strndup(start, (size_t)(dst - start)) : NULL;
        if (tokens[n - 1].kind == WORD && !tokens[n - 1].text) return -1;
    }
    return (int)n;
}

static int run(char *line, int previous, int *quit)
{
    struct token t[256] = {{0}};
    char *args[257], *input = NULL, *output = NULL;
    int append = 0, ac = 0, status = 2, count;
    count = tokenize(line, t, 256);
    if (count < 0) { fprintf(stderr, "Invalid syntax or too many tokens.\n"); goto done; }
    for (int i = 0; i < count; ++i) {
        if (t[i].kind == WORD) args[ac++] = t[i].text;
        else {
            int kind = t[i].kind;
            if (++i == count || t[i].kind != WORD) {
                fprintf(stderr, "Redirection requires a filename.\n"); goto done;
            }
            if (kind == INPUT) input = t[i].text;
            else { output = t[i].text; append = kind == APPEND; }
        }
    }
    args[ac] = NULL;
    if (!ac) { status = count ? 2 : previous; goto done; }
    if (!strcmp(args[0], "exit") || !strcmp(args[0], "cd") || !strcmp(args[0], "pwd")) {
        if (input || output) { fprintf(stderr, "Builtin redirection is unsupported.\n"); goto done; }
        if (!strcmp(args[0], "exit")) {
            char *end;
            long code = previous;
            if (ac > 2) goto done;
            if (ac == 2) {
                errno = 0;
                code = strtol(args[1], &end, 10);
                if (errno || end == args[1] || *end || code < 0 || code > 255) goto done;
            }
            *quit = 1; status = (int)code;
        } else if (!strcmp(args[0], "cd")) {
            const char *path = ac == 1 ? getenv("HOME") : args[1];
            if (ac > 2 || !path) goto done;
            status = chdir(path) ? 1 : 0;
            if (status) perror("cd");
        } else {
            char *path;
            if (ac != 1) goto done;
            path = getcwd(NULL, 0);
            status = path ? (puts(path) == EOF) : 1;
            if (!path) perror("pwd");
            free(path);
        }
    } else {
        pid_t child, waited;
        int ws;
        fflush(NULL);
        child = fork();
        if (child < 0) { perror("fork"); status = 1; goto done; }
        if (child == 0) {
            if (input || output) {
                for (int fd = 0; fd < 2; ++fd) {
                    const char *path = fd ? output : input;
                    int opened;
                    if (!path) continue;
                    opened = open(path, fd ? O_WRONLY | O_CREAT | (append ? O_APPEND : O_TRUNC) : O_RDONLY, 0666);
                    if (opened < 0) { perror(path); _exit(1); }
                    if (dup2(opened, fd) < 0) { perror("dup2"); _exit(1); }
                    if (opened != fd) close(opened);
                }
            }
            execvp(args[0], args);
            status = errno == ENOENT ? 127 : 126;
            perror(args[0]);
            _exit(status);
        }
        do { waited = waitpid(child, &ws, 0); } while (waited < 0 && errno == EINTR);
        if (waited < 0) { perror("waitpid"); status = 1; }
        else status = WIFEXITED(ws) ? WEXITSTATUS(ws) : 128 + WTERMSIG(ws);
    }
done:
    for (size_t i = 0; i < 256; ++i) free(t[i].text);
    return status;
}

int main(int argc, char **argv)
{
    char *line = NULL;
    size_t capacity = 0;
    int status = 0, quit = 0;
    if (argc == 3 && !strcmp(argv[1], "-c")) {
        line = strdup(argv[2]);
        if (!line) return 1;
        status = run(line, 0, &quit);
        free(line);
        return status;
    }
    if (argc != 1) { fprintf(stderr, "Usage: %s [-c COMMAND]\n", argv[0]); return 2; }
    while (!quit) {
        if (isatty(STDIN_FILENO)) { fputs("mini$ ", stdout); fflush(stdout); }
        if (getline(&line, &capacity, stdin) < 0) break;
        status = run(line, status, &quit);
    }
    if (ferror(stdin)) { perror("stdin"); status = 1; }
    free(line);
    return status;
}
