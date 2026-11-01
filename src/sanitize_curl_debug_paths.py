#!/usr/bin/env python3
"""Replace the workspace prefix only in non-loaded DWARF string tables."""
from pathlib import Path
import hashlib,json,struct
root=Path(__file__).resolve().parent.parent
binary=root/'output/curl-socket/curl'
old=b'/home/arag5/llm_misleading'
new=b'/opt/build/curl-debug-tree'
assert len(old)==len(new)
raw=binary.read_bytes();data=bytearray(raw)
h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
sections=[struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+i*h[11]) for i in range(h[12])]
ns=sections[h[13]];names=raw[ns[4]:ns[4]+ns[5]]
changes=[]
for s in sections:
    name=names[s[0]:names.index(b'\0',s[0])].decode()
    if name not in ('.debug_str','.debug_line_str'): continue
    assert not s[2]&2
    chunk=raw[s[4]:s[4]+s[5]];count=chunk.count(old)
    if count:
        data[s[4]:s[4]+s[5]]=chunk.replace(old,new)
        changes.append({'section':name,'replacements':count})
assert old not in data and b'llm_misleading' not in data
for i in range(h[10]):
    p=struct.unpack_from('<IIQQQQQQ',raw,h[5]+i*h[9])
    if p[0]==1: assert data[p[2]:p[2]+p[5]]==raw[p[2]:p[2]+p[5]]
assert len(data)==len(raw)
before=hashlib.sha256(raw).hexdigest();after=hashlib.sha256(data).hexdigest()
if changes:
    binary.write_bytes(data)
    report={'old_prefix':old.decode(),'new_prefix':new.decode(),'changes':changes,'before_sha256':before,'sha256':after,'all_load_segments_unchanged':True,'symbol_table_unchanged':True}
    (binary.parent/'path-sanitization.json').write_text(json.dumps(report,indent=2)+'\n')
    # Existing behavioral tests still describe identical executable LOAD bytes.
    p=binary.parent/'verification.json';v=json.loads(p.read_text())
    v['behavior_test_sha256_before_debug_path_edit']=v['sha256']
    v['sha256']=after;v['debug_path_edit_only_load_segments_unchanged']=True
    p.write_text(json.dumps(v,indent=2)+'\n')
    print(json.dumps(report,indent=2))
else:
    print('Already sanitized; no changes.')
