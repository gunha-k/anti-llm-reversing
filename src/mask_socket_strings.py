#!/usr/bin/env python3
"""Replace jq identifiers in .rodata in place; preserve all offsets and code."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
source = ROOT / 'output/socket-router'
target = ROOT / 'output/socket-gateway'
raw = source.read_bytes()
data = bytearray(raw)
h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6]+i*h[11]) for i in range(h[12])]
s = sections[h[13]]
names = raw[s[4]:s[4]+s[5]]
def section_name(s):
    return names[s[0]:names.index(b'\0',s[0])].decode()
# Each replacement has the same byte length. No terminators, pointers or format
# specifiers are moved. "nc" is the network-tool disguise, "sv" socket values.
rules = [
    (b'jqlang.org', b'socket.org'),
    (b'commandline JSON processor', b'commandline TCP/IP handler'),
    (b'jq', b'nc'), (b'JQ', b'NC'),
    (b'jv', b'sv'), (b'JV', b'SV'),
]
assert all(len(a)==len(b) for a,b in rules)
changes = []
for s in sections:
    if section_name(s) != '.rodata':
        continue
    start, size = s[4], s[5]
    for match in re.finditer(rb'[\x09\x0a\x0d\x20-\x7e]{2,}', raw[start:start+size]):
        old = match.group()
        new = old
        for a,b in rules:
            new = new.replace(a,b)
        if old != new:
            offset = start + match.start()
            data[offset:offset+len(old)] = new
            changes.append({'offset':hex(offset), 'before':old.decode(), 'after':new.decode()})
assert len(data)==len(raw)
for s in sections:
    if section_name(s) != '.rodata':
        if s[1] != 8:
            assert data[s[4]:s[4]+s[5]] == raw[s[4]:s[4]+s[5]]
assert data[:64] == raw[:64]
assert data[h[5]:h[5]+h[9]*h[10]] == raw[h[5]:h[5]+h[9]*h[10]]
assert data[h[6]:h[6]+h[11]*h[12]] == raw[h[6]:h[6]+h[11]*h[12]]
target.write_bytes(data)
target.chmod(0o755)
# Reuse the established behavior cases without executing the other verifier.
module = ast.parse((ROOT/'src/verify.py').read_text())
# cases includes an .encode() expression, so compile only that trusted assignment.
assignment = next(n for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cases' for t in n.targets))
namespace = {}
exec(compile(ast.Module(body=[assignment],type_ignores=[]), 'verify-cases', 'exec'), namespace)
cases = namespace['cases']
def invoke(path,args,stdin,env=None):
    p = subprocess.run([str(path),*args],input=stdin,capture_output=True,timeout=10,env=env)
    return p.returncode,p.stdout,p.stderr
# Only these user-facing outputs are expected to change; user input/filter text
# echoed in diagnostics must retain its original spelling.
def expected_output(args, original):
    if args == ['--help']:
        for a,b in rules: original=original.replace(a,b)
    elif args == ['--version']:
        original=original.replace(b'jq-',b'nc-')
    else:
        original=original.replace(b'jq:',b'nc:')
    return original
for args,stdin in cases:
    rc,out,err=invoke(source,args,stdin)
    actual=invoke(target,args,stdin)
    assert actual==(rc,expected_output(args,out),expected_output(args,err)),(args,actual,(rc,out,err))
# Strings supplied by the user are not subject to the static replacement.
args=['-n','{"jq":"jq", "jv":"jv", "JQ_COLORS":"JQ_COLORS"}']
assert invoke(source,args,b'')==invoke(target,args,b'')
# The renamed configuration environment variable is intentional and works.
env=dict(os.environ)
for key in ['JQ_COLORS','NC_COLORS']: env.pop(key,None)
old_env=dict(env,JQ_COLORS='1;31:1;32:1;33:1;34:1;35:1;36:1;37')
new_env=dict(env,NC_COLORS=old_env['JQ_COLORS'])
assert invoke(source,['-C','.'],b'{"a":1}',old_env)==invoke(target,['-C','.'],b'{"a":1}',new_env)
report = {
    'source':source.name,'output':target.name,
    'source_sha256':hashlib.sha256(raw).hexdigest(),
    'output_sha256':hashlib.sha256(data).hexdigest(),
    'changed_string_runs':len(changes),
    'changed_bytes':sum(a!=b for a,b in zip(raw,data)),
    'behavior_cases_passed':len(cases)+2,
    'code_and_elf_layout_unchanged':True,
    'compatibility_changes':['help/version/error text','JQ_* environment names become NC_*','jq module paths become nc module paths'],
    'changes':changes,
}
(ROOT/'output/socket-gateway-strings.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='changes'},indent=2))
