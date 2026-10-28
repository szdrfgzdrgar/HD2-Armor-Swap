"""Archive resources and per-material color atlases for universal armor swaps."""
from pathlib import Path
import struct,hashlib,math
import hd2_legacy as core
from hd2_scarf_colors import material_data,u32,u64,put32,put64

UNIT=core.UNIT;TEXTURE=core.TEXTURE;MATERIAL=0xeac0b497876adedf

def package_slice(b,name,start,size):
    total,segments=b.packages[name]
    if start<0 or size<0 or start+size>total:raise ValueError('游戏资源读取范围无效。')
    out=bytearray()
    for i,(logical,physical,bundle) in enumerate(segments):
        end=segments[i+1][0] if i+1<len(segments) else total
        left=max(start,logical);right=min(start+size,end)
        if right>left:out.extend(b.read_range(bundle,physical+left-logical,right-left))
    if len(out)!=size:raise ValueError('读取的资源长度不一致。')
    return bytes(out)

class Assets:
    def __init__(self,bundles,catalog,source,target,body,source_toc,source_gpu,source_stream,target_toc,target_gpu,keep_source=True):
        self.b=bundles;self.catalog=catalog;self.source=source;self.target=target;self.body=body;self.keep_source=keep_source
        self.toc=source_toc;self.original_gpu=source_gpu;self.gpu=bytearray(source_gpu);self.stream=source_stream;self.target_toc=target_toc;self.target_gpu=target_gpu
        self.index={(e['id'],e['type']):e for e in core.parse(source_toc,source_gpu,source_stream)}
        self.target_index={(e['id'],e['type']):e for e in core.parse(target_toc,target_gpu)}
        self.resources={};self.material_cache={};self.mask_cache={};self.palette_cache={};self.notes=[];self.palette_rows=[];self.palette_offsets={};self.private_keys=set()
        self.target_piece=None;self.atlas_id=None;self.template=None
        self.reference_tocs={source['archive']:source_toc,target['archive']:target_toc}
        for key,e in self.index.items():
            if key[1]!=UNIT:self.resources[key]=(bytearray(source_toc[e['header']:e['header']+80]),source_toc[e['offset']:e['offset']+e['size']])
    def private_id(self,label):
        raw=f"hd2-armors-0.8/{self.source['archive']}/{self.target['archive']}/{self.body}/{label}".encode()
        return int.from_bytes(hashlib.sha256(raw).digest()[:8],'little')
    def fresh_header(self,tid,fid):
        sample=next((e for e in self.index.values() if e['type']==tid),None)
        if sample:h=bytearray(self.toc[sample['header']:sample['header']+80])
        else:h=bytearray(80);put64(h,8,tid)
        put64(h,0,fid);put32(h,60,0);put32(h,64,0);put64(h,24,len(self.stream));put64(h,32,len(self.gpu))
        return h
    def add(self,tid,fid,data,pixels=None,header=None):
        h=bytearray(header) if header is not None else self.fresh_header(tid,fid);put64(h,0,fid);put64(h,8,tid);put32(h,56,len(data))
        if pixels is not None:
            self.gpu.extend(bytes((-len(self.gpu))%64));put64(h,32,len(self.gpu));put32(h,64,len(pixels));self.gpu.extend(pixels);put32(h,60,0);put64(h,24,len(self.stream))
        self.resources[fid,tid]=(h,bytes(data))
        return fid
    def source_blob(self,fid,tid):
        e=self.index.get((fid,tid))
        if e is None:return None
        return self.toc[e['offset']:e['offset']+e['size']]
    def external_texture(self,fid):
        # Missing shared palettes are resolved from kits that reference them;
        # only the small matching GPU slice is read from the bundle.
        for kit in self.catalog['armors']:
            if not any(int(p['material_lut'])==fid for p in kit['pieces']):continue
            a=kit['archive']
            if a not in self.reference_tocs:self.reference_tocs[a]=self.b.load(a)
            toc=self.reference_tocs[a];e=next((e for e in core.parse(toc) if e['id']==fid and e['type']==TEXTURE),None)
            if e is None:continue
            h=e['header'];pixels=package_slice(self.b,a+'.gpu_resources',u64(toc,h+32),u32(toc,h+64))
            return toc[e['offset']:e['offset']+e['size']],pixels
        raise ValueError('找不到共用主颜色表：'+str(fid))
    def palette(self,fid,target=False):
        key=(fid,target)
        if key in self.palette_cache:return self.palette_cache[key]
        toc=self.target_toc if target else self.toc;gpu=self.target_gpu if target else self.original_gpu;index=self.target_index if target else self.index
        e=index.get((fid,TEXTURE))
        if e is None:header,pixels=self.external_texture(fid)
        else:
            h=e['header'];header=toc[e['offset']:e['offset']+e['size']];pixels=gpu[u64(toc,h+32):u64(toc,h+32)+u32(toc,h+64)]
        w,h,fmt=u32(header,208),u32(header,204),u32(header,320)
        if (w,fmt)!=(23,10) or not 1<=h<=8 or len(pixels)<23*h*8:raise ValueError('主颜色表不是已识别的 23 列浮点格式。')
        if not target and getattr(self,'remove_yellow',False) and fid in (4398586474736961156,14000038807789650907):
            pixels,_=core.recolor_yellow_trim(pixels,fid)
        rows=[pixels[y*184:(y+1)*184] for y in range(h)]
        rows.extend([rows[-1]]*(8-h));result=(header,rows)
        self.palette_cache[key]=result
        return result
    def initialize_atlas(self,target_piece):
        self.target_piece=target_piece;fid=int(target_piece['material_lut'])
        self.atlas_id=fid or self.private_id('palette-atlas')
        if fid:header,rows=self.palette(fid,True)
        else:
            fid=next((int(p['material_lut']) for p in self.source['pieces'] if int(p['material_lut']) and p['slot']>=2),None)
            if fid is None:
                fid=next(e['id'] for e in self.index.values() if e['type']==TEXTURE and u32(self.toc,e['offset']+208)==23 and u32(self.toc,e['offset']+320)==10)
            header,rows=self.palette(fid)
        self.template=bytearray(header);self.palette_rows.extend(rows)
        # These first 8 rows are kept byte-identical to the target palette so
        # helmets sharing that palette retain their original color values.
        self.original_target_rows_sha256=hashlib.sha256(b''.join(rows)).hexdigest()
    def palette_offset(self,part,default):
        source_fid=int(part['piece']['material_lut']) or default;target_mode=False;chosen=source_fid
        if not self.keep_source and part['piece']['piece']!=2:
            candidates=[p for p in self.target['pieces'] if p['body'] in (self.body,3) and p['slot']==part['piece']['slot'] and p['piece']==part['piece']['piece'] and int(p['material_lut'])]
            chosen=int((candidates[0] if candidates else self.target_piece)['material_lut']) or source_fid;target_mode=bool(chosen!=source_fid or candidates)
        key=(chosen,target_mode)
        if key not in self.palette_offsets:
            _,rows=self.palette(chosen,target_mode);self.palette_offsets[key]=len(self.palette_rows);self.palette_rows.extend(rows)
        return self.palette_offsets[key]
    def shifted_mask(self,fid,row_offset):
        key=(fid,row_offset)
        if key in self.mask_cache:return self.mask_cache[key]
        e=self.index.get((fid,TEXTURE))
        if e is None:raise ValueError('来源盔甲缺少材质蒙版：'+str(fid))
        h=e['header'];toc=bytearray(self.toc[e['offset']:e['offset']+e['size']]);w,ht,fmt,arrays,mips=u32(toc,208),u32(toc,204),u32(toc,320),u32(toc,332),u32(toc,220)
        if fmt!=28 or row_offset%4:raise ValueError('尚未识别的材质蒙版格式。')
        plane=sum(max(1,w>>i)*max(1,ht>>i)*4 for i in range(mips));expected=plane*arrays
        pixels=self.original_gpu[u64(self.toc,h+32):u64(self.toc,h+32)+u32(self.toc,h+64)]
        if len(pixels)!=expected:
            s=self.stream[u64(self.toc,h+24):u64(self.toc,h+24)+u32(self.toc,h+60)]
            if len(s)==expected:pixels=s
            elif len(s)+len(pixels)==expected:pixels=s+pixels
            else:raise ValueError('分层材质蒙版的长度不匹配。')
        prefix=row_offset//4;put32(toc,332,prefix+arrays)
        # Convert any streaming wrapper to an entirely GPU-resident DDS.
        toc[:192]=bytes(192);put32(toc,8,0xffffffff)
        shifted=bytes(prefix*plane)+pixels;newid=self.private_id('mask/'+str(fid)+'/'+str(row_offset));self.add(TEXTURE,newid,toc,shifted)
        self.mask_cache[key]=newid
        return newid
    def material_for(self,part,mid,lod):
        raw=self.source_blob(mid,MATERIAL)
        if raw is None:
            if 'fallback_material' not in part:
                part['fallback_material']=next((m for s,m in part['materials'].items() if (m,MATERIAL) in self.index),None)
            mid=part['fallback_material']
            if mid is None:raise ValueError('来源部件没有可用的表面材质。')
            raw=self.source_blob(mid,MATERIAL)
            note='低细节共用材质使用该部件的原始表面材质：'+str(part['id'])
            if note not in self.notes:self.notes.append(note)
        n=u32(raw,64)
        if 0x7e662968 not in {u32(raw,136+4*i) for i in range(n)}:return mid
        tex,variables=material_data(raw)
        # Some native accessory materials reference a runtime/default mask that
        # is absent from all shipped archives. Keep that original binding rather
        # than guessing a mask or silently changing the accessory's appearance.
        mask_id=u64(raw,tex[0xb281e5f2]) if 0xb281e5f2 in tex else None
        if mask_id is None or (mask_id,TEXTURE) not in self.index:
            note='特殊附件保留原始材质绑定，未重排其配色（无可读取的原始蒙版）：'+str(part['id'])
            if note not in self.notes:self.notes.append(note)
            return mid
        offset=self.palette_offset(part,u64(raw,tex[0x7e662968]));pattern=int(part['piece']['pattern_lut'])
        key=(mid,offset,pattern)
        if key in self.material_cache:return self.material_cache[key]
        result=bytearray(raw);mask=self.shifted_mask(u64(raw,tex[0xb281e5f2]),offset)
        put64(result,tex[0x7e662968],self.atlas_id);put64(result,tex[0xb281e5f2],mask)
        if pattern and 0x81d4c49d in tex:put64(result,tex[0x81d4c49d],pattern)
        newid=self.private_id('material/'+str(mid)+'/'+str(offset)+'/'+str(pattern));self.add(MATERIAL,newid,result)
        self.material_cache[key]=newid
        return newid
    def finish_atlas(self):
        rows=len(self.palette_rows);height=1<<(rows-1).bit_length()
        pixels=b''.join(self.palette_rows+[bytes(184)]*(height-rows));toc=bytearray(self.template)
        toc[:192]=bytes(192);put32(toc,8,0xffffffff);put32(toc,204,height);put32(toc,220,1)
        put32(toc,200,u32(toc,200)&~0x20000);put32(toc,300,u32(toc,300)&~(0x400000|0x8))
        self.add(TEXTURE,self.atlas_id,toc,pixels)
        return {'id':str(self.atlas_id),'rows_used':rows,'height':height,'source_palettes':len(self.palette_offsets),'target_first_eight_rows_sha256':hashlib.sha256(pixels[:1472]).hexdigest(),'original_target_first_eight_rows_sha256':self.original_target_rows_sha256,'mask_count':len(self.mask_cache),'private_material_count':len(self.material_cache),
                'bindings':[{'lut':str(fid),'target':target,'row_offset':offset} for (fid,target),offset in self.palette_offsets.items()]}
    def unit_header(self,fid,source_e,gpu_offset=None,gpu_size=None):
        h=bytearray(self.toc[source_e['header']:source_e['header']+80]);put64(h,0,fid)
        if gpu_offset is not None:put64(h,32,gpu_offset);put32(h,64,gpu_size);put32(h,60,0);put64(h,24,len(self.stream))
        return h
    def compile(self):
        # Native type headers and resource payloads are preserved. Only the
        # explicitly added/replaced body resources enter this patch.
        groups={}
        for (fid,tid),(h,data) in self.resources.items():groups.setdefault(tid,[]).append((fid,bytearray(h),data))
        if set(groups)-{UNIT,TEXTURE,MATERIAL,0x18dead01056b72e9}:raise ValueError('来源档案包含尚未识别的非外观资源，停止生成。')
        original_types={u64(self.toc,72+i*32+8):self.toc[72+i*32:104+i*32] for i in range(u32(self.toc,4))}
        types=sorted(groups);count=sum(len(v) for v in groups.values());header=bytearray(self.toc[:72]);put32(header,4,len(types));put32(header,8,count)
        tt=bytearray();heads=[];payload=bytearray();start=72+32*len(types)+80*count
        for tid in types:
            th=bytearray(original_types.get(tid,bytes(32)));put64(th,8,tid);put64(th,16,len(groups[tid]));tt.extend(th)
            for fid,h,data in sorted(groups[tid],key=lambda x:x[0]):
                payload.extend(bytes((-(start+len(payload)))%16));put64(h,16,start+len(payload));put32(h,56,len(data));put32(h,76,len(heads)+1);payload.extend(data);heads.append(h)
        toc=bytes(header+tt+b''.join(heads)+payload);core.parse(toc,self.gpu,self.stream)
        return toc,bytes(self.gpu),self.stream
