/* Freestanding Linux x86-64 TCP echo service, with intentionally neutral symbols. */
__attribute__((noinline)) long unused_1(long n,long a,long b,long c,long d,long e,long f) {
    register long r10 __asm__("r10")=d;
    register long r8 __asm__("r8")=e;
    register long r9 __asm__("r9")=f;
    long result;
    __asm__ volatile("syscall" : "=a"(result) : "a"(n),"D"(a),"S"(b),"d"(c),"r"(r10),"r"(r8),"r"(r9) : "rcx","r11","memory");
    return result;
}
#define SC(n,a,b,c,d,e,f) unused_1(n,(long)(a),(long)(b),(long)(c),(long)(d),(long)(e),(long)(f))
__attribute__((noinline)) void unused_2(const char *s) {
    long n=0; while(s[n]) ++n;
    SC(1,2,s,n,0,0,0);
}
__attribute__((noinline)) int unused_3(long argc,char **argv) {
    unsigned port=18080;
    if(argc>2) return 0;
    if(argc==2) {
        port=0;
        if(!argv[1][0]) return 0;
        for(char *s=argv[1];*s;++s) {
            if(*s<'0'||*s>'9') return 0;
            port=port*10+(*s-'0');
            if(port>65535) return 0;
        }
    }
    return port;
}
/* Every state performs one operation and returns the next jump-table index.
 * All mutable state lives on the caller's stack; the table is read-only. */
struct context {
    long listener, client, count, sent;
    int port, result;
    unsigned char address[16];
    char buffer[4096];
};
enum { CREATE, OPTIONS, BIND, LISTEN, ACCEPT, RECEIVE, SEND, CLOSE, CLEANUP, FAIL, STOP };
#define STEP __attribute__((noinline, noclone, used))
STEP unsigned unused_6(struct context *c) {
    c->listener=SC(41,2,1,0,0,0,0);
    if(c->listener<0) { unused_2("socket failed\n"); return FAIL; }
    return OPTIONS;
}
STEP unsigned unused_7(struct context *c) {
    int yes=1;
    SC(54,c->listener,1,2,&yes,4,0);
    return BIND;
}
STEP unsigned unused_8(struct context *c) {
    if(SC(49,c->listener,c->address,16,0,0,0)<0) {
        unused_2("bind/listen failed\n"); return CLEANUP;
    }
    return LISTEN;
}
STEP unsigned unused_9(struct context *c) {
    if(SC(50,c->listener,16,0,0,0,0)<0) {
        unused_2("bind/listen failed\n"); return CLEANUP;
    }
    return ACCEPT;
}
STEP unsigned unused_10(struct context *c) {
    c->client=SC(43,c->listener,0,0,0,0,0);
    if(c->client==-4) return ACCEPT;
    if(c->client<0) { unused_2("accept failed\n"); return CLEANUP; }
    return RECEIVE;
}
STEP unsigned unused_11(struct context *c) {
    c->count=SC(0,c->client,c->buffer,sizeof(c->buffer),0,0,0);
    if(c->count==-4) return RECEIVE;
    if(c->count<=0) return CLOSE;
    c->sent=0;
    return SEND;
}
STEP unsigned unused_12(struct context *c) {
    long n=SC(44,c->client,c->buffer+c->sent,c->count-c->sent,0x4000,0,0);
    if(n==-4) return SEND;
    if(n<=0) return CLOSE;
    c->sent+=n;
    return c->sent<c->count ? SEND : RECEIVE;
}
STEP unsigned unused_13(struct context *c) {
    SC(3,c->client,0,0,0,0,0);
    return ACCEPT;
}
STEP unsigned unused_14(struct context *c) {
    SC(3,c->listener,0,0,0,0,0);
    return FAIL;
}
STEP unsigned unused_15(struct context *c) {
    c->result=1;
    return STOP;
}
typedef unsigned (*step)(struct context *);
step const unused_16[] __attribute__((used)) = {
    unused_6, unused_7, unused_8, unused_9, unused_10,
    unused_11, unused_12, unused_13, unused_14, unused_15
};
unsigned unused_5(struct context *, unsigned);
/* Tail jump preserves the dispatcher's return address and stack alignment.
 * Keep the actual indirect jump explicit, independent of compiler heuristics. */
__asm__(".global unused_5\n.type unused_5,@function\nunused_5:\n"
        "cmp $9,%esi\nja 1f\nmov %esi,%esi\njmp *unused_16(,%rsi,8)\n"
        "1: mov $10,%eax\nret\n.size unused_5,.-unused_5\n");
STEP int unused_4(int argc,char **argv) {
    int port=unused_3(argc,argv);
    if(!port) { unused_2("usage: jq [port:1-65535]\n"); return 2; }
    struct context c={.listener=-1, .client=-1, .port=port,
        .address={2,0,(unsigned char)(port>>8),(unsigned char)port,127,0,0,1}};
    unsigned state=CREATE;
    while(state<STOP) state=unused_5(&c,state);
    return c.result;
}
/* Entered from the original jq main's call at 0x401f81. The caller
 * saved argv at rsp+0 and argc at rsp+0x10 before pushing a return address.
 * This adapter is deliberately specific to the pinned input binary. */
__asm__(".global unused_0\n.type unused_0,@function\nunused_0:\n"
        "endbr64\nmov 0x18(%rsp),%edi\nmov 8(%rsp),%rsi\nsub $8,%rsp\n"
        "call unused_4\nmov %eax,%edi\nmov $60,%eax\nsyscall\nhlt\n"
        ".size unused_0,.-unused_0\n");
