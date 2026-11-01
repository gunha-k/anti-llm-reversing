/* A standalone C program, also usable as input to curl_main_hook.py. */
#include <errno.h>
#include <netinet/in.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    const char *text = getenv("HOOK_ECHO_PORT");
    unsigned port = 18080;
    int listener = -1, client = -1, yes = 1, result = 1;
    char buffer[4096];
    (void)argc;
    (void)argv;
    if (text) {
        port = 0;
        if (!*text) return 1;
        for (; *text; ++text) {
            if (*text < '0' || *text > '9') return 1;
            port = port * 10 + (unsigned)(*text - '0');
            if (port > 65535) return 1;
        }
        if (!port) return 1;
    }
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons((unsigned short)port);
    listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) goto done;
    if (setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes))) goto done;
    if (bind(listener, (struct sockaddr *)&address, sizeof(address))) goto done;
    if (listen(listener, 1)) goto done;
    do { client = accept(listener, NULL, NULL); } while (client < 0 && errno == EINTR);
    if (client < 0) goto done;
    for (;;) {
        ssize_t count = recv(client, buffer, sizeof(buffer), 0);
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) goto done;
        if (!count) { result = 0; break; }
        for (ssize_t sent = 0; sent < count;) {
            ssize_t n = send(client, buffer + sent, (size_t)(count - sent), MSG_NOSIGNAL);
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) goto done;
            sent += n;
        }
    }
done:
    if (client >= 0) close(client);
    if (listener >= 0) close(listener);
    return result;
}
