"""Merge the verified PH-56 scarf geometry into its loaded torso armor Unit.

The armor-kit accessory slot is absent on B-01. This joins the four original
scarf LODs to the torso LODs, preserving material resources and skin weights.
"""
import struct, math

SCARF_UNIT = 9871997257301833681
TORSO_UNITS = (7088624154722267692, 5015099231978410986)

def u32(b, p): return struct.unpack_from('<I', b, p)[0]
def put(b, p, v): struct.pack_into('<I', b, p, v)
def align(b, n=16): b.extend(bytes((-len(b)) % n))
def items(b, off): return [off + u32(b, off+4+4*i) for i in range(u32(b, off))]
def identity_rotation(m):
    expected = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.)
    return all(abs(x-y)<1e-6 for x,y in zip(m[:12], expected)) and abs(m[15]-1)<1e-6

def transforms(b):
    p=u32(b,0x34);n=u32(b,p)
    return [dict(local=b[p+16+64*i:p+16+64*(i+1)],
                 matrix=struct.unpack_from('<16f',b,p+16+64*n+64*i),
                 link=struct.unpack_from('<HH',b,p+16+128*n+4*i),
                 name=u32(b,p+16+132*n+4*i)) for i in range(n)]

def materials(b):
    p=u32(b,0x70);n=u32(b,p)
    return [(u32(b,p+4+4*i),struct.unpack_from('<Q',b,p+4+4*n+8*i)[0]) for i in range(n)]

def bone_lods(b):
    result=[]
    for p in items(b,u32(b,0x58)):
        n,mo,ro,fo=struct.unpack_from('<4I',b,p)
        real=list(struct.unpack_from('<'+'I'*n,b,p+ro))
        matrices=[struct.unpack_from('<16f',b,p+mo+64*i) for i in range(n)]
        fp=p+fo;remaps=[]
        for i in range(u32(b,fp)):
            off,count=struct.unpack_from('<II',b,fp+4+8*i)
            remaps.append(list(struct.unpack_from('<'+'I'*count,b,fp+off)))
        result.append(dict(real=real,matrices=matrices,remaps=remaps))
    return result

def streams(b):
    return [bytearray(b[p:p+448]) for p in items(b,u32(b,0x5c))]

def meshes(b):
    result=[]
    for p in items(b,u32(b,0x64)):
        nm,mat=struct.unpack_from('<II',b,p+104);ns,sec=struct.unpack_from('<II',b,p+120)
        result.append(dict(header=bytearray(b[p:p+128]),lod=struct.unpack_from('<i',b,p+56)[0],
                           transform=u32(b,p+48),stream=u32(b,p+60),
                           materials=[u32(b,p+mat+4*i) for i in range(nm)],
                           sections=[list(struct.unpack_from('<6I',b,p+sec+24*i)) for i in range(ns)]))
    return result

def section_data(mesh, stream, gpu):
    if len(mesh['sections'])!=1: raise ValueError('围巾合并所需的单材质网格结构已变化。')
    sec=mesh['sections'][0];_,start,nv,istart,ni,_=sec
    stride=u32(stream,356);vo=u32(stream,416)+start*stride;io=u32(stream,424)+istart*2
    if u32(stream,396)!=0 or io+ni*2>len(gpu) or vo+nv*stride>len(gpu):
        raise ValueError('围巾网格索引或数据范围异常。')
    raw=gpu[vo:vo+nv*stride];idx=list(struct.unpack_from('<'+'H'*ni,gpu,io))
    if idx and max(idx)>=nv: raise ValueError('围巾网格顶点索引越界。')
    return raw,idx,nv

def translate_bind(matrix, delta):
    # Stored matrices are column-major. B_new = B_old * T(-delta).
    result=list(matrix)
    for r in range(4): result[12+r]-=sum(matrix[4*c+r]*delta[c] for c in range(3))
    return tuple(result)

def bone_blob(real, matrices, remaps):
    b=bytearray(16);mo=len(b)
    for matrix in matrices:b.extend(struct.pack('<16f',*matrix))
    ro=len(b);b.extend(struct.pack('<'+'I'*len(real),*real));fo=len(b)
    b.extend(struct.pack('<I',len(remaps))+bytes(8*len(remaps)))
    for i,remap in enumerate(remaps):
        struct.pack_into('<II',b,fo+4+8*i,len(b)-fo,len(remap))
        b.extend(struct.pack('<'+'I'*len(remap),*remap))
    struct.pack_into('<4I',b,0,len(real),mo,ro,fo)
    return bytes(b)

def mesh_blob(mesh):
    b=bytearray(mesh['header']);nm=len(mesh['materials']);ns=len(mesh['sections'])
    put(b,104,nm);put(b,108,128);put(b,120,ns);put(b,124,128+nm*4)
    b.extend(struct.pack('<'+'I'*nm,*mesh['materials']))
    for s in mesh['sections']:b.extend(struct.pack('<6I',*s))
    return bytes(b)

def append_table(b, blobs, hashes=None, stream_table=False):
    align(b);start=len(b);n=len(blobs)
    b.extend(struct.pack('<I',n)+bytes(4*n))
    if hashes is not None:b.extend(struct.pack('<'+'I'*n,*hashes))
    if stream_table:b.extend(bytes(4))
    for i,blob in enumerate(blobs):
        put(b,start+4+4*i,len(b)-start);b.extend(blob)
    return start

def merge_torso_scarf(torso, torso_gpu, scarf, scarf_gpu):
    for b in (torso,scarf):
        if u32(b,0x2c)!=10800438 or struct.unpack_from('<5Q',b)!=(0,0,0,0,0):
            raise ValueError('围巾或胸甲 Unit 版本/引用结构已变化。')
    bt,st=transforms(torso),transforms(scarf)
    bones,scarfbones=bone_lods(torso),bone_lods(scarf)
    bs,ss=streams(torso),streams(scarf);bm,sm=meshes(torso),meshes(scarf)
    if len(bt)!=16 or len(st)!=18 or len(bones)!=4 or len(scarfbones)!=4:
        raise ValueError('围巾或胸甲骨骼结构已变化。')
    if len(bm)!=5 or len(sm)!=5 or len(bs)!=2 or len(ss)!=2:
        raise ValueError('围巾或胸甲 LOD 结构已变化。')
    for s,fmt in ((bs[0],0),(ss[0],33)):
        if u32(s,356)!=36 or struct.unpack_from('<Q',s,328)[0]!=7:
            raise ValueError('围巾顶点布局已变化。')
        expected=[(0,2),(1,30),(4,33),(4,33),(4,33),(7,fmt),(6,28)]
        if [struct.unpack_from('<II',s,8+20*i) for i in range(7)]!=expected:
            raise ValueError('围巾顶点属性已变化。')
    # Reuse existing skeleton names. Only the two animated clavicles are added.
    by_hash={t['name']:i for i,t in enumerate(bt)};smap={}
    real_needed=set().union(*(set(x['real']) for x in scarfbones))
    for i in sorted(real_needed):
        t=st[i]
        if t['name'] not in by_hash:
            parent=t['link'][1]
            if parent not in smap: raise ValueError('围巾父骨骼不存在。')
            copied=dict(t);copied['link']=(t['link'][0],smap[parent])
            by_hash[t['name']]=len(bt);bt.append(copied)
        smap[i]=by_hash[t['name']]
        existing=bt[smap[i]]
        if max(abs(x-y) for x,y in zip(existing['matrix'],t['matrix']))>1e-5:
            raise ValueError('围巾与胸甲骨骼的姿态不同。')
    # Give the scarf its own material slots in the joined Unit.
    base_materials=materials(torso);scarf_materials=dict(materials(scarf));slot_map={}
    for i,old in enumerate(sorted({x['materials'][0] for x in sm if x['lod']>=0}),1):
        slot=0xf56a0000+i
        if slot in dict(base_materials):raise ValueError('围巾材质槽编号冲突。')
        slot_map[old]=slot;base_materials.append((slot,scarf_materials[old]))
    scarf_by_lod={x['lod']:x for x in sm};new_bones={};vertices=bytearray();indices=[];lod_proof=[]
    for mesh in bm:
        lod=mesh['lod']
        if lod<0:continue
        s_mesh=scarf_by_lod[lod]
        tm=bt[mesh['transform']]['matrix'];scm=st[s_mesh['transform']]['matrix']
        if not identity_rotation(tm) or not identity_rotation(scm):
            raise ValueError('围巾模型旋转结构已变化。')
        delta=[scm[12+i]-tm[12+i] for i in range(3)]
        body_raw,body_idx,bn=section_data(mesh,bs[0],torso_gpu)
        scarf_raw,scarf_idx,sn=section_data(s_mesh,ss[0],scarf_gpu)
        if bn+sn>65535:raise ValueError('合并网格超过 16 位索引限制。')
        vertex_start=len(vertices)//40;index_start=len(indices)
        for raw,n,kind in ((body_raw,bn,'body'),(scarf_raw,sn,'scarf')):
            for i in range(n):
                v=bytearray(raw[i*36:(i+1)*36]);weight=struct.unpack_from('<f' if kind=='body' else '<2e',v,28)
                if kind=='body' and weight!=(1.0,):raise ValueError('胸甲的原始单骨骼权重已变化。')
                if kind=='scarf':
                    pos=struct.unpack_from('<3f',v)
                    struct.pack_into('<3f',v,0,*(pos[j]+delta[j] for j in range(3)))
                vertices.extend(v[:28]);vertices.extend(struct.pack('<4e',*(list(weight)+[0.]*(4-len(weight)))))
                vertices.extend(v[32:36])
        indices.extend(body_idx);indices.extend(i+bn for i in scarf_idx)
        mesh['materials']=[mesh['materials'][0],slot_map[s_mesh['materials'][0]]]
        mesh['sections']=[[0,vertex_start,bn+sn,index_start,len(body_idx),0],
                          [1,vertex_start,bn+sn,index_start+len(body_idx),len(scarf_idx),1]]
        ps=[struct.unpack_from('<3f',vertices,(vertex_start+i)*40) for i in range(bn+sn)]
        low=[min(p[j] for p in ps) for j in range(3)];high=[max(p[j] for p in ps) for j in range(3)]
        radius=max(math.sqrt(sum(x*x for x in p)) for p in ps)
        struct.pack_into('<7f',mesh['header'],8,*(low+high+[radius]))
        real=list(bones[lod]['real']);mats=list(bones[lod]['matrices']);sreal=[]
        for idx,matrix in zip(scarfbones[lod]['real'],scarfbones[lod]['matrices']):
            new_index=smap[idx];converted=translate_bind(matrix,delta)
            if new_index in real:
                at=real.index(new_index)
                if max(abs(x-y) for x,y in zip(mats[at],converted))>2e-5:
                    raise ValueError('围巾与胸甲的逆绑定矩阵不同。')
            else:at=len(real);real.append(new_index);mats.append(converted)
            sreal.append(at)
        remaps=[list(bones[lod]['remaps'][0]),[sreal[x] for x in scarfbones[lod]['remaps'][0]]]
        new_bones[lod]=bone_blob(real,mats,remaps)
        lod_proof.append({'lod':lod,'torso_vertices':bn,'scarf_vertices':sn,'torso_indices':len(body_idx),
                          'scarf_indices':len(scarf_idx),'scarf_translation':delta,'bounds_min':low,'bounds_max':high})
    # A single shared vertex layout with four half-float weights handles both originals.
    new_gpu=bytearray(vertices);align(new_gpu);index_offset=len(new_gpu)
    new_gpu.extend(struct.pack('<'+'H'*len(indices),*indices));align(new_gpu)
    primary=bytearray(bs[0]);put(primary,8+5*20+4,35)
    put(primary,352,len(vertices)//40);put(primary,356,40);put(primary,392,len(indices))
    struct.pack_into('<4I',primary,416,0,len(vertices),index_offset,len(indices)*2)
    proxy=bytearray(bs[1])
    for p in (416,424):
        old=u32(bs[1],p);size=u32(bs[1],p+4);align(new_gpu);put(proxy,p,len(new_gpu));new_gpu.extend(torso_gpu[old:old+size])
    # Rebuild only the two torso units; preserve their original identifiers and LOD group.
    result=bytearray(torso[:u32(torso,0x34)]);tp=len(result);result.extend(struct.pack('<I',len(bt))+bytes(12))
    for t in bt:result.extend(t['local'])
    for t in bt:result.extend(struct.pack('<16f',*t['matrix']))
    for t in bt:result.extend(struct.pack('<HH',*t['link']))
    for t in bt:result.extend(struct.pack('<I',t['name']))
    align(result);put(result,0x34,tp);put(result,0x4c,len(result))
    result.extend(torso[u32(torso,0x4c):u32(torso,0x58)])
    put(result,0x58,append_table(result,[new_bones[i] for i in range(4)]))
    stream_hashes=[u32(torso,u32(torso,0x5c)+4+8+4*i) for i in range(2)]
    put(result,0x5c,append_table(result,[primary,proxy],stream_hashes,True))
    put(result,0x64,append_table(result,[mesh_blob(x) for x in bm],[u32(x['header'],40) for x in bm]))
    align(result);put(result,0x70,len(result));result.extend(struct.pack('<I',len(base_materials)))
    result.extend(struct.pack('<'+'I'*len(base_materials),*(x[0] for x in base_materials)))
    result.extend(struct.pack('<'+'Q'*len(base_materials),*(x[1] for x in base_materials)))
    oldmat=u32(torso,0x70);oldend=u32(torso,0x60);oldcount=u32(torso,oldmat)
    result.extend(torso[oldmat+4+12*oldcount:oldend]);put(result,0x60,len(result))
    result.extend(struct.pack('<Q',len(bm)));align(result)
    return bytes(result),bytes(new_gpu),{'added_skeleton_bones':len(bt)-16,'lods':lod_proof,'material_slots':len(base_materials)}
