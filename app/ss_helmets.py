"""Freeze the three native SS helmets' adaptive LUTs at their default colors.

Only the twelve environment texture IDs are overridden. Helmet models, armor
palettes and gameplay records are never added to or rewritten by this profile.
"""
from pathlib import Path
import hashlib,json
import hd2_legacy as core
from universal_resources import u32,u64,put32,put64,package_slice
from adaptive_palettes import compile_toc

ROOT=Path(__file__).resolve().parent
PATCH='9ba626afa44a3aa3.patch_0'


def freeze(files,data,enabled=False):
    proof={'enabled':bool(enabled),'helmet_models_modified':0,'game_tested':False,'helmets':[],'texture_overrides':0}
    if not enabled:return files,proof
    catalog=json.loads((ROOT/'ss_helmets_catalog.json').read_text(encoding='utf8'))
    if len(catalog['helmets'])!=3:raise ValueError('SS helmet catalog must contain exactly three helmets.')
    protected={int(x) for x in catalog['protected_palette_ids']}
    allowed={int(v['material_lut']) for h in catalog['helmets'] for p in h['pieces'] for v in p['camouflage']}
    if len(allowed)!=12 or allowed & protected:
        raise ValueError('SS helmet environment palettes overlap another protected palette.')
    toc=files[PATCH];gpu=bytearray(files[PATCH+'.gpu_resources']);stream=files[PATCH+'.stream']
    entries=core.parse(toc,gpu,stream)
    resources={(e['id'],e['type']):(toc[e['header']:e['header']+80],toc[e['offset']:e['offset']+e['size']]) for e in entries}
    original_keys=set(resources);bundles=core.Bundles(data)
    for helmet in catalog['helmets']:
        native=bundles.load(helmet['archive']);native_entries=core.parse(native)
        index={(e['id'],e['type']):e for e in native_entries}
        if {e['id'] for e in native_entries if e['type']==core.UNIT}!={int(p['unit']) for p in helmet['pieces']}:
            raise ValueError('The SS helmet model catalog differs from this game installation.')
        rows=[]
        for piece in helmet['pieces']:
            if piece['slot']!=0 or piece['body']!=3:raise ValueError('Unexpected non-helmet piece in SS helmet profile.')
            default=int(piece['material_lut']);entry=index.get((default,core.TEXTURE))
            if entry is None:raise ValueError('Missing native SS helmet default palette.')
            head=native[entry['header']:entry['header']+80];raw=native[entry['offset']:entry['offset']+entry['size']]
            if (len(raw),raw[192:196],u32(raw,208),u32(raw,204),u32(raw,320),u32(head,60),u32(head,64))!=(340,b'DDS ',23,8,10,0,1928):
                raise ValueError('The native SS helmet default palette format has changed.')
            pixels=package_slice(bundles,helmet['archive']+'.gpu_resources',u64(head,32),1928)
            variants=piece['camouflage']
            if {v['type'] for v in variants}!={2,3,4,5} or len(variants)!=4:
                raise ValueError('SS helmet must contain all four native environment palettes.')
            for variant in variants:
                fid=int(variant['material_lut']);alt=index.get((fid,core.TEXTURE))
                if alt is None:raise ValueError('Missing native SS helmet environment palette.')
                alt_raw=native[alt['offset']:alt['offset']+alt['size']]
                if len(alt_raw)!=340 or (u32(alt_raw,208),u32(alt_raw,204),u32(alt_raw,320))!=(23,8,10):
                    raise ValueError('The native SS helmet environment palette format has changed.')
                h=bytearray(head);put64(h,0,fid);put64(h,24,len(stream));put32(h,60,0)
                gpu.extend(bytes((-len(gpu))%64));put64(h,32,len(gpu));gpu.extend(pixels)
                resources[fid,core.TEXTURE]=(h,raw)
                rows.append({'type':variant['type'],'target_lut':str(fid),'default_lut':str(default),
                             'pixels_sha256':hashlib.sha256(pixels).hexdigest(),
                             'header_sha256':hashlib.sha256(raw).hexdigest()})
        proof['helmets'].append({'name':helmet['name'],'archive':helmet['archive'],'variants':rows})
    if set(resources)-original_keys!={(fid,core.TEXTURE) for fid in allowed if (fid,core.TEXTURE) not in original_keys}:
        raise ValueError('SS helmet profile added an unexpected resource.')
    result=compile_toc(toc,resources,gpu,stream)
    proof['texture_overrides']=len(allowed)
    return {PATCH:result,PATCH+'.gpu_resources':bytes(gpu),PATCH+'.stream':stream},proof
