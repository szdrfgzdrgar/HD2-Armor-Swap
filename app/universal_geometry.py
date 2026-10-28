"""Native Unit assembly for arbitrary armor kits; helmet/cape units are never inputs."""
import struct,math,hashlib
from hd2_scarf import transforms,bone_lods,streams,meshes,materials,bone_blob,mesh_blob,append_table,align,u32,put

IDENTITY=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
SIZES={0:4,2:12,3:16,4:4,24:16,28:4,29:4,30:4,33:4,35:8}

def mul(a,b):return tuple(sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4))
def inverse(a):
    rows=[[a[c*4+r] for c in range(4)]+[float(r==c) for c in range(4)] for r in range(4)]
    for c in range(4):
        pivot=max(range(c,4),key=lambda r:abs(rows[r][c]))
        if abs(rows[pivot][c])<1e-12:raise ValueError('模型包含不可逆的变换矩阵。')
        rows[c],rows[pivot]=rows[pivot],rows[c];v=rows[c][c];rows[c]=[x/v for x in rows[c]]
        for r in range(4):
            if r==c:continue
            v=rows[r][c];rows[r]=[x-v*y for x,y in zip(rows[r],rows[c])]
    return tuple(rows[r][4+c] for c in range(4) for r in range(4))
def point(a,p):return tuple(sum(a[c*4+r]*p[c] for c in range(3))+a[12+r] for r in range(3))
def determinant(a):return a[0]*(a[5]*a[10]-a[9]*a[6])-a[4]*(a[1]*a[10]-a[9]*a[2])+a[8]*(a[1]*a[6]-a[5]*a[2])
def normalized(p):
    length=math.sqrt(sum(x*x for x in p))
    return tuple(x/(length or 1) for x in p)
def sign(v):return 1 if v>=0 else -1

def rotate_normal(raw,inv):
    if max(abs(inv[i]-IDENTITY[i]) for i in range(12))<1e-8:return raw
    n=struct.unpack('<I',raw)[0];x=(n&1023)*2/1023-1;y=((n>>10)&1023)*2/1023-1;z=1-abs(x)-abs(y)
    if z<0:x,y=(1-abs(y))*sign(x),(1-abs(x))*sign(y)
    v=normalized(tuple(inv[r*4]*x+inv[r*4+1]*y+inv[r*4+2]*z for r in range(3)))
    x,y,z=v;scale=abs(x)+abs(y)+abs(z);x/=scale or 1;y/=scale or 1
    if z<0:x,y=(1-abs(y))*sign(x),(1-abs(x))*sign(y)
    packed=(n&0xfff00000)|min(1023,max(0,round((x+1)*511.5)))|(min(1023,max(0,round((y+1)*511.5)))<<10)
    return struct.pack('<I',packed)

def layout(stream):
    out={};cursor=0
    for i in range(struct.unpack_from('<Q',stream,328)[0]):
        kind,fmt,index=struct.unpack_from('<III',stream,8+20*i)
        if fmt not in SIZES:raise ValueError('尚未识别的顶点格式：'+str(fmt))
        out[kind,index]=(fmt,cursor);cursor+=SIZES[fmt]
    if cursor>u32(stream,356):raise ValueError('顶点属性超过声明长度。')
    return out

def weight_values(raw,fmt):
    if fmt==0:return (*struct.unpack('<f',raw),0.,0.,0.)
    if fmt==33:return (*struct.unpack('<2e',raw),0.,0.)
    if fmt==35:return struct.unpack('<4e',raw)
    if fmt==3:return struct.unpack('<4f',raw)
    if fmt==29:
        v=struct.unpack('<I',raw)[0]
        return ((v&1023)/1023,((v>>10)&1023)/1023,((v>>20)&1023)/1023,0.)
    raise ValueError('尚未识别的蒙皮权重格式。')

def prepare(part):
    b=part['toc'];part=dict(part);part['transforms']=transforms(b);part['bones']=bone_lods(b);part['streams']=streams(b);part['meshes']=meshes(b);part['materials']=dict(materials(b))
    part['layouts']=[layout(s) for s in part['streams']]
    return part

def extract_section(part,mesh,sec):
    stream=part['streams'][mesh['stream']];attrs=part['layouts'][mesh['stream']];gpu=part['gpu']
    mi,vo,nv,io,ni,group=sec;stride=u32(stream,356);index_size=4 if u32(stream,396)==1 else 2
    index_offset=u32(stream,424)+io*index_size;vbo=u32(stream,416)
    if index_offset+ni*index_size>len(gpu):raise ValueError('模型三角形数据越界。')
    indices=struct.unpack_from('<'+('I' if index_size==4 else 'H')*ni,gpu,index_offset)
    # Some native units under-report NumVertices; the SDK also derives the
    # true range from referenced indices. Validate against the real stream.
    if indices and vo+max(indices)>=u32(stream,352):raise ValueError('部件顶点索引超过实际缓冲区。')
    used=sorted(set(indices));dense={v:i for i,v in enumerate(used)}
    values=[gpu[vbo+(vo+i)*stride:vbo+(vo+i+1)*stride] for i in used]
    if any(len(v)!=stride for v in values):raise ValueError('模型顶点数据越界。')
    lod=mesh['lod'];bi=part['bones'][lod]
    if mi>=len(bi['remaps']):raise ValueError('材质和骨骼对应表不完整。')
    remap=bi['remaps'][mi];available=sorted(i for k,i in attrs if k==6)
    order=[group]+[i for i in available if i!=group]
    selected=None
    for candidate in order:
        if (6,candidate) not in attrs:continue
        fmt,off=attrs[6,candidate]
        if fmt not in (28,24):continue
        good=True
        for v in values:
            wf,wo=attrs[7,0];weights=weight_values(v[wo:wo+SIZES[wf]],wf)
            ids=struct.unpack_from('<4B' if fmt==28 else '<4I',v,off)
            if any(w>1e-8 and idx>=len(remap) for w,idx in zip(weights,ids)):good=False;break
        if good:selected=candidate;break
    if selected is None:raise ValueError('没有可用的部件骨骼索引组。')
    return values,[dense[i] for i in indices],attrs,bi,remap,selected

def assemble(parts,base_part,target_unit,material_for,log=lambda x:None,validate_poses=False):
    """Join complete selected-body armor into a target torso carrier.

    Each draw section retains its own source textures, mask array, weights,
    palette and joint-remap semantics. All four distance levels are assembled.
    """
    parts=[prepare(p) for p in parts];base=next(p for p in parts if p['id']==base_part)
    tf=[dict(t) for t in base['transforms']];by_hash={t['name']:i for i,t in enumerate(tf)}
    def add_transform(part,i,active=None):
        t=part['transforms'][i]
        if t['name'] in by_hash:return by_hash[t['name']]
        active=set() if active is None else set(active)
        if i in active:raise ValueError('部件骨骼层级存在循环。')
        active.add(i);parent=t['link'][1]
        newparent=add_transform(part,parent,active) if parent!=i else 0
        copied=dict(t);copied['link']=(t['link'][0],newparent);at=len(tf);tf.append(copied);by_hash[t['name']]=at
        return at
    # Skinning nodes and their ancestors only; retain the base mesh's LOD nodes.
    for part in parts:
        for bi in part['bones']:
            for i in bi['real']:add_transform(part,i)
    if len(tf)>=65535:raise ValueError('合并后的骨骼数量过多。')
    base_lods={x['lod']:x for x in base['meshes'] if x['lod']>=0}
    for mesh in base_lods.values():
        i=mesh['transform'];tf[i]['matrix']=IDENTITY
        local=bytearray(tf[i]['local']);struct.pack_into('<12f',local,0,1,0,0,0,1,0,0,0,1,0,0,0);struct.pack_into('<4f',local,48,1,1,1,0);tf[i]['local']=bytes(local)
    descriptions=[];palette_bones={};material_ids=[];material_index={};bone_maps={};stats=[]
    for lod in (3,2,1,0):
        draw=[];real=[];bind=[];bone_lookup={}
        for part in parts:
            available=sorted({x['lod'] for x in part['meshes'] if x['lod']>=0})
            pick=min(available,key=lambda x:(abs(x-lod),x))
            for mesh in (x for x in part['meshes'] if x['lod']==pick):
                world=part['transforms'][mesh['transform']]['matrix'];iw=inverse(world)
                for sec in mesh['sections']:
                    if sec[4]==0:continue
                    values,indices,attrs,bi,remap,index_group=extract_section(part,mesh,sec)
                    if not values:continue
                    mid=part['materials'].get(mesh['materials'][sec[0]],0)
                    private=material_for(part,mid,lod)
                    if private not in material_index:material_index[private]=len(material_ids);material_ids.append(private)
                    matidx=material_index[private];mapped=[]
                    for local in remap:
                        old_index=bi['real'][local];new_index=add_transform(part,old_index)
                        # Re-express each original inverse bind in the joined
                        # skeleton and the identity mesh coordinate system.
                        converted=mul(mul(mul(inverse(tf[new_index]['matrix']),part['transforms'][old_index]['matrix']),bi['matrices'][local]),iw)
                        key=(new_index,tuple(round(v,5) for v in converted))
                        if key not in bone_lookup:bone_lookup[key]=len(real);real.append(new_index);bind.append(converted)
                        mapped.append(bone_lookup[key])
                    draw.append(dict(part=part,mesh=mesh,values=values,indices=indices,attrs=attrs,index_group=index_group,mapped=mapped,material=matidx,world=world,inverse=iw,original_bi=bi,original_remap=remap))
                    stats.append({'lod':lod,'source_unit':str(part['id']),'source_material':str(mid),'vertices':len(values),'triangles':len(indices)//3,'index_group':index_group})
        if not real:raise ValueError('所选盔甲没有可渲染的部件。')
        descriptions.append((lod,draw,real,bind))
    index_fmt=28 if max(len(r) for _,_,r,_ in descriptions)<256 else 24
    include_color=any((5,0) in d['attrs'] for _,draw,_,_ in descriptions for d in draw)
    uv_count=max(i+1 for _,draw,_,_ in descriptions for d in draw for k,i in d['attrs'] if k==4)
    vstride=(4 if include_color else 0)+12+4+4*uv_count+16+(4 if index_fmt==28 else 16);vertices=bytearray();triangles=[];compiled_meshes=[];bone_sections={};max_error=0.;checked=0
    for lod,draw,real,bind in descriptions:
        sections=[];points=[];group_key=None;group_draw=None
        def flush_mesh():
            if not sections:return
            # Keep the original part's render flags and mesh metadata. The
            # compiled joint/vertex coordinates still use the identity carrier.
            source_mesh=group_draw['mesh'];base_mesh=base_lods[min(base_lods,key=lambda x:abs(x-lod))]
            mesh=dict(source_mesh);mesh['header']=bytearray(source_mesh['header']);mesh['lod']=lod;mesh['stream']=0;mesh['transform']=base_mesh['transform'];mesh['sections']=list(sections)
            put(mesh['header'],48,mesh['transform']);put(mesh['header'],56,lod);put(mesh['header'],60,0)
            lo=[min(p[k] for p in points) for k in range(3)];hi=[max(p[k] for p in points) for k in range(3)]
            struct.pack_into('<7f',mesh['header'],8,*(lo+hi+[max(math.sqrt(sum(v*v for v in p)) for p in points)]))
            compiled_meshes.append(mesh)
        for d in draw:
            next_key=(d['part']['id'],id(d['mesh']))
            if next_key!=group_key:
                flush_mesh();sections=[];points=[];group_key=next_key;group_draw=d
            nv=len(d['values']);start_vertex=len(vertices)//vstride;start_index=len(triangles);attrs=d['attrs'];part=d['part'];selected=d['index_group'];mi=d['material']
            for v in d['values']:
                _,po=attrs[0,0];pos=struct.unpack_from('<3f',v,po);newpos=point(d['world'],pos);points.append(newpos)
                _,no=attrs[1,0];normal=rotate_normal(v[no:no+4],d['inverse'])
                color=v[attrs[5,0][1]:attrs[5,0][1]+4] if (5,0) in attrs else b'\xff'*4
                uv=b''.join(v[attrs[4,i][1]:attrs[4,i][1]+4] if (4,i) in attrs else bytes(4) for i in range(uv_count))
                wf,wo=attrs[7,0];weights=weight_values(v[wo:wo+SIZES[wf]],wf)
                bf,bo=attrs[6,selected];ids=struct.unpack_from('<4B' if bf==28 else '<4I',v,bo)
                remapped=[d['mapped'][i] if w>1e-8 else 0 for w,i in zip(weights,ids)]
                vertices.extend((color if include_color else b'')+struct.pack('<3f',*newpos)+normal+uv+struct.pack('<4f',*weights)+struct.pack('<4B' if index_fmt==28 else '<4I',*remapped))
                if validate_poses and checked%37==0:
                    # Deterministic joint-space pose checks across a sparse set
                    # of vertices, without requiring a running game.
                    src=[0.,0.,0.];dst=[0.,0.,0.]
                    for w,old,new in zip(weights,ids,remapped):
                        if w<=1e-8:continue
                        old_real=d['original_bi']['real'][d['original_remap'][old]];old_joint=part['transforms'][old_real]['matrix']
                        a=point(mul(old_joint,d['original_bi']['matrices'][d['original_remap'][old]]),pos)
                        b=point(mul(tf[real[new]]['matrix'],bind[new]),newpos)
                        for k in range(3):src[k]+=w*a[k];dst[k]+=w*b[k]
                    max_error=max(max_error,max(abs(a-b) for a,b in zip(src,dst)))
                checked+=1
            idx=d['indices']
            if determinant(d['world'])<0:idx=[x for i in range(0,len(idx),3) for x in (idx[i],idx[i+2],idx[i+1])]
            triangles.extend(idx)
            sections.append([mi,start_vertex,nv,start_index,len(idx),mi])
        # Each draw uses its own vertex window, preserving per-material skin
        # data even when the original meshes shared vertices across materials.
        flush_mesh();bone_sections[lod]=(real,bind)
    # Remap identity for every draw slot: individual vertex indices have
    # already been converted to this LOD's combined joint palette.
    nmat=len(material_ids)
    for mesh in compiled_meshes:mesh['materials']=[0xa8000000+i for i in range(nmat)]
    bones=[bone_blob(bone_sections[i][0],bone_sections[i][1],[list(range(len(bone_sections[i][0]))) for _ in range(nmat)]) for i in range(4)]
    gpu=bytearray(vertices);align(gpu);io=len(gpu);wide=max(triangles,default=0)>65535
    # Indices are local to each section, and each section has its own VB start.
    gpu.extend(struct.pack('<'+('I' if wide else 'H')*len(triangles),*triangles))
    stream=bytearray(base['streams'][0]);stream[8:328]=bytes(320)
    components=([(5,4,0)] if include_color else [])+[(0,2,0),(1,30,0),*((4,33,i) for i in range(uv_count)),(7,3,0),(6,index_fmt,0)]
    for i,(kind,fmt,index) in enumerate(components):struct.pack_into('<IIIQ',stream,8+20*i,kind,fmt,index,0)
    struct.pack_into('<Q',stream,328,len(components));put(stream,352,len(vertices)//vstride);put(stream,356,vstride);put(stream,392,len(triangles));put(stream,396,int(wide))
    struct.pack_into('<4I',stream,416,0,len(vertices),io,len(triangles)*(4 if wide else 2))
    # Keep source LOD group/layout and target slot identity. No helmet units,
    # gameplay properties, passives or armor-stat definitions are emitted.
    original=base['toc'];result=bytearray(original[:u32(original,0x34)]);result[:40]=bytes(40);tp=len(result)
    result.extend(struct.pack('<I',len(tf))+bytes(12))
    for t in tf:result.extend(t['local'])
    for t in tf:result.extend(struct.pack('<16f',*t['matrix']))
    for t in tf:result.extend(struct.pack('<HH',*t['link']))
    for t in tf:result.extend(struct.pack('<I',t['name']))
    align(result);put(result,0x34,tp);put(result,0x4c,len(result));put(result,0x50,0);put(result,0x54,0)
    cp=u32(target_unit,0x4c);end=min(x for x in (u32(target_unit,p) for p in (0x50,0x54,0x58)) if x>cp)
    result.extend(target_unit[cp:end])
    put(result,0x58,append_table(result,bones));put(result,0x5c,append_table(result,[stream],[u32(stream,0)],True))
    put(result,0x64,append_table(result,[mesh_blob(x) for x in compiled_meshes],[u32(x['header'],40) for x in compiled_meshes]))
    align(result);put(result,0x70,len(result));result.extend(struct.pack('<I',nmat));result.extend(struct.pack('<'+'I'*nmat,*(0xa8000000+i for i in range(nmat))));result.extend(struct.pack('<'+'Q'*nmat,*material_ids));put(result,0x60,len(result));result.extend(struct.pack('<Q',4));align(result)
    if validate_poses and max_error>1e-4:raise ValueError('合并模型的骨骼校验失败：'+str(max_error))
    lod_proof=rebuild_lod_groups(result,original,compiled_meshes)
    return bytes(result),bytes(gpu),{'preserved_part_mesh_headers':True,'synthetic_vertex_color':False if not include_color else True,'uv_sets':uv_count,'lod_references':lod_proof,'parts':len(parts),'sections':stats,'joints':len(tf),'materials':nmat,'vertices':len(vertices)//vstride,'triangles':len(triangles)//3,'skeleton_rest_error':max_error,'lods':4}



def lod_index_locations(unit):
    """Parse native LOD entry mesh indices (Filediver unit.go LODGroup)."""
    base=u32(unit,0x30)
    if not base or base+4>len(unit):raise ValueError('模型缺少有效的远近显示表。')
    count=u32(unit,base)
    if count>1024 or base+4+4*count>len(unit):raise ValueError('远近显示组数量越界。')
    locations=[]
    for i in range(count):
        group=base+u32(unit,base+4+4*i)
        if group+20>len(unit):raise ValueError('远近显示组头越界。')
        entries=u32(unit,group+16)
        if entries>1024 or group+20+4*entries>len(unit):raise ValueError('远近显示条目数量越界。')
        for j in range(entries):
            entry=group+u32(unit,group+20+4*j)
            if entry+12>len(unit):raise ValueError('远近显示条目头越界。')
            n=u32(unit,entry+8)
            if n>65536 or entry+12+4*n>len(unit):raise ValueError('远近显示模型索引表越界。')
            locations.extend(entry+12+4*k for k in range(n))
    if not locations:raise ValueError('模型远近显示表为空。')
    return locations

def validate_lod_links(unit):
    count=len(meshes(unit));values=[u32(unit,p) for p in lod_index_locations(unit)]
    if any(v>=count for v in values):raise ValueError('远近显示表引用了不存在的模型，停止生成。')
    return {'mesh_count':count,'references':values,'all_in_range':True}

def repair_lod_links(unit,original,compiled_meshes=None):
    """Rewrite original mesh ordinals to the new mesh ordinals by actual LOD.

    Joining a Unit can remove its proxy and other original mesh records. The
    native LOD groups must follow the new mesh table, including menu previews.
    """
    old=meshes(original);new=meshes(unit) if compiled_meshes is None else compiled_meshes
    by_lod={m['lod']:i for i,m in enumerate(new)};changed=0
    for p in lod_index_locations(unit):
        index=u32(unit,p)
        if index>=len(old) or old[index]['lod'] not in by_lod:raise ValueError('无法对应原始远近模型，停止生成。')
        replacement=by_lod[old[index]['lod']]
        changed+=replacement!=index;put(unit,p,replacement)
    result=validate_lod_links(unit);result['rewritten_references']=changed
    return result



def rebuild_lod_groups(unit,original,compiled_meshes):
    base=u32(original,0x30);old_meshes=meshes(original);groups=[]
    by_lod={lod:[i for i,m in enumerate(compiled_meshes) if m['lod']==lod] for lod in (0,1,2,3)}
    for i in range(u32(original,base)):
        group=base+u32(original,base+4+4*i);nf,ne=struct.unpack_from('<II',original,group+12)
        block=bytearray(original[group:group+20])+bytearray(4*(ne+nf))
        for j in range(ne):
            entry=group+u32(original,group+20+4*j);n=u32(original,entry+8);old_indices=struct.unpack_from('<'+'I'*n,original,entry+12)
            lods=list(dict.fromkeys(old_meshes[index]['lod'] for index in old_indices))
            indices=list(dict.fromkeys(index for lod in lods for index in by_lod[lod]))
            if not indices:raise ValueError('远近显示表没有对应的原版部件。')
            put(block,20+4*j,len(block));block.extend(original[entry:entry+8]+struct.pack('<I',len(indices))+struct.pack('<'+'I'*len(indices),*indices))
        for j in range(nf):
            old_footer=group+u32(original,group+20+4*ne+4*j);align(block);put(block,20+4*ne+4*j,len(block));block.extend(original[old_footer:old_footer+40])
        groups.append(block)
    put(unit,0x30,append_table(unit,groups))
    result=validate_lod_links(unit);result['rebuilt_for_part_meshes']=True
    return result


def hidden_unit(unit):
    result=bytearray(unit)
    for mesh_at in [u32(result,0x64)+u32(result,u32(result,0x64)+4+4*i) for i in range(u32(result,u32(result,0x64)))]:
        n=u32(result,mesh_at+120);offset=u32(result,mesh_at+124)
        for j in range(n):put(result,mesh_at+offset+24*j+16,0)
    return bytes(result)
