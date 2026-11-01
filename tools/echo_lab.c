/* Position-independent, libc-free Linux x86-64 loopback echo experiment. */
#ifndef DEFAULT_PORT
#define DEFAULT_PORT 18080
#endif

static long call(long number, long a, long b, long c, long d, long e)
{
    register long r10 __asm__("r10") = d;
    register long r8 __asm__("r8") = e;
    register long r9 __asm__("r9") = 0;
    long result;
    __asm__ volatile("syscall" : "=a"(result)
                     : "a"(number), "D"(a), "S"(b), "d"(c),
                       "r"(r10), "r"(r8), "r"(r9)
                     : "rcx", "r11", "memory");
    return result;
}
#define SC(n,a,b,c,d,e) call(n,(long)(a),(long)(b),(long)(c),(long)(d),(long)(e))

/* Initial stack: argc, argv[], NULL, envp[], NULL. No host ABI assumptions. */
__attribute__((used, visibility("hidden")))
int echo_lab_run(long *stack)
{
    const char prefix[] = "ELF_ECHO_PORT=";
    char **env = (char **)(stack + stack[0] + 2);
    unsigned port = DEFAULT_PORT;
    for (; *env; ++env) {
        unsigned i = 0;
        while (prefix[i] && (*env)[i] == prefix[i]) ++i;
        if (!prefix[i]) {
            const char *p = *env + i;
            port = 0;
            if (!*p) return 1;
            for (; *p; ++p) {
                if (*p < '0' || *p > '9') return 1;
                port = port * 10 + (unsigned)(*p - '0');
                if (port > 65535) return 1;
            }
            if (!port) return 1;
            break;
        }
    }
    unsigned char address[16] = {
        2, 0, (unsigned char)(port >> 8), (unsigned char)port, 127, 0, 0, 1
    };
    char buffer[4096];
    int yes = 1, result = 1;
    long listener = SC(41, 2, 1, 0, 0, 0), client = -1;
    if (listener < 0) goto done;
    if (SC(54, listener, 1, 2, &yes, sizeof(yes)) < 0) goto done;
    if (SC(49, listener, address, sizeof(address), 0, 0) < 0) goto done;
    if (SC(50, listener, 1, 0, 0, 0) < 0) goto done;
    do { client = SC(43, listener, 0, 0, 0, 0); } while (client == -4);
    if (client < 0) goto done;
    for (;;) {
        long count = SC(0, client, buffer, sizeof(buffer), 0, 0);
        if (count == -4) continue;
        if (count < 0) goto done;
        if (!count) { result = 0; break; }
        for (long sent = 0; sent < count;) {
            long n = SC(44, client, buffer + sent, count - sent, 0x4000, 0);
            if (n == -4) continue;
            if (n <= 0) goto done;
            sent += n;
        }
    }
done:
    if (client >= 0) SC(3, client, 0, 0, 0, 0);
    if (listener >= 0) SC(3, listener, 0, 0, 0, 0);
    return result;
}

__asm__(".section .text.entry,\"ax\",@progbits\n"
        ".global echo_lab_entry\n.hidden echo_lab_entry\n"
        ".type echo_lab_entry,@function\necho_lab_entry:\n"
        "endbr64\nmov %rsp,%rdi\nand $-16,%rsp\n"
        "call echo_lab_run\nmov %eax,%edi\nmov $231,%eax\nsyscall\nhlt\n"
        ".size echo_lab_entry,.-echo_lab_entry\n.previous\n");
