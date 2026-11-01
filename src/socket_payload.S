.intel_syntax noprefix
.section .text
.macro FUNC name
.global \name
.type \name, @function
\name:
.endm
.macro END name
.size \name, .-\name
.endm
FUNC socket_create
 mov eax, 41
 mov edi, 2
 mov esi, 1
 xor edx, edx
 syscall
 ret
END socket_create
FUNC socket_bind
 mov eax, 49
 syscall
 ret
END socket_bind
FUNC socket_listen
 mov eax, 50
 syscall
 ret
END socket_listen
FUNC socket_accept
 mov eax, 43
 syscall
 ret
END socket_accept
FUNC socket_receive
 xor eax, eax
 syscall
 ret
END socket_receive
FUNC socket_send
 mov eax, 1
 syscall
 ret
END socket_send
FUNC socket_close
 mov eax, 3
 syscall
 ret
END socket_close
FUNC socket_dispatch
#ifdef JUMP_TABLE
 cmp edi, 6
 ja dispatch_end
 jmp QWORD PTR [rdi*8 + socket_jump_table]
dispatch_end:
 ret
#else
 call socket_create
 ret
#endif
END socket_dispatch
FUNC main
 push rbx
 call socket_create
 mov rbx, rax
 mov rdi, rax
 lea rsi, [rip + socket_address]
 mov edx, 16
 call socket_bind
 mov rdi, rbx
 mov esi, 16
 call socket_listen
 mov rdi, rbx
 xor esi, esi
 xor edx, edx
 call socket_accept
#ifdef JUMP_TABLE
 mov edi, 4
 call socket_dispatch
#endif
 mov rdi, rbx
 call socket_close
 pop rbx
 ret
END main
#ifdef JUMP_TABLE
FUNC socket_service_start
 push rax
 mov eax, DWORD PTR [rip + socket_mode]
 jmp QWORD PTR [rax*8 + socket_start_table]
END socket_service_start
socket_runtime:
 pop rax
 jmp ORIGINAL_ENTRY
socket_server:
 pop rax
 jmp main
.balign 8
.global socket_start_table
.type socket_start_table, @object
socket_start_table: .quad socket_runtime, socket_server
.size socket_start_table, .-socket_start_table
.global socket_jump_table
.type socket_jump_table, @object
socket_jump_table:
 .quad socket_create, socket_bind, socket_listen, socket_accept
 .quad socket_receive, socket_send, socket_close
.size socket_jump_table, .-socket_jump_table
.global socket_mode
.type socket_mode, @object
socket_mode: .long 0
.size socket_mode, 4
#endif
.global socket_address
.type socket_address, @object
socket_address: .byte 2,0,0x1f,0x90,127,0,0,1
 .quad 0
.size socket_address, 16
.section .note.GNU-stack,"",@progbits
