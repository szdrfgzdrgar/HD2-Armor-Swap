"""Keep native adaptive targets' four alternate LUTs consistent with merged meshes.

This is an asset-only path. It deliberately does not claim to transfer a native
camouflage binding to a target kit that has no such binding.
"""
from pathlib import Path
import hashlib
import json
import struct
import hd2_legacy as core
from universal_resources import u32, u64, put32, put64

ROOT = Path(__file__).resolve().parent
PATCH = '9ba626afa44a3aa3.patch_0'
TYPES = {2:'forest',3:'desert',4:'arctic',5:'crimson'}


def metadata():
    return json.loads((ROOT/'adaptive_catalog.json').read_text(encoding='utf8'))


def adaptive_ids():
    return set(metadata()['armors'])


def status(source_id, target_id, keep_source):
    ids = adaptive_ids()
    if keep_source and source_id in ids:
        return 'native_variants' if target_id in ids else 'source_binding_unavailable'
    if not keep_source and target_id in ids:
        return 'native_variants'
    if target_id in ids:
        return 'fixed_source_colors'
    return 'fixed_colors'


def variants(kit, body):
    """LUT ID -> environment -> LUT ID; reject ambiguous catalog joins."""
    record = metadata()['armors'].get(kit['archive'])
    if not record:
        return {}
    native = {(p['body'],p['unit']):p for p in record['pieces']}
    result = {}
    for p in kit['pieces']:
        if p['body'] not in (body,3):
            continue
        n = native.get((p['body'],p['unit']))
        if n is None or (n['slot'],n['piece']) != (p['slot'],p['piece']):
            raise ValueError('Adaptive armor metadata differs from the body catalog.')
        entries = {int(c['type']):int(c['material_lut']) for c in n['camouflage']}
        if not entries:
            continue
        if set(entries) != set(TYPES):
            raise ValueError('Adaptive armor must have all four native camouflage variants.')
        fid = int(p['material_lut'])
        if not fid:
            raise ValueError('Adaptive piece has no default primary LUT.')
        if fid in result and result[fid] != entries:
            raise ValueError('Adaptive pieces disagree on a shared primary LUT.')
        result[fid] = entries
    return result


def read_rows(toc, gpu, index, fid):
    e = index.get((fid,core.TEXTURE))
    if not e:
        raise ValueError('Missing native adaptive LUT: '+str(fid))
    raw = toc[e['offset']:e['offset']+e['size']]
    if len(raw) != 340 or raw[192:196] != b'DDS ':
        raise ValueError('Unsupported native adaptive texture header.')
    height = u32(raw,204)
    if (u32(raw,208),u32(raw,320)) != (23,10) or not 1 <= height <= 8:
        raise ValueError('Unsupported native adaptive LUT dimensions or format.')
    at, size = u64(toc,e['header']+32),u32(toc,e['header']+64)
    pixels = gpu[at:at+size]
    if len(pixels) < height*184:
        raise ValueError('Native adaptive LUT pixels are truncated.')
    rows = [pixels[y*184:(y+1)*184] for y in range(height)]
    return b''.join(rows+[rows[-1]]*(8-height))


def compile_toc(original, resources, gpu, stream):
    types = {u64(original,72+i*32+8):original[72+i*32:104+i*32]
             for i in range(u32(original,4))}
    groups = {}
    for (fid,tid),(head,raw) in resources.items():
        groups.setdefault(tid,[]).append((fid,head,raw))
    if set(groups) != set(types):
        raise ValueError('Adaptive packaging changed the resource type set.')
    count = len(resources)
    header = bytearray(original[:72]); put32(header,8,count)
    start = 72+32*len(types)+80*count
    type_headers, heads, payload = bytearray(),[],bytearray()
    for tid in sorted(types):
        th = bytearray(types[tid]); put64(th,16,len(groups[tid])); type_headers.extend(th)
        for fid,head,raw in sorted(groups[tid],key=lambda x:x[0]):
            payload.extend(bytes((-(start+len(payload)))%16))
            head = bytearray(head); put64(head,16,start+len(payload)); put32(head,56,len(raw))
            put32(head,76,len(heads)+1); heads.append(head); payload.extend(raw)
    result = bytes(header+type_headers+b''.join(heads)+payload)
    core.parse(result,gpu,stream)
    return result


def preserve(files, report, data, source, target, body, keep_source, appearance_profile):
    state = status(source['archive'],target['archive'],keep_source)
    proof = {'status':state,'runtime_binding_transferred':False,'game_tested':False,
             'target_has_native_binding':target['archive'] in adaptive_ids(),
             'variants':[],'environment_types':TYPES,
             'visible_environment_variants':state == 'native_variants'}
    if target['archive'] not in adaptive_ids():
        return files,proof
    if not report.get('palette_atlas',{}).get('bindings'):
        raise ValueError('Adaptive packaging needs the merged palette row map.')
    toc, gpu, stream = files[PATCH],bytearray(files[PATCH+'.gpu_resources']),files[PATCH+'.stream']
    entries = core.parse(toc,gpu,stream)
    index = {(e['id'],e['type']):e for e in entries}
    resources = {(e['id'],e['type']):(toc[e['header']:e['header']+80],toc[e['offset']:e['offset']+e['size']]) for e in entries}
    atlas_id = int(report['palette_atlas']['id']); ae = index[atlas_id,core.TEXTURE]
    head = toc[ae['header']:ae['header']+80]; raw = toc[ae['offset']:ae['offset']+ae['size']]
    start, size = u64(head,32),u32(head,64); baseline = bytes(gpu[start:start+size])
    if u32(raw,204) != report['palette_atlas']['height'] or len(baseline) != u32(raw,204)*184:
        raise ValueError('Expanded palette dimensions do not agree with the row map.')
    bundles = core.Bundles(data)
    archives = {}
    maps = {False:variants(source,body),True:variants(target,body)}
    for owner,kit in ((False,source),(True,target)):
        if maps[owner]:
            atoc = bundles.load(kit['archive']); agpu = bundles.load(kit['archive']+'.gpu_resources')
            archives[owner] = (atoc,agpu,{(e['id'],e['type']):e for e in core.parse(atoc,agpu)})
    carrier = next(p for p in target['pieces'] if p['unit'] == report['carrier_unit'] and p['body'] in (body,3))
    carrier_variants = maps[True].get(int(carrier['material_lut']))
    if not carrier_variants:
        raise ValueError('The target carrier does not have a native adaptive binding.')
    torso = next((p for p in source['pieces'] if p['slot']==2 and p['piece']==0 and p['body'] in (body,3)),None)
    for env in sorted(TYPES):
        fid = carrier_variants[env]
        target_first_rows = read_rows(*archives[True],fid)
        pixels = bytearray(baseline); pixels[:1472] = target_first_rows
        mapped = []
        for block in report['palette_atlas']['bindings']:
            owner, original_lut, offset = block['target'],int(block['lut']),block['row_offset']*184
            alternate = maps[owner].get(original_lut,{}).get(env)
            if alternate is None:
                continue
            if offset < 1472 or offset+1472 > len(pixels):
                raise ValueError('Adaptive palette block is outside the expanded atlas.')
            rows = read_rows(*archives[owner],alternate)
            pixels[offset:offset+1472] = rows
            mapped.append({'default_lut':str(original_lut),'variant_lut':str(alternate),
                           'row_offset':block['row_offset'],'rows_sha256':hashlib.sha256(rows).hexdigest()})
        if appearance_profile.get('collar_native_mask'):
            binding = appearance_profile['collar_palette_binding']
            owner = binding['target']
            alternate = maps[owner].get(int(binding['lut']),{}).get(env)
            if alternate is None:
                raise ValueError('Native SS-33 collar requires an adaptive torso palette.')
            pixels[:1472] = read_rows(*archives[owner],alternate)
        helmets = set(metadata()['helmet_alternate_luts'])
        if str(fid) in helmets and bytes(pixels[:1472]) != target_first_rows:
            raise ValueError('Adaptive LUT would change a shared helmet palette.')
        h = bytearray(head); put64(h,0,fid)
        gpu.extend(bytes((-len(gpu))%64)); put64(h,32,len(gpu)); put32(h,64,len(pixels)); gpu.extend(pixels)
        resources[fid,core.TEXTURE] = (h,raw)
        proof['variants'].append({'type':env,'name':TYPES[env],'target_lut':str(fid),
                                  'height':u32(raw,204),'blocks':mapped,
                                  'pixels_sha256':hashlib.sha256(pixels).hexdigest(),
                                  'native_target_first_rows_preserved':bytes(pixels[:1472]) == target_first_rows})
    proof['default_atlas_preserved'] = hashlib.sha256(baseline).hexdigest()
    result = compile_toc(toc,resources,gpu,stream)
    return {PATCH:result,PATCH+'.gpu_resources':bytes(gpu),PATCH+'.stream':stream},proof
