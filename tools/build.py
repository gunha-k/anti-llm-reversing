#!/usr/bin/env python3
"""Reproducible ELF64 surgery; input remains untouched. No external Python modules."""
import hashlib, json, pathlib, re, struct, subprocess
ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT/'build'; OUT = ROOT/'output'
BUILD.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
def run(*args):
    return subprocess.check_output([str(x) for x in args], text=True)
def align(n, a=4096): return (n+a-1)//a*a
raw = (ROOT/'programs/jq').read_bytes()
assert raw[:6] == b'\x7fELF\x02\x01'
h = list(struct.unpack_from('<16sHHIQQQIHHHHHH', raw))
assert h[1:3] == [2,62], 'requires static x86-64 ET_EXEC'
ph = [list(struct.unpack_from('<IIQQQQQQ', raw, h[5]+i*h[9])) for i in range(h[10])]
assert not any(p[0] == 3 for p in ph), 'dynamic interpreter unsupported'
sections = [list(struct.unpack_from('<IIQQQQIIQQ', raw, h[6]+i*h[11])) for i in range(h[12])]
assert not any(s[1] in (2,11) for s in sections), 'input must already be stripped'
oldstrings = sections[h[13]]
names = raw[oldstrings[4]:oldstrings[4]+oldstrings[5]]
def name_at(i): return names[i:names.index(b'\0',i)].decode()
sec_names = [name_at(s[0]) for s in sections]
functions = sorted(set((int(a,16),int(b,16)) for a,b in re.findall(r'FDE .*?pc=([0-9a-f]+)\.\.([0-9a-f]+)',run('readelf','--debug-dump=frames',ROOT/'programs/jq'))))
def section_at(addr):
    return next((i for i,s in enumerate(sections) if s[2]&2 and s[3]<=addr<s[3]+s[5]),0)
max_end = max(p[3]+p[6] for p in ph if p[0]==1)
base_bias = ph[0][3]-ph[0][2]
insert_offset = align(max(len(raw), max_end-base_bias))
base = min(p[3] for p in ph if p[0] == 1) - 4096
assert base >= 0x10000
report = {'input_sha256':hashlib.sha256(raw).hexdigest(),'recovered_function_ranges':len(functions),'variants':[]}
for variant, filename in [(1,'socket-client'),(2,'socket-server'),(3,'socket-router')]:
    data = bytearray(raw); hdr = h.copy(); sh = [s.copy() for s in sections]
    strings = bytearray(names); symbols = []
    def string(t, table):
        pos=len(table); table.extend(t.encode()+b'\0'); return pos
    def append(blob, alignment=8):
        data.extend(b'\0'*(align(len(data),alignment)-len(data)))
        off=len(data); data.extend(blob); return off
    def section(n,t,flags,addr,off,size,link=0,info=0,alignment=8,entsize=0):
        sh.append([string(n,strings),t,flags,addr,off,size,link,info,alignment,entsize]); return len(sh)-1
    socket_idx = None
    if variant >= 2:
        obj=BUILD/f'payload{variant}.o'; elf=BUILD/f'payload{variant}.elf'; binary=BUILD/f'payload{variant}.bin'
        run('gcc','-c','-x','assembler-with-cpp',f'-DORIGINAL_ENTRY={h[4]}',*(['-DJUMP_TABLE'] if variant==3 else []), ROOT/'tools/socket_payload.S','-o',obj)
        run('ld','-nostdlib',f'-Ttext={base:#x}','-e','main',obj,'-o',elf)
        run('objcopy','-O','binary','--only-section=.text',elf,binary)
        payload=binary.read_bytes()
        data.extend(b'\0'*(insert_offset-len(data))); data.extend(payload)
        idx=section('.text.socket',1,6,base,insert_offset,len(payload),alignment=16)
        socket_idx = idx
        for line in run('readelf','-sW',elf).splitlines():
            m=re.match(r'\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+(FUNC|OBJECT)\s+GLOBAL\s+DEFAULT\s+\d+\s+(\S+)',line)
            if m:
                addr,size,typ,n=m.groups(); symbols.append((n,int(addr,16),int(size),idx,2 if typ=='FUNC' else 1))
        if variant==3: hdr[4]=next(s[1] for s in symbols if s[0]=='socket_service_start')
        poff=align(len(data),8)
        phsize=(len(ph)+2)*56
        total=poff-insert_offset+phsize
        assert total <= 4096, 'socket segment must fit below original mappings'
        phaddr=base+poff-insert_offset
        pnew=[[6,4,poff,phaddr,phaddr,phsize,phsize,8],
              [1,5,insert_offset,base,base,total,total,4096]]
        pnew.extend(p.copy() for p in ph)
        append(b''.join(struct.pack('<IIQQQQQQ',*p) for p in pnew))
        hdr[5]=poff; hdr[10]=len(pnew)
    labels=['socket_connect','socket_poll','socket_read','socket_write','socket_shutdown','socket_resolve','socket_accept','socket_listen']
    for i,(a,b) in enumerate(functions,1):
        n=labels[i-1] if variant==1 and i<=len(labels) else f'unused_{i}'
        symbols.append((n,a,b-a,section_at(a),2))
    # Stripped input contains no variable boundaries: label data sections, not guessed variables.
    for i,s in enumerate(sections):
        if s[2]&2 and not s[2]&4 and s[1] in (1,8) and s[5]:
            symbols.append((f'unused_{len(symbols)+1}',s[3],s[5],i,1))
    # Put socket code first in section iteration, as well as in virtual address order.
    if socket_idx is not None:
        order=[0,socket_idx]+[i for i in range(1,len(sh)) if i!=socket_idx]
        mapping={old:new for new,old in enumerate(order)}
        sh=[sh[i] for i in order]
        for s in sh:
            s[6]=mapping[s[6]]
            if s[2]&0x40 or s[1] in (4,9): s[7]=mapping[s[7]]
        symbols=[(n,a,z,mapping[idx],t) for n,a,z,idx,t in symbols]
        hdr[13]=mapping[h[13]]
    # Ordinary nm sorts names; nm -n sorts addresses; readelf uses table order.
    symbols.sort(key=lambda s:(s[0].startswith('unused_'),s[1],s[0]))
    symstr=bytearray(b'\0'); symtab=bytearray(24)
    for n,a,size,idx,typ in symbols:
        symtab.extend(struct.pack('<IBBHQQ',string(n,symstr),0x10|typ,0,idx,a,size))
    si=section('.strtab',3,0,0,append(symstr),len(symstr),alignment=1)
    section('.symtab',2,0,0,append(symtab),len(symtab),link=si,info=1,entsize=24)
    sh[hdr[13]][4]=append(strings,1); sh[hdr[13]][5]=len(strings)
    hdr[6]=append(b''.join(struct.pack('<IIQQQQIIQQ',*s) for s in sh)); hdr[12]=len(sh)
    struct.pack_into('<16sHHIQQQIHHHHHH',data,0,*hdr)
    target=OUT/filename; target.write_bytes(data); target.chmod(0o755)
    report['variants'].append({'variant':variant,'file':filename,'entry':hex(hdr[4]),'symbols':len(symbols),'sha256':hashlib.sha256(data).hexdigest()})
(OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
