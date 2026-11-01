#!/usr/bin/env python3
import hashlib,json,pathlib,struct,subprocess,re
root=pathlib.Path(__file__).resolve().parent.parent
build=root/'build'; out=root/'output/socket-mode'
build.mkdir(exist_ok=True);out.mkdir(exist_ok=True)
def run(*args): return subprocess.check_output([str(a) for a in args],text=True)
obj=build/'unused_socket.o'; elf=build/'unused_socket.elf'; binary=build/'unused_socket.bin'
run('gcc','-c','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pie','-fno-asynchronous-unwind-tables',root/'src/unused_socket.c','-o',obj)
run('ld','-nostdlib','-T',root/'src/unused_socket.ld',obj,'-o',elf)
run('objcopy','-O','binary','--only-section=.unused',elf,binary)
raw=(root/'jq').read_bytes(); data=bytearray(raw)
assert hashlib.sha256(raw).hexdigest() == 'b1c22172dd303f3be49e935aa56aa48a8b7a46e0bc838b4997d3bb451495870f', 'Hook stack offsets require the original jq build'
h=list(struct.unpack_from('<16sHHIQQQIHHHHHH',raw))
assert raw[:6]==b'\x7fELF\x02\x01' and h[1:3]==[2,62]
ph=[list(struct.unpack_from('<IIQQQQQQ',raw,h[5]+i*h[9])) for i in range(h[10])]
sh=[list(struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+i*h[11])) for i in range(h[12])]
assert not any(p[0]==3 for p in ph)
assert not any(s[1] in (2,11) for s in sh), 'This builder expects the provided stripped original.'
base=0x800000
assert max(p[3]+p[6] for p in ph if p[0]==1)<base
s=sh[h[13]]; names=bytearray(raw[s[4]:s[4]+s[5]])
def addstr(table,value):
    i=len(table);table.extend(value.encode()+b'\0');return i
def append(blob,alignment=8):
    data.extend(b'\0'*((-len(data))%alignment));i=len(data);data.extend(blob);return i
payload=binary.read_bytes();offset=append(payload,4096);idx=len(sh)
sh.append([addstr(names,'.text.unused'),1,6,base,offset,len(payload),0,0,16,0])
entries=[]
for line in run('readelf','-sW',elf).splitlines():
    m=re.match(r'\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+(FUNC|OBJECT)\s+GLOBAL\s+DEFAULT\s+\d+\s+(unused_\d+|main)',line)
    if m: entries.append((m[4],int(m[1],16),int(m[2]),2 if m[3]=="FUNC" else 1))
assert {n for n,a,z,t in entries} == {f"unused_{i}" for i in range(17)}
adapter=next(a for n,a,z,t in entries if n=='unused_0')
def file_offset(address):
    p=next(p for p in ph if p[0]==1 and p[3]<=address<p[3]+p[5])
    return p[2]+address-p[3]
main_address=0x401f00; main_size=6985
hook_address=0x407130
hook_offset=file_offset(hook_address)
assert raw[hook_offset:hook_offset+4]==bytes.fromhex('f30f1efa')
# Preserve ENDBR64; patch only the called function, never main or its call.
patch_offset=hook_offset+4
patch=b'\xe9'+struct.pack('<i',adapter-(hook_address+4+5))
data[patch_offset:patch_offset+5]=patch
entries.extend([('main',main_address,main_size,2),('unused_17',hook_address,9,2)])
# Retain original entry, so libc initializes TLS before the original main runs.

poff=(len(data)+7)//8*8;phsize=(len(ph)+2)*56;paddr=base+poff-offset
pnew=[[6,4,poff,paddr,paddr,phsize,phsize,8]]+ph+[[1,5,offset,base,base,poff-offset+phsize,poff-offset+phsize,4096]]
assert append(b''.join(struct.pack('<IIQQQQQQ',*p) for p in pnew))==poff
h[5]=poff;h[10]=len(pnew)
strings=bytearray(b'\0');symtab=bytearray(24)
for n,a,z,t in sorted(entries):
    if n.startswith('unused_'): continue
    symbol_section=next((i for i,s in enumerate(sh) if s[2]&2 and s[3]<=a<s[3]+s[5]),None)
    assert symbol_section is not None
    symtab.extend(struct.pack('<IBBHQQ',addstr(strings,n),0x10|t,0,symbol_section,a,z))
stridx=len(sh)
sh.append([addstr(names,'.strtab'),3,0,0,append(strings),len(strings),0,0,1,0])
sh.append([addstr(names,'.symtab'),2,0,0,append(symtab),len(symtab),stridx,1,8,24])
sh[h[13]][4]=append(names,1);sh[h[13]][5]=len(names)
h[6]=append(b''.join(struct.pack('<IIQQQQIIQQ',*s) for s in sh));h[12]=len(sh)
struct.pack_into('<16sHHIQQQIHHHHHH',data,0,*h)
assert data[64:patch_offset]==raw[64:patch_offset]
assert data[patch_offset+5:len(raw)]==raw[patch_offset+5:]
main_offset=file_offset(main_address)
assert data[main_offset:main_offset+main_size]==raw[main_offset:main_offset+main_size]
target=out/'binary';target.write_bytes(data);target.chmod(0o755)
report={'file':str(target.relative_to(root)),'source_sha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(data).hexdigest(),'entry':hex(h[4]),'payload_bytes':len(payload),'original_bytes_preserved_except_elf_header_and_5_byte_callee_patch':True,'main_address':hex(main_address),'main_size':main_size,'main_byte_identical':True,'hook_address':hex(hook_address),'patch_offset':patch_offset,'patch_size':5,'original_function_symbols_present':False,'added_symbols':['main'],'behavior':'TCP echo server, 127.0.0.1, default port 18080; optional port argument'}
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
