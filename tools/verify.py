#!/usr/bin/env python3
import pathlib, subprocess, struct, json, hashlib, re
root=pathlib.Path(__file__).resolve().parent.parent
cases=[(['--version'],b''),(['--help'],b''),(['.'],b'{"a":[1,true,null,"hello"]}'),(['-c','.items | map(. * 2)'],b'{"items":[1,2,3]}'),(['-n','[range(100)] | add'],b''),(['-r','.name'], '{"name":"안녕하세요"}'.encode()),(['-s','add'],b'1\n2\n3\n'),(['-R','split(",")'],b'a,b,c\n'),(['--arg','x','value','-n','$x'],b''),(['--argjson','x','{"k":2}','-n','$x.k'],b''),(['-e','.'],b'false'),(['-e','.'],b'null'),(['-e','.'],b'true'),(['.'],b'{invalid'),(['this is invalid jq'],b'{}'),(['-n','error("expected")'],b''),(['--stream','-c','.'],b'{"a":[1,2]}'),(['-n','[range(10000)] | map(select(. % 3 == 0)) | length'],b''),(['-n','"abc123" | capture("(?<n>[0-9]+)")'],b''),(['-S','.'],b'{"z":1,"a":2}'),(['-n','reduce range(10) as $i (0; . + $i)'],b'')]
def invoke(path,args,stdin):
    p=subprocess.run([str(path),*args],input=stdin,capture_output=True,timeout=10)
    return p.returncode,p.stdout,p.stderr
raw=(root/'programs/jq').read_bytes()
h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
ph=[struct.unpack_from('<IIQQQQQQ',raw,h[5]+i*56) for i in range(h[10])]
results=[]
for name in ['socket-client','socket-server','socket-router']:
    binary=root/'output'/name
    for args,stdin in cases:
        expected=invoke(root/'programs/jq',args,stdin); actual=invoke(binary,args,stdin)
        assert actual==expected,(name,args,expected,actual)
    blob=binary.read_bytes()
    # ELF header changes intentionally; every other original loadable byte is identical.
    for p in ph:
        if p[0]==1:
            start=max(p[2],64); end=p[2]+p[5]
            assert blob[start:end]==raw[start:end],(name,'original LOAD altered')
    syms=subprocess.check_output(['readelf','-sW',str(binary)],text=True)
    entries=[]
    for line in syms.splitlines():
        m=re.match(r'\s*\d+:\s+([0-9a-f]+)\s+\d+\s+(?:FUNC|OBJECT)\s+GLOBAL\s+DEFAULT\s+\d+\s+(\S+)',line)
        if m: entries.append((int(m[1],16),m[2]))
    socket=[a for a,n in entries if n=='main' or n.startswith('socket_')]
    unused=[a for a,n in entries if n.startswith('unused_')]
    assert socket and unused and max(socket)<min(unused),(name,'address order')
    assert all(n=='main' or n.startswith(('socket_','unused_')) for a,n in entries)
    seen_unused=False
    for a,n in entries:
        if n.startswith('unused_'): seen_unused=True
        else: assert not seen_unused,(name,'symbol table order')
    for flags in [[],['-n']]:
        listed=subprocess.check_output(['nm',*flags,str(binary)],text=True).splitlines()
        symbol_names=[line.split()[-1] for line in listed]
        first_unused=next(i for i,n in enumerate(symbol_names) if n.startswith('unused_'))
        assert all(n.startswith('unused_') for n in symbol_names[first_unused:])
    if name!='socket-client':
        assert 'unused_1' in syms and ' main\n' in syms and 'socket_create' in syms
        full_dis=subprocess.check_output(['objdump','-d',str(binary)],text=True)
        assert re.search(r'Disassembly of section (\S+):',full_dis)[1]=='.text.socket'
        dis=subprocess.check_output(['objdump','-d','-j','.text.socket',str(binary)],text=True)
        if name=='socket-router':
            assert 'socket_start_table' in syms and 'socket_jump_table' in syms
            assert dis.count('jmp    *')>=2,dis
    results.append({'file':name,'behavior_cases_passed':len(cases),'socket_first_in_symbol_and_address_order':True,'original_load_bytes_preserved_except_elf_header':True})
manifest=json.loads((root/'output/manifest.json').read_text())
assert hashlib.sha256(raw).hexdigest()==manifest['input_sha256']
(root/'output/verification.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
