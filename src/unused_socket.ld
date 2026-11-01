ENTRY(unused_0)
PHDRS { payload PT_LOAD FLAGS(5); }
SECTIONS {
  . = 0x800000;
  .unused : { *(.text*) *(.rodata*) } :payload
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
