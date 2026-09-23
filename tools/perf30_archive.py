"""Read/replace GNU ar members without ambiguous duplicate-name replacement."""
import hashlib
def digest(data):return hashlib.sha256(data).hexdigest()
def records(raw):
    assert raw[:8]==b'!<arch>\n';offset=8;longnames=b'';out=[]
    while offset<len(raw):
        h=raw[offset:offset+60];assert len(h)==60 and h[58:60]==b'`\n'
        size=int(h[48:58]);data=raw[offset+60:offset+60+size];assert len(data)==size
        rawname=h[:16].decode().strip();name=rawname
        if rawname=='//':longnames=data
        elif rawname.startswith('/') and rawname not in ('/','/SYM64/'):
            start=int(rawname[1:]);name=longnames[start:longnames.index(b'/\n',start)].decode()
        else:name=name.rstrip('/')
        out.append({'header':h,'data':data,'rawname':rawname,'name':name})
        offset+=60+size+(size%2)
    assert offset==len(raw);return out
def members(raw):
    return [(r['name'],digest(r['data'])) for r in records(raw) if r['rawname'] not in ('/','/SYM64/','//')]
def replace(raw,replacements):
    result=bytearray(b'!<arch>\n');counts={key:0 for key in replacements}
    for r in records(raw):
        if r['rawname'] in ('/','/SYM64/'):continue # rebuilt by ranlib
        key=(r['name'],digest(r['data']));data=replacements.get(key,r['data'])
        if key in replacements:counts[key]+=1
        h=r['header'];h=h[:48]+str(len(data)).encode().ljust(10,b' ')+h[58:]
        result.extend(h);result.extend(data)
        if len(data)%2:result.extend(b'\n')
    assert all(counts.values()),counts
    return bytes(result),counts
