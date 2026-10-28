"""Keep a merged PH-56 scarf on its own original material-LUT rows.

Shared primary LUT + shifted RGBA ID-mask arrays follow the asset-merging
layout documented by ARoese/Helldivers-2-IDMask-Edit. No image conversion or
color estimation is performed: all 23 columns of each scarf row are copied.
"""
import struct,hashlib

TEXTURE=0xcd4238c6a0c69e32
MATERIAL=0xeac0b497876adedf
UNIT=0xe0a48d0be9a7453f
SCARF_MATERIAL=8738487785636392115
TORSO_MATERIAL=614122630990816523
SCARF_LUT=5088769063782502550
SCARF_MASK=7898898053052312356
TARGET_LUT=8899838268388796601
PRIVATE_MASK=0xf56c000000000001
PRIVATE_MATERIAL=0xf56c000000000002
PRIVATE_EMPTY_DECAL=0xf56c000000000003
SCARF_SLOTS={0xf56a0001,0xf56a0002}


def u32(b,p):return struct.unpack_from('<I',b,p)[0]
def u64(b,p):return struct.unpack_from('<Q',b,p)[0]
def put32(b,p,v):struct.pack_into('<I',b,p,v)
def put64(b,p,v):struct.pack_into('<Q',b,p,v)
def sha(b):return hashlib.sha256(b).hexdigest()

def entries(toc):
    nt,n=struct.unpack_from('<II',toc,4);start=72+nt*32
    return {(u64(toc,start+80*i),u64(toc,start+80*i+8)):start+80*i for i in range(n)}
def blob(toc,h):return bytes(toc[u64(toc,h+16):u64(toc,h+16)+u32(toc,h+56)])
def gpu_blob(toc,gpu,h):return bytes(gpu[u64(toc,h+32):u64(toc,h+32)+u32(toc,h+64)])

def material_data(b):
    nt,nv=u32(b,64),u32(b,104);base=136+12*nt+20*nv
    tex={u32(b,136+4*i):136+4*nt+8*i for i in range(nt)};variables={}
    for i in range(nv):
        p=136+12*nt+20*i;cls,n,ident,off,stride=struct.unpack_from('<5I',b,p)
        if cls>3 or n!=0 or stride!=0:raise ValueError('围巾材质变量结构已变化。')
        variables[ident]=(cls,base+off,4*(cls+1))
    return tex,variables

def private_material(base,scarf):
    # The torso shader is the same general armor-LUT parent used by the SDK's
    # armorlut template, which supports expanded mask arrays / LUT stacks.
    if u64(base,24)!=0xf5ebd93181fdf00c:raise ValueError('通用护甲 LUT 材质父项已变化。')
    result=bytearray(base);bt,bv=material_data(base);st,sv=material_data(scarf)
    if len(bt)!=13 or len(st)!=12 or not set(st)<=set(bt):
        raise ValueError('胸甲和围巾材质贴图槽已变化。')
    for usage,offset in st.items():put64(result,bt[usage],u64(scarf,offset))
    for ident,(cls,offset,size) in sv.items():
        if ident not in bv or bv[ident][0]!=cls:raise ValueError('围巾变量无法对应通用材质。')
        result[bv[ident][1]:bv[ident][1]+size]=scarf[offset:offset+size]
    put64(result,bt[0x7e662968],TARGET_LUT)
    put64(result,bt[0xb281e5f2],PRIVATE_MASK)
    # The general torso parent has a DecalSheet slot absent from the original
    # scarf. Bind an entirely transparent sheet for this private scarf material.
    put64(result,bt[0x632a8b80],PRIVATE_EMPTY_DECAL)
    # Verified runtime pattern binding of the PH-56 accessory and B-01 torso.
    put64(result,bt[0x81d4c49d],17405844890543665857)
    return bytes(result)

def check_lut(toc_header,pixels):
    if len(toc_header)!=340 or toc_header[192:196]!=b'DDS ':raise ValueError('颜色表 DDS 结构异常。')
    if (u32(toc_header,208),u32(toc_header,204),u32(toc_header,320),u32(toc_header,332))!=(23,8,10,1):
        raise ValueError('颜色表格式已变化。')
    if len(pixels)!=1928:raise ValueError('颜色表数据长度已变化。')

def restore_scarf_colors(candidate,gpu,stream,source_toc,source_gpu,target_toc,target_gpu=None):
    current=entries(candidate);source=entries(source_toc);target=entries(target_toc)
    for key in ((PRIVATE_MASK,TEXTURE),(PRIVATE_MATERIAL,MATERIAL),(PRIVATE_EMPTY_DECAL,TEXTURE)):
        if key in current:raise ValueError('围巾专用资源编号已经存在。')
    scarf_lut_h=source[SCARF_LUT,TEXTURE];scarf_lut_toc=blob(source_toc,scarf_lut_h)
    scarf_colors=gpu_blob(source_toc,source_gpu,scarf_lut_h);check_lut(scarf_lut_toc,scarf_colors)
    if (TARGET_LUT,TEXTURE) in current:
        h=current[TARGET_LUT,TEXTURE];body_toc=blob(candidate,h);body_colors=gpu_blob(candidate,gpu,h)
        palette_header=bytearray(candidate[h:h+80]);has_palette=True
    else:
        if target_gpu is None:raise ValueError('B-01 原配色模式需要原始颜色资源。')
        h=target[TARGET_LUT,TEXTURE];body_toc=blob(target_toc,h);body_colors=gpu_blob(target_toc,target_gpu,h)
        palette_header=bytearray(target_toc[h:h+80]);has_palette=False
    check_lut(body_toc,body_colors)
    # Keep the original first eight rows, and the entire original scarf LUT.
    # The LUT is data sampled at level zero; a single unfiltered mip prevents
    # interpolation of unrelated material parameters between atlas rows.
    atlas_toc=bytearray(body_toc);put32(atlas_toc,204,16);put32(atlas_toc,220,1)
    put32(atlas_toc,200,u32(atlas_toc,200)&~0x20000)
    put32(atlas_toc,300,u32(atlas_toc,300)&~(0x400000|0x8))
    atlas_pixels=body_colors[:1472]+scarf_colors[:1472]
    mask_h=source[SCARF_MASK,TEXTURE];mask_toc=bytearray(blob(source_toc,mask_h))
    mask_pixels=gpu_blob(source_toc,source_gpu,mask_h)
    if len(mask_toc)!=340 or (u32(mask_toc,208),u32(mask_toc,204),u32(mask_toc,320),u32(mask_toc,332),u32(mask_toc,220))!=(256,256,28,1,9):
        raise ValueError('围巾的 RGBA 材质蒙版结构已变化。')
    if len(mask_pixels)!=349524 or u32(source_toc,mask_h+60)!=0:
        raise ValueError('围巾蒙版数据长度已变化。')
    # A native 256x256 RGBA texture with all nine mip levels avoids the 1x1
    # placeholder issue. It is private to the scarf, preserving torso decals.
    empty_decal_toc=bytes(mask_toc)
    empty_decal_pixels=bytes(len(mask_pixels))
    put32(mask_toc,332,4)
    # Four RGBA array slices = 16 mask channels. The scarf's four original
    # channels move from rows 0..3 to 8..11; all other channels remain empty.
    mask_atlas=bytes(len(mask_pixels)*2)+mask_pixels+bytes(len(mask_pixels))
    mat_h=source[TORSO_MATERIAL,MATERIAL];sc_h=source[SCARF_MATERIAL,MATERIAL]
    mat=private_material(blob(source_toc,mat_h),blob(source_toc,sc_h))
    changed=bytearray(candidate);bound=[]
    for (fid,typ),h in current.items():
        if typ!=UNIT:continue
        offset=u64(changed,h+16);size=u32(changed,h+56);unit=bytearray(changed[offset:offset+size])
        mp=u32(unit,0x70);n=u32(unit,mp);slots=[u32(unit,mp+4+4*i) for i in range(n)]
        found=SCARF_SLOTS&set(slots)
        if not found:continue
        if found!=SCARF_SLOTS:raise ValueError('合并围巾的材质槽不完整。')
        for i,slot in enumerate(slots):
            if slot in SCARF_SLOTS:put64(unit,mp+4+4*n+8*i,PRIVATE_MATERIAL)
        changed[offset:offset+size]=unit;bound.append(str(fid))
    if len(bound)!=6:raise ValueError('没有找到六个合并围巾的胸甲资源。')
    mask_header=bytearray(source_toc[mask_h:mask_h+80]);put64(mask_header,0,PRIVATE_MASK)
    material_header=bytearray(source_toc[mat_h:mat_h+80]);put64(material_header,0,PRIVATE_MATERIAL)
    empty_decal_header=bytearray(source_toc[mask_h:mask_h+80]);put64(empty_decal_header,0,PRIVATE_EMPTY_DECAL)
    additions=[(mask_header,bytes(mask_toc),mask_atlas),(material_header,mat,b''),(empty_decal_header,empty_decal_toc,empty_decal_pixels)]
    if not has_palette:additions.append((palette_header,bytes(atlas_toc),atlas_pixels))
    nt,n=struct.unpack_from('<II',changed,4);delta=80*len(additions);old_start=72+nt*32+n*80
    data=bytearray();gpu=bytearray(gpu);groups={}
    def append_resource(header,body,pixels):
        put64(header,16,len(changed)+delta+len(data));put32(header,56,len(body))
        put64(header,24,len(stream));put32(header,60,0)
        if pixels:
            gpu.extend(bytes((-len(gpu))%64));put64(header,32,len(gpu));put32(header,64,len(pixels));gpu.extend(pixels)
        data.extend(body)
        return header
    for (fid,typ),h in current.items():
        header=bytearray(changed[h:h+80])
        if (fid,typ)==(TARGET_LUT,TEXTURE):
            header=append_resource(header,bytes(atlas_toc),atlas_pixels)
        else:put64(header,16,u64(header,16)+delta)
        groups.setdefault(typ,[]).append(header)
    for header,body,pixels in additions:
        groups[u64(header,8)].append(append_resource(header,body,pixels))
    head=bytearray(changed[:72]);put32(head,8,n+len(additions));types=bytearray();ordered=[]
    for i in range(nt):
        header=bytearray(changed[72+32*i:104+32*i]);typ=u64(header,8)
        put64(header,16,len(groups[typ]));types.extend(header);ordered.extend(groups[typ])
    for i,header in enumerate(ordered,1):put32(header,76,i)
    result=bytes(head+types+b''.join(ordered)+changed[old_start:]+data)
    proof={'method':'shared primary LUT atlas and shifted independent RGBA ID masks',
           'body_rows':[0,7],'scarf_rows':[8,15],'active_scarf_mask_rows':[8,11],
           'primary_lut':str(TARGET_LUT),'primary_lut_dimensions':[23,16],
           'mask_id':str(PRIVATE_MASK),'material_id':str(PRIVATE_MATERIAL),
           'mask_dimensions':[256,256,4],'bound_torso_ids':sorted(bound),
           'original_scarf_color_rows_sha256':sha(scarf_colors[:1472]),
           'output_scarf_color_rows_sha256':sha(atlas_pixels[1472:]),
           'original_body_color_rows_sha256':sha(body_colors[:1472]),
           'output_body_color_rows_sha256':sha(atlas_pixels[:1472]),
           'original_scarf_mask_sha256':sha(mask_pixels),'original_scarf_variable_count':30,
           'private_material_parent':'f5ebd93181fdf00c',
           'scarf_decal_disabled':True,'empty_decal_texture':str(PRIVATE_EMPTY_DECAL),
           'empty_decal_dimensions':[256,256,1],'empty_decal_mips':9,
           'empty_decal_rgba_sha256':sha(empty_decal_pixels),
           'game_tested':False}
    return result,bytes(gpu),proof
