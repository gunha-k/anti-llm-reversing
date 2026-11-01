#!/usr/bin/env python3
import hashlib,json,pathlib,socket,subprocess,time,struct,re
root=pathlib.Path(__file__).resolve().parent.parent
binary=root/'output/socket-mode/binary'
raw=(root/'programs/jq').read_bytes();blob=binary.read_bytes()
patch_offset=0x7134
assert blob[64:patch_offset]==raw[64:patch_offset]
assert blob[patch_offset+5:len(raw)]==raw[patch_offset+5:]
assert blob[0x1f00:0x1f00+6985]==raw[0x1f00:0x1f00+6985]
assert struct.unpack_from('<Q',blob,24)[0]==struct.unpack_from('<Q',raw,24)[0]
assert blob[patch_offset]==0xe9
# Final binary has only main; use the intermediate ELF to locate anonymous code.
symbols={}
for line in subprocess.check_output(['readelf','-sW',str(binary)],text=True).splitlines():
    m=re.match(r'\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+(FUNC|OBJECT)\s+GLOBAL\s+DEFAULT\s+\d+\s+(unused_\d+|main)',line)
    if m: symbols[m[4]]=(int(m[1],16),int(m[2]),m[3])
assert symbols=={'main':(0x401f00,6985,'FUNC')}
assert b'unused_' not in blob
for line in subprocess.check_output(['readelf','-sW',str(root/'build/unused_socket.elf')],text=True).splitlines():
    m=re.match(r'\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+(FUNC|OBJECT)\s+GLOBAL\s+DEFAULT\s+\d+\s+(unused_\d+)',line)
    if m: symbols[m[4]]=(int(m[1],16),int(m[2]),m[3])
def disassemble_range(name):
    address,size,_=symbols[name]
    return subprocess.check_output(['objdump','-d',f'--start-address={address}',f'--stop-address={address+size}',str(binary)],text=True)

main_dis=subprocess.check_output(['objdump','-d','--disassemble=main',str(binary)],text=True)
assert re.search(r'401f81:.*call\s+407130',main_dis)
assert patch_offset+5+0x400000+struct.unpack_from('<i',blob,patch_offset+1)[0]==symbols['unused_0'][0]
worker_dis=disassemble_range('unused_4')
assert re.search(r'call\s+'+format(symbols['unused_5'][0],'x')+r'\b',worker_dis)
h=struct.unpack_from('<16sHHIQQQIHHHHHH',blob)
loads=[struct.unpack_from('<IIQQQQQQ',blob,h[5]+i*h[9]) for i in range(h[10])]
table,size,kind=symbols['unused_16']
assert kind=='OBJECT' and size==80
segment=next(p for p in loads if p[0]==1 and p[3]<=table and table+size<=p[3]+p[5])
payload=(root/'build/unused_socket.bin').read_bytes()
assert blob[segment[2]:segment[2]+len(payload)]==payload
addresses=struct.unpack_from('<10Q',blob,segment[2]+table-segment[3])
assert addresses==tuple(symbols[f'unused_{i}'][0] for i in range(6,16))
assert len(set(addresses))==10
assert all(symbols[f'unused_{i}'][2]=='FUNC' for i in range(6,16))
dis=disassemble_range('unused_5')
assert re.search(r'jmp\s+\*',dis)

for args in [['0'],['65536'],['abc'],['1','2']]:
    p=subprocess.run([str(binary),*args],capture_output=True,timeout=3)
    assert p.returncode==2 and b'usage: jq' in p.stderr
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
p=subprocess.Popen([str(binary),str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
checks=[]
try:
    deadline=time.monotonic()+3
    while True:
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.2): pass
            break
        except OSError:
            if p.poll() is not None: raise AssertionError(p.communicate())
            if time.monotonic()>deadline: raise
            time.sleep(.02)
    for payload in [b'hello socket\n', '{"메시지":"echo"}\n'.encode(), bytes(range(256))*512]:
        with socket.create_connection(('127.0.0.1',port),timeout=3) as c:
            c.sendall(payload);c.shutdown(socket.SHUT_WR)
            received=bytearray()
            while True:
                chunk=c.recv(65536)
                if not chunk: break
                received.extend(chunk)
            assert received==payload
            checks.append({'echo_bytes':len(payload),'passed':True})
    # A second instance must report the bind error rather than silently continue.
    duplicate=subprocess.run([str(binary),str(port)],capture_output=True,timeout=3)
    assert duplicate.returncode==1 and b'bind/listen failed' in duplicate.stderr
    assert p.poll() is None
finally:
    p.terminate()
    try: p.communicate(timeout=3)
    except subprocess.TimeoutExpired: p.kill();p.communicate()
report={'original_content_preserved_except_header_and_callee_patch':True,'original_main_bytes_identical':6985,'jump_table_function_targets_verified':10,'only_main_symbol_retained':True,'indirect_jump_verified':True,'original_main_calls_patched_callee':True,'invalid_port_cases_passed':4,'echo_cases':checks,'duplicate_bind_error_passed':True,'server_stopped_after_test':True,'sha256':hashlib.sha256(blob).hexdigest()}
(root/'output/socket-mode/verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
