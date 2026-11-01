#!/usr/bin/env python3
import hashlib,json,os,pathlib,socket,subprocess,time
root=pathlib.Path(__file__).resolve().parent.parent
binary=root/'output/curl-socket/curl'
def environment(port): return dict(os.environ,CURL_SOCKET_PORT=str(port))
for port in ['0','65536','abc','']:
    p=subprocess.run([str(binary),'--version'],env=environment(port),capture_output=True,timeout=3)
    assert p.returncode==1 and not p.stdout
cases=[]
for payload in [b'hello socket\n','테스트\n'.encode(),bytes(range(256))*512]:
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    p=subprocess.Popen([str(binary),'--version'],env=environment(port),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+3
        while True:
            try:
                c=socket.create_connection(('127.0.0.1',port),timeout=3);break
            except ConnectionRefusedError:
                assert p.poll() is None
                if time.monotonic()>deadline: raise
                time.sleep(.02)
        with c:
            c.sendall(payload);c.shutdown(socket.SHUT_WR)
            received=bytearray()
            while True:
                part=c.recv(65536)
                if not part: break
                received.extend(part)
            assert received==payload
        stdout,stderr=p.communicate(timeout=3)
        assert p.returncode==0 and not stdout,(p.returncode,stdout,stderr)
        cases.append({'bytes':len(payload),'echo_matches':True,'exited_zero_after_eof':True,'curl_version_not_executed':True})
    finally:
        if p.poll() is None:p.kill();p.communicate()
with socket.socket() as occupied:
    occupied.bind(('127.0.0.1',0));occupied.listen(1)
    p=subprocess.run([str(binary)],env=environment(occupied.getsockname()[1]),capture_output=True,timeout=3)
    assert p.returncode==1
symbols=subprocess.check_output(['nm',str(binary)],text=True)
assert ' T tool_stderr_read_hook\n' in symbols and ' T main\n' in symbols
report={'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'invalid_port_cases':4,'bind_failure_exit':True,'echo_tests':cases}
(root/'output/curl-socket/verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
