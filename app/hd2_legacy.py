from pathlib import Path
import struct,json

def lz4_block(data,expected):
    out=bytearray(); pos=0
    def length(initial):
        nonlocal pos
        n=initial
        if initial==15:
            while True:
                if pos>=len(data): raise ValueError('Truncated length')
                b=data[pos]; pos+=1; n+=b
                if b!=255: break
        return n
    while pos<len(data):
        token=data[pos]; pos+=1
        literals=length(token>>4)
        if pos+literals>len(data) or len(out)+literals>expected: raise ValueError('Bad literal range')
        out.extend(data[pos:pos+literals]);pos+=literals
        if pos==len(data): break
        if pos+2>len(data): raise ValueError('Truncated offset')
        offset=int.from_bytes(data[pos:pos+2],'little');pos+=2
        if not 0<offset<=len(out): raise ValueError('Invalid offset')
        count=length(token&15)+4
        if len(out)+count>expected: raise ValueError('Oversized match')
        pattern=out[-offset:]
        out.extend((pattern*((count+offset-1)//offset))[:count])
    if len(out)!=expected: raise ValueError('Wrong decoded size')
    return bytes(out)

def dsar(data):
    if data[:4]!=b'DSAR': raise ValueError('Not DSAR')
    count=struct.unpack_from('<I',data,8)[0]
    if 32+32*count>len(data): raise ValueError('Bad table')
    out=bytearray()
    for i in range(count):
        at=32+i*32
        uoff,coff,usize,csize,kind=struct.unpack_from('<QQIIB',data,at)
        if uoff!=len(out) or coff+csize>len(data): raise ValueError('Bad chunk range')
        block=data[coff:coff+csize]
        out.extend(lz4_block(block,usize) if kind==3 else block)
    return bytes(out)


import bisect, hashlib, re, uuid, argparse, zipfile
from datetime import datetime

SOURCE='d8cd425483086455'
TARGET='58e4bd4b2278d15c'
UNIT=0xe0a48d0be9a7453f
SOURCE_PARTS={'slim body':17025900687927008879,'stocky body':15506792001684480068,'slim left arm':10527733968595312226,'stocky left arm':10178501245460811057,'slim right arm':69876747235779132,'stocky right arm':8923945159529307492,'slim waist':7470288056812912186,'stocky waist':3306967223026041170,'left leg':7157602910548862458,'right leg':16970593047438816163}
TARGET_PARTS={'slim body':18025254480580733275,'stocky body':16534447055458057688,'slim left arm':2567690365343907235,'stocky left arm':17786515856343915068,'slim right arm':3467853974557819730,'stocky right arm':4262785967333127230,'slim waist':5315292825954710384,'stocky waist':11475355184270700671,'left leg':7066004653337270514,'right leg':14584676054580543486}
# Additional matches checked against customization labels and mesh group hashes.
EXTRA_PAIRS={1720314625163248514:4741415154744209210,5809497804576864603:3800685569620653850,14153784729321594614:3006284353944471300,14375882890344212790:2971673397720090427,9501191279192290192:8751633847476789976,11861961532059517982:11454252334967675991,12655331561606289602:77768752549360061,15211186993657817445:17866398670168798715,14466413169173209984:254349306793314548,5015099231978410986:1769949868322349152,7088624154722267692:3286754234729990316}
REMAP={SOURCE_PARTS[k]:v for k,v in TARGET_PARTS.items()}
REMAP.update(EXTRA_PAIRS)
PENDING_TARGET=3415621014299968645
UNMAPPED_SOURCE=9871997257301833681

class Bundles:
    def __init__(self,root):
        self.root=Path(root).resolve();self.headers={};self.cache={};self.packages={}
        index=self.root/'bundles.nxa'
        if not index.is_file():raise ValueError('未找到 bundles.nxa；此版仅支持带该索引的打包资源格式。')
        raw=index.read_bytes()
        if len(raw)>128*1024*1024:raise ValueError('索引过大，停止读取。')
        toc=dsar(raw)
        if len(toc)<24:raise ValueError('索引截断。')
        count=struct.unpack_from('<I',toc,16)[0]
        if 24+count*24>len(toc):raise ValueError('资源表越界。')
        for i in range(count):
            size,noff,n,eoff=struct.unpack_from('<QIII',toc,24+i*24)
            if noff>=len(toc) or eoff+n*16>len(toc):raise ValueError('资源索引越界。')
            end=toc.find(b'\0',noff)
            if end<0:raise ValueError('资源名无结束符。')
            name=toc[noff:end].decode('utf-8').replace(chr(92),'/').rsplit('/',1)[-1]
            entries=[]
            for j in range(n):
                at=eoff+j*16;logical,start=struct.unpack_from('<QI',toc,at)
                entries.append((logical,start,'bundles.%02d.nxa'%toc[at+15]))
            self.packages[name]=(size,sorted(entries))
    def read_range(self,name,start,size):
        path=self.root/name
        if name not in self.headers:
            with path.open('rb') as f:
                prefix=f.read(32)
                if prefix[:4]!=b'DSAR':raise ValueError('无效分卷：'+name)
                n=struct.unpack_from('<I',prefix,8)[0]
                if n>1000000:raise ValueError('分卷表过大。')
                table=f.read(32*n)
                if len(table)!=32*n:raise ValueError('分卷表截断。')
            desc=[struct.unpack_from('<QQIIBB',table,32*i) for i in range(n)]
            self.headers[name]=([d[0] for d in desc],desc)
        offsets,desc=self.headers[name];idx=bisect.bisect_right(offsets,start)-1
        if idx<0:raise ValueError('资源起始位置不在分卷中。')
        result=bytearray()
        with path.open('rb') as f:
            while size:
                if idx>=len(desc):raise ValueError('分卷资源截断。')
                uoff,coff,usize,csize,kind,_=desc[idx]
                if not uoff<=start<uoff+usize:raise ValueError('分卷存在间隙。')
                key=(name,idx)
                if key not in self.cache:
                    f.seek(coff);packed=f.read(csize)
                    if len(packed)!=csize:raise ValueError('压缩数据截断。')
                    if kind==3:block=lz4_block(packed,usize)
                    elif kind==0 and csize==usize:block=packed
                    else:raise ValueError('不支持的压缩格式：'+str(kind))
                    if len(self.cache)>128:self.cache.clear()
                    self.cache[key]=block
                count=min(size,uoff+usize-start)
                result.extend(self.cache[key][start-uoff:start-uoff+count])
                start+=count;size-=count;idx+=1
        return bytes(result)
    def load(self,name):
        if name not in self.packages:raise ValueError('索引中找不到资源：'+name)
        size,entries=self.packages[name]
        if size>256*1024*1024 or not entries or entries[0][0]!=0:raise ValueError('不支持的资源大小或索引。')
        result=bytearray(size)
        for i,(logical,start,bundle) in enumerate(entries):
            end=entries[i+1][0] if i+1<len(entries) else size
            if not logical<=end<=size:raise ValueError('资源索引顺序错误。')
            result[logical:end]=self.read_range(bundle,start,end-logical)
        return bytes(result)

def parse(toc,gpu=None,stream=None):
    if len(toc)<72 or struct.unpack_from('<I',toc)[0]!=0xf0000011:raise ValueError('不是支持的游戏档案。')
    nt,n=struct.unpack_from('<II',toc,4);start=72+nt*32;end=start+n*80
    if end>len(toc):raise ValueError('档案资源表越界。')
    entries=[]
    for i in range(n):
        at=start+i*80;e=struct.unpack_from('<QQQQQQQIIIIII',toc,at)
        fid,tid,toff,soff,goff=e[:5];ts,ss,gs=e[7:10]
        if toff+ts>len(toc) or (ts and toff<end):raise ValueError('模型数据越界。')
        if gpu is not None and gs and goff+gs>len(gpu):raise ValueError('GPU 数据越界。')
        if stream is not None and ss and soff+ss>len(stream):raise ValueError('贴图 stream 数据越界。')
        entries.append({'id':fid,'type':tid,'header':at,'offset':toff,'size':ts})
    if len({(e['id'],e['type']) for e in entries})!=n:raise ValueError('资源 ID 重复。')
    return entries

def labels(toc,e):
    blob=toc[e['offset']:e['offset']+e['size']]
    return {k.decode():v.decode() for k,v in re.findall(rb'HelldiverCustomization(BodyType|Slot|Weight|PieceType)_([A-Za-z0-9_]+)',blob)}

def check(root):
    b=Bundles(root)
    result={'data_directory':str(b.root),'catalog_packages':len(b.packages),'bundles':len(list(b.root.glob('bundles.[0-9][0-9].nxa'))),'source':{},'target':{}}
    for key,archive in [('source',SOURCE),('target',TARGET)]:
        for suffix in ('','.gpu_resources','.stream'):
            name=archive+suffix
            result[key][name]=b.packages[name][0] if name in b.packages else None
    if any(v is None for k in ('source','target') for v in result[k].values()):raise ValueError('未找到两件护甲的完整档案。')
    return b,result

def collision_scan(root,keys):
    collisions=[];unreadable=[]
    for path in Path(root).iterdir():
        if not re.fullmatch(r'[0-9a-fA-F]{16}\.patch_\d+',path.name):continue
        try:
            with path.open('rb') as f:
                h=f.read(72)
                if len(h)!=72 or struct.unpack_from('<I',h)[0]!=0xf0000011:raise ValueError('unsupported')
                nt,n=struct.unpack_from('<II',h,4)
                if nt>10000 or n>1000000:raise ValueError('oversized')
                f.seek(72+nt*32);table=f.read(n*80)
                if len(table)!=n*80:raise ValueError('truncated')
            overlap=[]
            for i in range(n):
                pair=struct.unpack_from('<QQ',table,i*80)
                if pair in keys:overlap.append(str(pair[0]))
            if overlap:collisions.append({'file':path.name,'overlapping_resources':len(overlap),'unit_ids':[x for x in overlap if (int(x),UNIT) in keys]})
        except (OSError,ValueError,struct.error):unreadable.append(path.name)
    return collisions,unreadable


TEXTURE = 0xcd4238c6a0c69e32
# Per-piece primary palette bindings, verified from Filediver armor-set metadata.
# Keys are B-01 palette IDs; values are PH-56 palette IDs.
COLOR_LUT_REMAP = {
    11590113946843745450: 15582037679626784816,
    17745773801767941727: 14647728085467686159,
    14392145978854826493: 3407076529290252504,
    16006472208516274850: 8089725939406680062,
    13779560771756172763: 4398586474736961156,
    8899838268388796601: 14000038807789650907,
}


# Verified against all four B-01 kit records and their original resource archives.
VARIANT_UNIT_ALIASES = {210741088782467259: 11861961532059517982,
 1297635014908290446: 15211186993657817445,
 2211582350184476547: 14153784729321594614,
 2552357895482913313: 5809497804576864603,
 2709058781394543389: 12655331561606289602,
 3415621014299968645: 14466413169173209984,
 4292276616635538038: 12655331561606289602,
 4661856320322270170: 15211186993657817445,
 5890354066914717422: 11861961532059517982,
 7535532618541176833: 15211186993657817445,
 9657078067338063946: 5809497804576864603,
 10884337435683456396: 14153784729321594614,
 12110429268135116022: 7088624154722267692,
 12395370135027842387: 14375882890344212790,
 12658265416151559544: 14375882890344212790,
 15089103303351293005: 1720314625163248514,
 15475421575454726038: 1720314625163248514,
 15635181247503290225: 5015099231978410986,
 15687564603842858068: 7088624154722267692,
 17388793511846232887: 9501191279192290192,
 18281779898182974174: 5015099231978410986}
VARIANT_EXPECTED_UNITS = {'519cc1ec2eb56e1d': [210741088782467259,
                      254349306793314548,
                      2211582350184476547,
                      2552357895482913313,
                      2567690365343907235,
                      3415621014299968645,
                      3467853974557819730,
                      4262785967333127230,
                      4292276616635538038,
                      5315292825954710384,
                      7066004653337270514,
                      7535532618541176833,
                      11475355184270700671,
                      12110429268135116022,
                      12395370135027842387,
                      14584676054580543486,
                      15475421575454726038,
                      15635181247503290225,
                      16534447055458057688,
                      17388793511846232887,
                      17786515856343915068,
                      18025254480580733275],
 '562a45e9bc984eb9': [254349306793314548,
                      1769949868322349152,
                      2567690365343907235,
                      2709058781394543389,
                      3286754234729990316,
                      3415621014299968645,
                      3467853974557819730,
                      3800685569620653850,
                      4262785967333127230,
                      4661856320322270170,
                      4741415154744209210,
                      5315292825954710384,
                      7066004653337270514,
                      8751633847476789976,
                      10884337435683456396,
                      11454252334967675991,
                      11475355184270700671,
                      12658265416151559544,
                      14584676054580543486,
                      16534447055458057688,
                      17786515856343915068,
                      18025254480580733275],
 '58e4bd4b2278d15c': [77768752549360061,
                      254349306793314548,
                      1769949868322349152,
                      2567690365343907235,
                      2971673397720090427,
                      3006284353944471300,
                      3286754234729990316,
                      3415621014299968645,
                      3467853974557819730,
                      3800685569620653850,
                      4262785967333127230,
                      4741415154744209210,
                      5315292825954710384,
                      7066004653337270514,
                      8751633847476789976,
                      11454252334967675991,
                      11475355184270700671,
                      14584676054580543486,
                      16534447055458057688,
                      17786515856343915068,
                      17866398670168798715,
                      18025254480580733275],
 '6cd3d55c05d4eac1': [77768752549360061,
                      254349306793314548,
                      1297635014908290446,
                      2567690365343907235,
                      2971673397720090427,
                      3006284353944471300,
                      3415621014299968645,
                      3467853974557819730,
                      4262785967333127230,
                      5315292825954710384,
                      5890354066914717422,
                      7066004653337270514,
                      8751633847476789976,
                      9657078067338063946,
                      11475355184270700671,
                      14584676054580543486,
                      15089103303351293005,
                      15687564603842858068,
                      16534447055458057688,
                      17786515856343915068,
                      18025254480580733275,
                      18281779898182974174]}

def add_variant_units(candidate, gpu, stream, source_toc, variant_tocs):
    # Each kit's exact Unit set is checked before adding shared PH-56 aliases.
    for archive, expected in VARIANT_EXPECTED_UNITS.items():
        toc = variant_tocs[archive]
        actual = {e['id'] for e in parse(toc) if e['type'] == UNIT}
        if actual != set(expected):
            raise ValueError('B-01 变体部件已变化：' + archive)
    source_units = {e['id']: e for e in parse(source_toc) if e['type'] == UNIT}
    for target_id, source_id in VARIANT_UNIT_ALIASES.items():
        se = source_units[source_id]
        source_labels = labels(source_toc, se)
        found = False
        for toc in variant_tocs.values():
            te = next((e for e in parse(toc) if e['type'] == UNIT and e['id'] == target_id), None)
            if te is None:
                continue
            found = True
            target_labels = labels(toc, te)
            # PH-56 intentionally shares one hip armor asset between both body types.
            if target_id == PENDING_TARGET:
                source_labels = {k: v for k, v in source_labels.items() if k != 'BodyType'}
                target_labels = {k: v for k, v in target_labels.items() if k != 'BodyType'}
            if source_labels != target_labels:
                raise ValueError('新增部件标签不一致：' + str(target_id))
        if not found:
            raise ValueError('缺少变体部件：' + str(target_id))
    entries = parse(candidate, gpu, stream)
    index = {(e['id'], e['type']): e for e in entries}
    nt, nf = struct.unpack_from('<II', candidate, 4)
    body_start = 72 + nt * 32 + nf * 80
    delta = len(VARIANT_UNIT_ALIASES) * 80
    groups = {}
    for e in entries:
        h = bytearray(candidate[e['header']:e['header']+80])
        struct.pack_into('<Q', h, 16, e['offset'] + delta)
        groups.setdefault(e['type'], []).append(h)
    payload = bytearray()
    proof = []
    for target_id, source_id in sorted(VARIANT_UNIT_ALIASES.items()):
        if (target_id, UNIT) in index:
            raise ValueError('新增部件 ID 已存在。')
        e = index[(REMAP[source_id], UNIT)]
        blob = candidate[e['offset']:e['offset']+e['size']]
        payload.extend(bytes((-(len(candidate)+delta+len(payload))) % 16))
        offset = len(candidate) + delta + len(payload)
        h = bytearray(candidate[e['header']:e['header']+80])
        struct.pack_into('<Q', h, 0, target_id)
        struct.pack_into('<Q', h, 16, offset)
        groups[UNIT].append(h)
        payload.extend(blob)
        proof.append({'target':str(target_id),'source':str(source_id),'payload_sha256':hashlib.sha256(blob).hexdigest()})
    head = bytearray(candidate[:72])
    struct.pack_into('<I', head, 8, nf + len(proof))
    type_headers = bytearray()
    ordered = []
    for i in range(nt):
        h = bytearray(candidate[72+i*32:104+i*32])
        tid = struct.unpack_from('<Q', h, 8)[0]
        struct.pack_into('<Q', h, 16, len(groups[tid]))
        type_headers.extend(h)
        ordered.extend(groups[tid])
    for i, h in enumerate(ordered, 1):
        struct.pack_into('<I', h, 76, i)
    result = bytes(head + type_headers + b''.join(ordered) + candidate[body_start:] + payload)
    actual = {e['id'] for e in parse(result, gpu, stream) if e['type'] == UNIT}
    if not set().union(*map(set, VARIANT_EXPECTED_UNITS.values())) <= actual:
        raise ValueError('四个 B-01 变体的覆盖校验失败。')
    return result, proof


def recolor_yellow_trim(pixels, source_id):
    # Only the base-color RGB of three confirmed yellow material rows is edited.
    # All material parameters, alpha, other rows and stored mip data are preserved.
    rows = {4398586474736961156: (1, 7), 14000038807789650907: (1,)}.get(source_id, ())
    result = bytearray(pixels)
    proof = []
    for row in rows:
        offset = row * 23 * 8
        rgba = struct.unpack_from('<4e', result, offset)
        if rgba[:3] != (0.66796875, 0.625, 0.1953125):
            raise ValueError('黄色饰边的色值已变化，停止使用旧修改方案。')
        olive = (0.26953125, 0.296875, 0.25390625)
        struct.pack_into('<3e', result, offset, *olive)
        proof.append({'row':row,'column':0,'before_rgb':list(rgba[:3]),'after_rgb':list(olive)})
    return bytes(result), proof


def add_camo_palettes(candidate, source_gpu, source_stream, target_toc, *, remove_yellow=True):
    entries = parse(candidate, source_gpu, source_stream)
    source_index = {(e['id'], e['type']): e for e in entries}
    target_index = {(e['id'], e['type']): e for e in parse(target_toc)}
    nt, nf = struct.unpack_from('<II', candidate, 4)
    old_body_start = 72 + nt * 32 + nf * 80
    extra_count = len(COLOR_LUT_REMAP)
    delta = extra_count * 80
    gpu = bytearray(source_gpu)
    additions = bytearray()
    extra_headers = []
    proof = []
    for target_id, source_id in COLOR_LUT_REMAP.items():
        src = source_index.get((source_id, TEXTURE))
        tgt = target_index.get((target_id, TEXTURE))
        if src is None or tgt is None:
            raise ValueError('主颜色表缺失，停止生成迷彩模式。')
        if (target_id, TEXTURE) in source_index:
            raise ValueError('目标颜色表已经存在，不能重复写入。')
        header = bytearray(candidate[src['header']:src['header']+80])
        blob = bytes(candidate[src['offset']:src['offset']+src['size']])
        target_blob = target_toc[tgt['offset']:tgt['offset']+tgt['size']]
        for body in (blob, target_blob):
            if len(body) != 340 or body[192:196] != b'DDS ':
                raise ValueError('颜色表的 DDS 结构已变化。')
            height, width = struct.unpack_from('<II', body, 204)
            fmt = struct.unpack_from('<I', body, 320)[0]
            if (width, height, fmt) != (23, 8, 10):
                raise ValueError('颜色表尺寸或格式已变化。')
        old_gpu_offset = struct.unpack_from('<Q', header, 32)[0]
        stream_size, gpu_size = struct.unpack_from('<II', header, 60)
        if stream_size != 0 or gpu_size != 1928:
            raise ValueError('颜色表的配套数据格式已变化。')
        pixels = source_gpu[old_gpu_offset:old_gpu_offset+gpu_size]
        original_hash = hashlib.sha256(pixels).hexdigest()
        trim_proof = []
        if remove_yellow:
            pixels, trim_proof = recolor_yellow_trim(pixels, source_id)
        gpu.extend(bytes((-len(gpu)) % 64))
        new_gpu_offset = len(gpu)
        gpu.extend(pixels)
        new_toc_offset = len(candidate) + delta + len(additions)
        struct.pack_into('<Q', header, 0, target_id)
        struct.pack_into('<Q', header, 16, new_toc_offset)
        struct.pack_into('<Q', header, 24, len(source_stream))
        struct.pack_into('<Q', header, 32, new_gpu_offset)
        additions.extend(blob)
        extra_headers.append(header)
        proof.append({'target_lut': str(target_id), 'source_lut': str(source_id),
                      'source_gpu_sha256': original_hash, 'output_gpu_sha256': hashlib.sha256(pixels).hexdigest(), 'trim_edits': trim_proof})
    groups = {}
    for e in entries:
        h = bytearray(candidate[e['header']:e['header']+80])
        struct.pack_into('<Q', h, 16, e['offset']+delta)
        groups.setdefault(e['type'], []).append(h)
    groups[TEXTURE].extend(extra_headers)
    header = bytearray(candidate[:72])
    struct.pack_into('<I', header, 8, nf+extra_count)
    types = bytearray()
    ordered = []
    for i in range(nt):
        type_header = bytearray(candidate[72+i*32:104+i*32])
        tid = struct.unpack_from('<Q', type_header, 8)[0]
        struct.pack_into('<Q', type_header, 16, len(groups[tid]))
        types.extend(type_header)
        ordered.extend(groups[tid])
    for i, h in enumerate(ordered, 1):
        struct.pack_into('<I', h, 76, i)
    result = bytes(header + types + b''.join(ordered) + candidate[old_body_start:] + additions)
    parsed = parse(result, gpu, source_stream)
    if len(parsed) != nf + extra_count:
        raise ValueError('颜色表输出校验失败。')
    return result, bytes(gpu), proof



def attach_scarf(candidate, output_gpu, source_toc, source_gpu, stream):
    from hd2_scarf import merge_torso_scarf, SCARF_UNIT, TORSO_UNITS
    original = {e['id']:e for e in parse(source_toc,source_gpu,stream) if e['type']==UNIT}
    def unit_data(fid):
        e=original[fid]
        goff=struct.unpack_from('<Q',source_toc,e['header']+32)[0]
        gsize=struct.unpack_from('<I',source_toc,e['header']+64)[0]
        return source_toc[e['offset']:e['offset']+e['size']],source_gpu[goff:goff+gsize]
    scarf,scarf_gpu=unit_data(SCARF_UNIT)
    unit_map={target:source for source,target in REMAP.items()}
    unit_map.update(VARIANT_UNIT_ALIASES)
    wanted={target:source for target,source in unit_map.items() if source in TORSO_UNITS}
    entries=parse(candidate,output_gpu,stream)
    result=bytearray(candidate);gpu=bytearray(output_gpu);proof=[]
    for source in TORSO_UNITS:
        body,body_gpu=unit_data(source)
        merged,merged_gpu,detail=merge_torso_scarf(body,body_gpu,scarf,scarf_gpu)
        gpu.extend(bytes((-len(gpu))%64));goff=len(gpu);gpu.extend(merged_gpu)
        targets=[]
        for e in entries:
            if e['type']!=UNIT or wanted.get(e['id'])!=source:continue
            result.extend(bytes((-len(result))%16));toff=len(result);result.extend(merged)
            struct.pack_into('<Q',result,e['header']+16,toff)
            struct.pack_into('<Q',result,e['header']+32,goff)
            struct.pack_into('<I',result,e['header']+56,len(merged))
            struct.pack_into('<I',result,e['header']+64,len(merged_gpu))
            targets.append(str(e['id']))
        proof.append({'torso_source':str(source),'scarf_source':str(SCARF_UNIT),
                      'targets':targets,'merged_toc_sha256':hashlib.sha256(merged).hexdigest(),
                      'merged_gpu_sha256':hashlib.sha256(merged_gpu).hexdigest(),**detail})
    parse(result,gpu,stream)
    if sum(len(x['targets']) for x in proof)!=6:raise ValueError('围巾未覆盖六个胸甲编号。')
    return bytes(result),bytes(gpu),proof


def build(root,output,log=print,*,keep_camo=True,remove_yellow=False,include_scarf=True,restore_scarf=True):
    data=Path(root).resolve();outbase=Path(output).resolve()
    if outbase==data or data in outbase.parents:raise ValueError('输出目录不能位于游戏 data 内。')
    log('读取打包索引……');b,report=check(data)
    log('从原版游戏资源提取 PH-56 和 B-01……')
    src={s:b.load(SOURCE+s) for s in ('','.gpu_resources','.stream')}
    tgt=b.load(TARGET)
    source_entries=parse(src[''],src['.gpu_resources'],src['.stream']);target_entries=parse(tgt)
    sm={e['id']:e for e in source_entries if e['type']==UNIT};tm={e['id']:e for e in target_entries if e['type']==UNIT}
    if set(sm)!=set(REMAP)|{UNMAPPED_SOURCE} or set(tm)!=set(REMAP.values())|{PENDING_TARGET}:raise ValueError('游戏部件已发生变化，拒绝使用旧对应关系。')
    for sid,tid in EXTRA_PAIRS.items():
        if labels(src[''],sm[sid])!=labels(tgt,tm[tid]):raise ValueError('部件标签不匹配，停止转换。')
    # Check the two torso plates independently of their shared labels.
    for sid,tid,meshhash in ((5015099231978410986,1769949868322349152,2746127589),(7088624154722267692,3286754234729990316,3382519647)):
        for blob,e in ((src[''],sm[sid]),(tgt,tm[tid])):
            if struct.pack('<I',meshhash) not in blob[e['offset']:e['offset']+e['size']]:raise ValueError('躯干部件网格标识发生变化。')
    candidate=bytearray(src['']);changed=[]
    for e in source_entries:
        if e['type']==UNIT and e['id'] in REMAP:
            struct.pack_into('<Q',candidate,e['header'],REMAP[e['id']]);changed.append((e['id'],REMAP[e['id']]))
    # Only header FileIDs change. Model bodies, materials, offsets and sidecars stay intact.
    result_entries=parse(candidate,src['.gpu_resources'],src['.stream'])
    assert len(changed)==21
    for before,after in zip(source_entries,result_entries):
        assert before['type']==after['type'] and before['offset']==after['offset'] and before['size']==after['size']
    restored=bytearray(candidate)
    for e in source_entries:struct.pack_into('<Q',restored,e['header'],e['id'])
    assert restored==src['']
    log('补齐 B-01 四个变体的肩甲、胸甲、护肢及共用腰甲……')
    variant_tocs={TARGET:tgt}
    for archive in VARIANT_EXPECTED_UNITS:
        if archive != TARGET:variant_tocs[archive]=b.load(archive)
    candidate,variant_proof=add_variant_units(candidate,src['.gpu_resources'],src['.stream'],src[''],variant_tocs)
    result_entries=parse(candidate,src['.gpu_resources'],src['.stream'])
    color_proof=[]
    output_gpu=src['.gpu_resources']
    if keep_camo:
        log('保留 PH-56 迷彩色：添加六组主颜色表覆盖……')
        candidate,output_gpu,color_proof=add_camo_palettes(candidate,output_gpu,src['.stream'],tgt,remove_yellow=remove_yellow)
        if remove_yellow:log('已将三处确认的黄色饰边色值改为深橄榄色。')
        result_entries=parse(candidate,output_gpu,src['.stream'])
    else:
        log('不保留 PH-56 迷彩色：沿用 B-01 配色。')
    scarf_proof=[]
    if include_scarf:
        log('把独立围巾合入两种体型胸甲，保留四级 LOD 和蒙皮权重……')
        candidate,output_gpu,scarf_proof=attach_scarf(candidate,output_gpu,src[''],src['.gpu_resources'],src['.stream'])
        result_entries=parse(candidate,output_gpu,src['.stream'])
    scarf_color_proof={}
    if include_scarf and restore_scarf:
        from hd2_scarf_colors import restore_scarf_colors
        log('恢复围巾布料：独立配色、原版反光参数，并关闭额外胸甲贴花……')
        target_gpu=None if keep_camo else b.load(TARGET+'.gpu_resources')
        candidate,output_gpu,scarf_color_proof=restore_scarf_colors(candidate,output_gpu,src['.stream'],src[''],src['.gpu_resources'],tgt,target_gpu)
        result_entries=parse(candidate,output_gpu,src['.stream'])
        current_index={(e['id'],e['type']):e for e in result_entries}
        for proof in scarf_proof:
            e=current_index[(int(proof['targets'][0]),UNIT)]
            proof['geometry_merge_toc_sha256']=proof['merged_toc_sha256']
            proof['merged_toc_sha256']=hashlib.sha256(candidate[e['offset']:e['offset']+e['size']]).hexdigest()
        for proof in color_proof:
            if proof['target_lut']=='8899838268388796601':
                e=current_index[(8899838268388796601,TEXTURE)];h=e['header']
                goff=struct.unpack_from('<Q',candidate,h+32)[0];gs=struct.unpack_from('<I',candidate,h+64)[0]
                proof['pre_atlas_gpu_sha256']=proof['output_gpu_sha256']
                proof['output_gpu_sha256']=hashlib.sha256(output_gpu[goff:goff+gs]).hexdigest()
                proof['atlas_scarf_rows_added']=8
    log('检查已安装 Mod 的资源冲突……')
    conflicts,unreadable=collision_scan(data,{(e['id'],e['type']) for e in result_entries})
    out=outbase/('PH56_on_B01_'+('scarf_' if include_scarf else '')+('PH56_camo_no_yellow_' if keep_camo and remove_yellow else ('PH56_camo_' if keep_camo else 'B01_colors_'))+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);out.mkdir(parents=True,exist_ok=False)
    patchdir=out/'Experimental_Mod';patchdir.mkdir()
    name='9ba626afa44a3aa3.patch_0'
    files={name:bytes(candidate),name+'.gpu_resources':output_gpu,name+'.stream':src['.stream']}
    checksums={}
    for fname,content in files.items():
        path=patchdir/fname;path.write_bytes(content);checksums[fname]=hashlib.sha256(content).hexdigest()
    report.update({'experimental':True,'game_tested':False,'method':'Unit ID replacement, optional scarf geometry merge, optional palette overrides','mapped_units':42,'target_units':42,'pending_target_unit':None,'pending_part':None,'unmapped_source_unit_retained':str(UNMAPPED_SOURCE),'scarf_loaded_via_torso':include_scarf,'mappings':[{'source':str(s),'target':str(t)} for s,t in sorted(changed)],'installed_conflicts':conflicts,'unreadable_installed_patches':unreadable,'sha256':checksums,'source_archive_sha256':{s or 'toc':hashlib.sha256(v).hexdigest() for s,v in src.items()},'limitations':['Shared Unit IDs can affect other armor variants and pieces.','No in-game validation of rigging, LOD, attachment behavior, or loading.','No files have been installed or changed in the game directory.']})
    report.update({'version':'0.7','restore_scarf_material':bool(include_scarf and restore_scarf),'scarf_color_atlas':scarf_color_proof,'include_scarf':include_scarf,'scarf_merge':scarf_proof,'keep_ph56_camo':keep_camo,
        'remove_yellow_trim':bool(keep_camo and remove_yellow),
        'yellow_trim_edits':sum(len(x['trim_edits']) for x in color_proof),
        'variant_alias_count':len(variant_proof),'variant_aliases':variant_proof,
        'covered_b01_variants':list(VARIANT_EXPECTED_UNITS),
        'covered_units_per_variant':22,
        'variant_archive_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in variant_tocs.items()},
        'color_mode':'ph56_camo' if keep_camo else 'b01_colors',
        'color_override_count':len(color_proof),'color_lut_overrides':color_proof,
        'color_mode_game_tested':False,
        'color_notes':['Primary material LUTs are replaced using verified per-piece bindings.',
            'Shared palettes may affect other armor using the same palette IDs.',
            'Pattern LUT resources and gameplay settings are not edited.']})
    (out/'diagnostic_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    text='''B-01 穿着 → PH-56 Jaguar 外观：围巾去贴花实验包 0.7
================================================
这次包含真实 Patch 和配套资源；不是配置文件。
从本机游戏资源提取。模型部分修改 Unit 编号；围巾模式合并胸甲与围巾几何；迷彩模式另加主颜色表覆盖。生成过程不写入游戏目录。

状态与限制：
- 覆盖 B-01 四个变体；每个变体的 22 个护甲模型部件均有对应。
- 苗条腰甲使用 PH-56 自身在两种体型间共用的腰甲资源；须在游戏内确认。
- 模型、材质和主贴图取自 PH-56；恢复围巾材质时使用独立的完整颜色表行，胸甲与围巾分开取色；仍需游戏内确认。
- 去黄边模式另改三处已确认的黄色基础色。
- 仅修改外观资源；不包含属性、被动或游戏逻辑文件。
- 围巾开启时合并四级 LOD、追加两根原版锁骨绑定，并保留原始权重；须确认姿势、材质和穿模。
- B-01 多个变体及其他共用模型的护甲可能受影响，不能保证只改变 Variation 1。
- 尚未在游戏内验证，请把它视为测试候选包。

测试步骤：
1. 关闭游戏。
2. 先查看下方冲突清单；用你现有的 Mod 管理器暂时停用相冲突的护甲外观 Mod。
3. 用 Mod 管理器导入 Experimental_Mod 文件夹内的三件配套文件。
   让管理器分配空闲 Patch 编号；不要覆盖已安装的 patch_0。
   三个文件必须使用同一个编号，且保留 .gpu_resources / .stream 后缀。
4. 在游戏内选择 B-01 Tactical；四个变体、两种体型均需实际确认。
5. 若出现异常，退出游戏并在管理器中停用本测试包。
   若手动安装，只撤回本次新加入的三个文件，不删除其他 Mod 或原版档案。

当前检测到的资源重叠（重叠表示潜在冲突，不等于一定无法共存）：
'''
    trim_text = '已开启去黄色饰边：确认的黄色基础色改为深橄榄色。' if keep_camo and remove_yellow else '未开启去黄色饰边。'
    mode_text = '保留 PH-56 迷彩色：包含六组主颜色表覆盖。' if keep_camo else '不保留 PH-56 迷彩色：沿用 B-01 配色。'
    scarf_text=('已开启围巾，恢复原版布料配色与反光参数，并关闭围巾的额外贴花。' if restore_scarf else '已开启围巾，沿用 0.5 的胸甲共用配色。') if include_scarf else '围巾关闭：与 0.4 模型一致。'
    text = scarf_text+'\n'+trim_text+'\n本次配色选项：'+mode_text+'\n切换模式：在 Mod 管理器中停用旧测试包，再导入本包。两个模式只能启用一个。\n新增迷彩颜色需游戏内确认；共用同一颜色表的其他护甲也可能变色。\n\n'+text
    text+='\n'.join(x['file']+'：'+str(x['overlapping_resources'])+' 项重叠' for x in conflicts) if conflicts else '(未检测到；这不等于保证兼容)'
    text+='\n\n诊断及文件 SHA-256 见 diagnostic_report.json。\n'
    (out/'先读我_实验包说明.txt').write_text(text,encoding='utf-8-sig')
    zip_path=outbase/(out.name+'.zip')
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(out))
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip() is not None:raise ValueError('ZIP 校验失败。')
    log('已生成实验 ZIP：'+str(zip_path));log('四个 B-01 变体，每个 22/22 部件；游戏内效果未验证。潜在冲突 Patch 数：'+str(len(conflicts)))
    return zip_path,report

def gui():
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox,scrolledtext
    import threading,queue
    window=tk.Tk();window.title('HD2 原版外观转换 · 围巾去贴花版 0.7');window.geometry('900x790')
    main=ttk.Frame(window,padding=16);main.pack(fill='both',expand=True)
    ttk.Label(main,text='B-01 → PH-56 Jaguar 原版外观',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
    ttk.Label(main,text='直接读取 bundles.nxa；不需要来源 Patch 或外部迁移引擎。').pack(anchor='w',pady=8)
    ttk.Label(main,text='实验版：补全围巾，覆盖四个 B-01 变体；效果需游戏内确认。',foreground='#9b5100').pack(anchor='w')
    data=tk.StringVar(value=r'D:\SteamLibrary\steamapps\common\Helldivers 2\data');output=tk.StringVar(value=str(Path(__file__).resolve().parent/'Generated'))
    for title,var in [('游戏 data 文件夹',data),('生成文件保存到',output)]:
        row=ttk.Frame(main);row.pack(fill='x',pady=8);ttk.Label(row,text=title,width=20).pack(side='left');ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
        def select(v=var):
            p=filedialog.askdirectory()
            if p:v.set(p)
        ttk.Button(row,text='浏览',command=select).pack(side='left',padx=5)
    keep_camo=tk.BooleanVar(value=True)
    colors=ttk.LabelFrame(main,text='配色选项',padding=8);colors.pack(fill='x',pady=8)
    ttk.Radiobutton(colors,text='保留 PH-56 迷彩色（替换 B-01 主颜色表）',variable=keep_camo,value=True).pack(anchor='w')
    ttk.Radiobutton(colors,text='不保留迷彩色（使用 B-01 黑黄配色）',variable=keep_camo,value=False).pack(anchor='w')
    remove_yellow=tk.BooleanVar(value=False)
    trim_button=ttk.Checkbutton(colors,text='去除黄色饰边（改为深橄榄色，仅在保留迷彩时生效）',variable=remove_yellow)
    trim_button.pack(anchor='w',pady=(5,0))
    def update_trim(*_):trim_button.configure(state='normal' if keep_camo.get() else 'disabled')
    keep_camo.trace_add('write',update_trim)
    ttk.Label(colors,text='切换后需重新生成并替换旧测试包；每次只启用一种配色。').pack(anchor='w',pady=(5,0))
    include_scarf=tk.BooleanVar(value=True)
    ttk.Checkbutton(main,text='补全 PH-56 围巾（合入胸甲，需游戏内确认）',variable=include_scarf).pack(anchor='w',pady=6)
    restore_scarf=tk.BooleanVar(value=True)
    scarf_colors=ttk.Checkbutton(main,text='恢复围巾原版布料材质（独立配色、反光参数及去贴花）',variable=restore_scarf)
    scarf_colors.pack(anchor='w',pady=(0,5))
    include_scarf.trace_add('write',lambda *_:scarf_colors.configure(state='normal' if include_scarf.get() else 'disabled'))
    buttons=ttk.Frame(main);buttons.pack(fill='x',pady=10)
    console=scrolledtext.ScrolledText(main,wrap='word',height=18);console.pack(fill='both',expand=True)
    events=queue.Queue();active=False
    def run(mode):
        nonlocal active
        if active:return
        if not data.get().strip() or not output.get().strip():messagebox.showerror('缺少目录','请选择游戏和输出目录。');return
        d,o,c,y,f,k=data.get(),output.get(),keep_camo.get(),remove_yellow.get(),include_scarf.get(),restore_scarf.get();active=True
        def worker():
            try:
                if mode=='check':
                    _,r=check(d);events.put('已确认两件护甲及 GPU/stream 配套资源均在打包索引中。');events.put('分卷数：'+str(r['bundles'])+'；资源数：'+str(r['catalog_packages']))
                else:build(d,o,events.put,keep_camo=c,remove_yellow=y,include_scarf=f,restore_scarf=k)
            except Exception as exc:events.put('失败：'+str(exc))
            finally:events.put(None)
        threading.Thread(target=worker,daemon=True).start()
    ttk.Button(buttons,text='检查打包资源',command=lambda:run('check')).pack(side='left',padx=5)
    ttk.Button(buttons,text='生成实验 Patch',command=lambda:run('build')).pack(side='left',padx=5)
    def poll():
        nonlocal active
        while True:
            try:msg=events.get_nowait()
            except queue.Empty:break
            if msg is None:active=False
            else:console.insert('end',msg+'\n');console.see('end')
        window.after(100,poll)
    console.insert('end','此版本只输出文件，不会自动安装。生成后先看包内说明和冲突清单。\n')
    poll();window.mainloop()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Experimental PH-56 appearance on B-01 builder')
    parser.add_argument('--data');parser.add_argument('--out');parser.add_argument('--check',action='store_true')
    parser.add_argument('--color-mode',choices=('ph56_camo','b01_colors'),default='ph56_camo')
    parser.add_argument('--keep-yellow-trim',action='store_true',help='Keep original PH-56 yellow accents in camo mode')
    parser.add_argument('--no-scarf',action='store_true',help='Disable scarf merging and retain v0.4 geometry')
    parser.add_argument('--remove-yellow-trim',action='store_true',help='Use custom olive trim instead of original yellow')
    parser.add_argument('--legacy-scarf-colors',action='store_true',help='Retain v0.5 shared scarf coloring')
    args=parser.parse_args()
    if args.data:
        if args.check:print(json.dumps(check(args.data)[1],ensure_ascii=False,indent=2))
        elif args.out:build(args.data,args.out,keep_camo=args.color_mode=='ph56_camo',remove_yellow=args.remove_yellow_trim and not args.keep_yellow_trim,include_scarf=not args.no_scarf,restore_scarf=not args.legacy_scarf_colors)
        else:parser.error('--out is required for building')
    else:gui()
