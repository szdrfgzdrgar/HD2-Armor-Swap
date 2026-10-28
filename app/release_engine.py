"""Version 1.0 release packaging around the validated native armor builders."""
from pathlib import Path
import ctypes, hashlib, json, os, re, shutil, struct, tempfile, uuid, zipfile
import swap_backend as backend
import hd2_legacy as core
from hd2_scarf import meshes, materials
from hd2_scarf_colors import material_data
from universal_geometry import validate_lod_links, lod_index_locations
from universal_resources import u32, u64, put32, put64
import adaptive_palettes
import ss_helmets

VERSION = '1.2.0'
ROOT = Path(__file__).resolve().parent
CREDIT = '该免费软件由B站Mr-Foxington/chatgpt制作'
SS33 = '3ab4af712c5ec0df'
RS89 = '85d392768bf6a259'
GORE = 12070197922454493211
PATCH = '9ba626afa44a3aa3.patch_0'


class UserError(Exception):
    def __init__(self, code, detail=''):
        self.code, self.detail = code, detail
        super().__init__(detail or code)


def desktop_directory():
    if os.name == 'nt':
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    for candidate in [Path(os.environ.get('OneDrive', str(Path.home()))) / 'Desktop', Path.home() / 'Desktop']:
        if candidate.is_dir():
            return candidate
    return Path.home()


def catalog():
    return backend.load_catalog()


def safe_name(value, limit=130):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value)
    value = re.sub(r'\s+', ' ', value).strip(' .')
    return value[:limit].rstrip(' .') or 'ArmorSwap'


def armor_name(kit, lang='zh'):
    name = kit['name_zh'] if lang == 'zh' else kit['name']
    if kit.get('variant'):
        name += (' 变体 ' if lang == 'zh' else ' Variant ') + str(kit['variant'])
    return name


def output_name(source, target, body, lang='zh', keep_source=True, remove_yellow=False, freeze_ss_helmets=False):
    if lang == 'zh':
        name = f"穿戴{armor_name(target,lang)}_显示{armor_name(source,lang)}_{'壮硕' if body == 0 else '苗条'}"
        if not keep_source: name += '_目标配色'
        if remove_yellow and keep_source and source['archive'] == core.SOURCE: name += '_去黄边'
    else:
        name = f"Wear_{armor_name(target,lang)}__Look_{armor_name(source,lang)}__{'Stocky' if body == 0 else 'Slim'}"
        if not keep_source: name += '__TargetColors'
        if remove_yellow and keep_source and source['archive'] == core.SOURCE: name += '__NoYellowTrim'
    if adaptive_palettes.status(source['archive'],target['archive'],keep_source) == 'source_binding_unavailable':
        name += '_固定配色' if lang == 'zh' else '__FixedColors'
    if freeze_ss_helmets:
        name += '_SS头盔固定配色' if lang == 'zh' else '__FixedSSHelmets'
    return safe_name(name) + '.zip'


def next_available(folder, name):
    p = folder / name
    for i in range(2, 10000):
        if not p.exists(): return p
        p = folder / f'{Path(name).stem} ({i}){Path(name).suffix}'
    raise UserError('too_many_outputs')


def apply_profiles(files, report, data, source, target, body, keep_source, hide_caps, leaf_compat):
    toc = bytearray(files[PATCH]); gpu = bytearray(files[PATCH + '.gpu_resources']); stream = files[PATCH + '.stream']
    original_toc = bytes(toc); original_gpu = bytes(gpu)
    entries = core.parse(toc, gpu, stream)
    index = {(e['id'], e['type']): e for e in entries}
    proof = {'hidden_wound_sections': 0, 'collar_native_mask': False, 'leaf_high_detail': False, 'notes': []}
    carrier_entry = next((e for e in entries if e['type'] == core.UNIT and str(e['id']) == report.get('carrier_unit')), None)
    original_carrier = None
    if carrier_entry:
        e = carrier_entry; original_carrier = bytes(toc[e['offset']:e['offset']+e['size']])
    if hide_caps:
        for e in entries:
            if e['type'] != core.UNIT: continue
            raw = bytearray(toc[e['offset']:e['offset']+e['size']]); binding = dict(materials(raw))
            table = u32(raw, 0x64)
            for i, mesh in enumerate(meshes(raw)):
                at = table + u32(raw, table + 4 + 4*i)
                for j, sec in enumerate(mesh['sections']):
                    if sec[4] and binding.get(mesh['materials'][sec[0]]) == GORE:
                        put32(raw, at + u32(raw, at+124) + 24*j + 16, 0)
                        proof['hidden_wound_sections'] += 1
            toc[e['offset']:e['offset']+e['size']] = raw
    if source['archive'] == SS33 and leaf_compat and carrier_entry:
        atlas = int(report['palette_atlas']['id'])
        if atlas in {int(x) for x in catalog()['helmet_lut_ids']}:
            proof['notes'].append('leaf_profile_skipped_shared_helmet_palette')
        else:
            bundles = core.Bundles(data); st = bundles.load(source['archive']); sg = bundles.load(source['archive']+'.gpu_resources')
            si = {(e['id'],e['type']):e for e in core.parse(st)}
            torso = next(p for p in backend.selected(source,body).values() if p['slot'] == 2 and p['piece'] == 0)
            source_lut = int(torso['material_lut']); su = si[int(torso['unit']),core.UNIT]
            native_unit = st[su['offset']:su['offset']+su['size']]
            native = []
            for _, mid in materials(native_unit):
                me = si.get((mid,0xeac0b497876adedf))
                if not me: continue
                raw = st[me['offset']:me['offset']+me['size']]; tx,_ = material_data(raw)
                if 0x7e662968 in tx and u64(raw,tx[0x7e662968]) == source_lut:
                    native.append((raw,tx))
            if len(native) != 1: raise UserError('leaf_profile_changed')
            raw, tx = native[0]; native_mask = u64(raw,tx[0xb281e5f2]); base_data = u64(raw,tx[0xc2eb8d6e]); changed = []
            for e in entries:
                if e['type'] != 0xeac0b497876adedf: continue
                material = toc[e['offset']:e['offset']+e['size']]; mt,_ = material_data(material)
                if (0x7e662968 in mt and u64(material,mt[0x7e662968]) == atlas and
                    0xc2eb8d6e in mt and u64(material,mt[0xc2eb8d6e]) == base_data):
                    put64(toc,e['offset']+mt[0xb281e5f2],native_mask); changed.append(str(e['id']))
            if len(changed) != 1 or (native_mask,core.TEXTURE) not in index: raise UserError('leaf_profile_changed')
            ae = index[atlas,core.TEXTURE]; go = u64(toc,ae['header']+32)
            chosen, target_mode = source_lut,False
            if not keep_source:
                candidates = [p for p in target['pieces'] if p['body'] in (body,3) and p['slot']==2 and p['piece']==0 and int(p['material_lut'])]
                carrier_piece = next(p for p in target['pieces'] if p['unit']==report['carrier_unit'] and p['body'] in (body,3))
                chosen = int((candidates[0] if candidates else carrier_piece)['material_lut']) or source_lut
                target_mode = bool(chosen != source_lut or candidates)
            block = next((b for b in report['palette_atlas']['bindings'] if int(b['lut'])==chosen and b['target']==target_mode),None)
            if block is None: raise UserError('leaf_profile_changed')
            palette_offset = go+block['row_offset']*184
            gpu[go:go+1472] = gpu[palette_offset:palette_offset+1472]
            proof.update(collar_native_mask=True, native_materials=changed,
                         source_palette=str(source_lut), native_mask=str(native_mask), helmet_palette_overlap=False,
                         collar_palette_binding=block)
            # Preserve the complete profile accepted in v0.8.5: the five foliage
            # parts use their highest detail meshes, while other parts retain LODs.
            group_keys = []
            for sec in report['geometry']['sections']:
                key = (sec['source_unit'],sec['lod'])
                if not group_keys or group_keys[-1] != key: group_keys.append(key)
            selected = backend.selected(source,body)
            foliage = set()
            for fid,p in selected.items():
                if p['piece'] != 0: continue
                ue = si[fid,core.UNIT]; ub = st[ue['offset']:ue['offset']+ue['size']]
                if any((mid,0xeac0b497876adedf) in si and u64(st,si[mid,0xeac0b497876adedf]['offset']+24) == 10267922236328122831 for _,mid in materials(ub)):
                    foliage.add(str(fid))
            raw = bytearray(toc[carrier_entry['offset']:carrier_entry['offset']+carrier_entry['size']])
            if len(group_keys) != len(meshes(raw)): raise UserError('leaf_profile_changed')
            high = {fid:i for i,(fid,lod) in enumerate(group_keys) if lod == 0 and fid in foliage}
            for p in lod_index_locations(raw):
                fid,lod = group_keys[u32(raw,p)]
                if fid in high: put32(raw,p,high[fid])
            toc[carrier_entry['offset']:carrier_entry['offset']+carrier_entry['size']] = raw
            proof.update(leaf_high_detail=True, leaf_parts=len(high))
    for e in entries:
        if e['type'] == core.UNIT: validate_lod_links(toc[e['offset']:e['offset']+e['size']])
    core.parse(toc,gpu,stream)
    # Validate that all emitted Unit IDs remain body-only.
    helmets = {int(x) for x in catalog()['excluded_helmet_unit_ids']}
    if any(e['type'] == core.UNIT and e['id'] in helmets for e in entries): raise UserError('helmet_guard')
    return {PATCH:bytes(toc),PATCH+'.gpu_resources':bytes(gpu),PATCH+'.stream':stream}, proof


def build_release(data, output, source_id, target_id, body=0, keep_source=True,
                  remove_yellow=True, hide_caps=True, leaf_compat=True, lang='zh', progress=None, freeze_ss_helmets=False):
    progress = progress or (lambda key, **kw:None)
    kits = {k['archive']:k for k in catalog()['armors']}
    if source_id not in kits or target_id not in kits: raise UserError('choose_armor')
    if source_id == target_id: raise UserError('same_armor')
    source,target = kits[source_id],kits[target_id]
    data,output = Path(data).resolve(),Path(output).resolve()
    if data == output or data in output.parents: raise UserError('output_in_game')
    progress('checking')
    # Only final ZIPs are written to the chosen destination. All intermediate
    # folders and legacy builder reports are scoped to a cleaned temporary dir.
    with tempfile.TemporaryDirectory(prefix='.HD2ArmorSwap_', dir=ROOT.parent) as staging:
        stages = [('检查','checking'),('读取','reading'),('整合','assembling'),('生成围巾','assembling'),('整理','finishing'),('检查已安装','finishing')]
        last = [None]
        def backend_log(message):
            for prefix,key in stages:
                if message.startswith(prefix) and last[0] != key:
                    last[0] = key; progress(key); break
        path, report = backend.build(data,staging,source_id,target_id,body,keep_source,remove_yellow,True,backend_log)
        with zipfile.ZipFile(path) as z:
            files = {PATCH+s:z.read('Experimental_Mod/'+PATCH+s) for s in ('','.gpu_resources','.stream')}
        if report.get('version') in ('0.7','0.6','0.5'):
            profile = {'verified_PH56_B01_engine':True,'appearance_bytes_preserved':True,'notes':[]}
        else:
            progress('profiles')
            files, profile = apply_profiles(files,report,data,source,target,body,keep_source,hide_caps,leaf_compat)
        files, adaptive = adaptive_palettes.preserve(files,report,data,source,target,body,keep_source,profile)
        files, helmets = ss_helmets.freeze(files,data,freeze_ss_helmets)
        report.update(release_version=VERSION, credit=CREDIT, release_profile=profile,
                      wearing_target=target['name'],displayed_appearance=source['name'],adaptive_camouflage=adaptive,
                      ss_helmet_colors=helmets,
                      automatic_fixes={'hide_wound_caps':hide_caps,'PH56_trim_when_applicable':remove_yellow,
                                       'SS33_foliage_when_applicable':leaf_compat},
                      replace_primary_color_tables=bool(keep_source))
        report['sha256'] = {n:hashlib.sha256(v).hexdigest() for n,v in files.items()}
        identity = f"hd2-armors/{source_id}/{target_id}/{body}/{report['sha256'][PATCH]}"
        title = f"Wear {target['name']} - Look {source['name']} ({'Stocky' if body == 0 else 'Slim'})"
        if freeze_ss_helmets:title += ' + Fixed SS helmets'
        helmet_note = ('SS-33、SS-15、SS-500 头盔已固定为各自默认配色。 / SS-33, SS-15 and SS-500 helmets use their own fixed default colors.'
                       if freeze_ss_helmets else '未启用 SS 头盔固定配色。 / SS helmet color freeze is disabled.')
        manifest = {'Version':1,'Guid':str(uuid.uuid5(uuid.NAMESPACE_URL,identity)),'Name':title[:120],
                    'Description':f"穿戴 {target['name_zh']}，显示 {source['name_zh']} 外观。仅{'壮硕' if body == 0 else '苗条'}体型，头盔模型不替换。{helmet_note} {CREDIT}"}
        adaptive_note = {
            'native_variants':'保留穿戴目标的原生环境切换；四组颜色表已输出，尚需游戏内验证。 / Native target switching retained; four LUT variants packaged; in-game verification pending.',
            'source_binding_unavailable':'此包是固定配色：来源的环境变色尚未迁移到普通穿戴目标。 / FIXED COLORS: source adaptive binding is NOT transferred to this non-adaptive target.',
            'fixed_source_colors':'使用来源固定配色；穿戴目标保留原生切换入口，但所选来源没有环境配色。 / Fixed source colors selected; source has no environmental color variants.',
            'fixed_colors':'固定配色组合。 / Fixed-color combination.'
        }[adaptive['status']]
        guide = f'''HD2 Armor Swap {VERSION}
{CREDIT}

SS 头盔配色 / SS helmet colors:
{helmet_note}
启用时仅覆盖三款头盔的 12 份环境颜色表，不替换头盔模型，不改动盔甲颜色表。
When enabled, only the twelve helmet environment LUTs are frozen; helmet models and armor LUTs are preserved.
恢复原生头盔变色：停用旧包，取消勾选后重新生成、导入并部署。
To restore native helmet color changes, disable the old package and generate/import/deploy a new one with the option unchecked.

环境变色 / Adaptive camouflage:
{adaptive_note}

穿戴目标 / Wear: {armor_name(target,'zh')} / {armor_name(target,'en')}
显示外观 / Look: {armor_name(source,'zh')} / {armor_name(source,'en')}
体型 / Body: {'壮硕 / Stocky' if body == 0 else '苗条 / Slim'}

关闭游戏，在 Arsenal 中停用旧的同目标护甲替换包，再直接导入本 ZIP。
Close the game, disable previous replacements for the same armor in Arsenal,
then import this ZIP directly. Enable one replacement for the target at a time.

程序没有自动安装 Mod，也没有修改盔甲属性、被动或头盔模型。
The app does not install mods automatically or edit stats, passives or helmet models.
部件/配色表被其他盔甲共用时可能同时影响它们，详见 diagnostic_report.json。
Shared body resources may affect other armor. See diagnostic_report.json.
SS-33 方案沿用已确认的领口/胸前原版蒙版修正；其他特效部件以游戏实际效果为准。
The SS-33 profile preserves the accepted collar/torso mask fix; other special effects require in-game checks.
其叶片保留最高细节；去红斑选项隐藏伤口断面，可能影响该外观的受伤显示。
Foliage uses highest detail in this profile; hiding wound caps can affect dismemberment visuals.
不是所有护甲组合均已完成游戏内验证。Not every combination has been tested in game.
'''
        output.mkdir(parents=True,exist_ok=True)
        name = output_name(source,target,body,lang,keep_source,remove_yellow,freeze_ss_helmets)
        progress('packing')
        # Exclusive file creation prevents overwriting an existing generated mod.
        for attempt in range(1,10000):
            result = next_available(output,name)
            try:
                with result.open('xb') as f:
                    with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf8'))
                        for n,raw in files.items(): z.writestr(n,raw)
                        z.writestr('README.txt',guide.encode('utf-8-sig'))
                        z.writestr('diagnostic_report.json',json.dumps(report,ensure_ascii=False,indent=2).encode('utf8'))
                break
            except FileExistsError: continue
            except Exception:
                result.unlink(missing_ok=True); raise
        else: raise UserError('too_many_outputs')
        try:
            with zipfile.ZipFile(result) as z:
                if z.testzip() is not None: raise UserError('bad_zip')
                for n,h in report['sha256'].items():
                    if hashlib.sha256(z.read(n)).hexdigest() != h: raise UserError('bad_zip')
        except Exception:
            result.unlink(missing_ok=True); raise
    progress('done',path=str(result))
    return result,report
