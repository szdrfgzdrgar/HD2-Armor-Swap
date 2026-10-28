from pathlib import Path
import json,sys,struct,hashlib,zipfile,uuid,re
from datetime import datetime
import hd2_legacy as core
from universal_resources import Assets,UNIT,TEXTURE,MATERIAL,u32,u64,put32,put64
from universal_geometry import assemble,hidden_unit,validate_lod_links

ROOT=Path(__file__).resolve().parent
DEFAULT_DATA=r'D:\SteamLibrary\steamapps\common\Helldivers 2\data'

def load_catalog():
    data=json.loads((ROOT/'armor_catalog.json').read_text(encoding='utf8'))
    if any(any(p['slot']<2 for p in k['pieces']) for k in data['armors']):raise ValueError('盔甲目录中混入了头盔或披肩。')
    return data

def selected(kit,body):
    result={}
    for p in kit['pieces']:
        if p['body'] in (body,3) and p['slot']>=2:result[int(p['unit'])]=p
    return result

def check_plan(data,source_id,target_id,body=0):
    catalog=load_catalog();kits={k['archive']:k for k in catalog['armors']}
    if source_id not in kits or target_id not in kits:raise ValueError('只能选择目录中的盔甲，不能选择头盔。')
    if source_id==target_id:raise ValueError('来源和目标是同一套盔甲，无需替换。')
    b=core.Bundles(data);src=kits[source_id];tgt=kits[target_id]
    st=b.load(source_id);tt=b.load(target_id);se=core.parse(st);te=core.parse(tt)
    for kit,es in ((src,se),(tgt,te)):
        actual={str(e['id']) for e in es if e['type']==UNIT};expected={p['unit'] for p in kit['pieces']}
        if actual!=expected:raise ValueError('游戏资源已更新，部件与盔甲目录不一致：'+kit['name'])
    source_parts=selected(src,body);target_parts=selected(tgt,body)
    if not source_parts or not target_parts:raise ValueError('所选盔甲没有对应体型的部件。')
    carrier=min(target_parts,key=lambda fid:(target_parts[fid]['slot']!=2,target_parts[fid]['piece']!=0,int(target_parts[fid]['material_lut'])==0,fid))
    head={int(x) for x in catalog['excluded_helmet_unit_ids']}
    if head&set(target_parts):raise ValueError('目标部件与头盔资源重叠，停止生成。')
    return b,catalog,src,tgt,st,tt,source_parts,target_parts,carrier

def build(data,output,source_id,target_id,body=0,keep_source=True,remove_yellow=False,use_verified=True,log=print):
    data=Path(data).resolve();outbase=Path(output).resolve()
    if data==outbase or data in outbase.parents:raise ValueError('输出目录不能位于游戏 data 文件夹中。')
    log('检查两套盔甲和所选体型……');b,catalog,src,tgt,st,tt,sp,tp,carrier=check_plan(data,source_id,target_id,body)
    # Keep the user's already tested path for this exact armor family.
    b01={'58e4bd4b2278d15c','562a45e9bc984eb9','6cd3d55c05d4eac1','519cc1ec2eb56e1d'}
    if use_verified and source_id==core.SOURCE and target_id in b01:
        log('采用已经验证成功的 PH-56 → B-01 专用转换方案。')
        return core.build(data,outbase,log,keep_camo=keep_source,remove_yellow=remove_yellow,include_scarf=True,restore_scarf=True)
    log('读取来源外观、迷彩和附件……')
    sg=b.load(source_id+'.gpu_resources');ss=b.load(source_id+'.stream') if source_id+'.stream' in b.packages else b''
    tg=b.load(target_id+'.gpu_resources');se={e['id']:e for e in core.parse(st,sg,ss) if e['type']==UNIT};te={e['id']:e for e in core.parse(tt,tg) if e['type']==UNIT}
    bank=Assets(b,catalog,src,tgt,body,st,sg,ss,tt,tg,keep_source)
    bank.remove_yellow=bool(remove_yellow and source_id==core.SOURCE and keep_source)
    bank.initialize_atlas(tp[carrier]);parts=[]
    for fid,p in sp.items():
        e=se[fid];h=e['header'];go=u64(st,h+32);gs=u32(st,h+64)
        parts.append(dict(id=fid,piece=p,toc=st[e['offset']:e['offset']+e['size']],gpu=sg[go:go+gs]))
    basepart=min(parts,key=lambda p:(p['piece']['slot']!=2,p['piece']['piece']!=1,p['id']))
    e=te[carrier];target_unit=tt[e['offset']:e['offset']+e['size']]
    log('整合整套盔甲及附件，检查体型和动作绑定……')
    merged,merged_gpu,geometry=assemble(parts,basepart['id'],target_unit,bank.material_for,log,validate_poses=True)
    bank.gpu.extend(bytes((-len(bank.gpu))%64));go=len(bank.gpu);bank.gpu.extend(merged_gpu)
    head=bank.unit_header(carrier,se[basepart['id']],go,len(merged_gpu));bank.resources[carrier,UNIT]=(head,merged)
    # Empty draw sections suppress redundant target pieces while keeping a
    # valid native Unit/GPU layout. No helmet units enter the output.
    small=min(parts,key=lambda p:len(p['gpu'])+len(p['toc']));empty=hidden_unit(small['toc'])
    for fid in tp:
        if fid==carrier:continue
        bank.resources[fid,UNIT]=(bank.unit_header(fid,se[small['id']]),empty)
    log('整理独立配色，保留头盔共用颜色表的原始部分……');atlas=bank.finish_atlas();toc,gpu,stream=bank.compile()
    entries=core.parse(toc,gpu,stream);unit_ids={e['id'] for e in entries if e['type']==UNIT}
    if unit_ids!=set(tp) or unit_ids&{int(x) for x in catalog['excluded_helmet_unit_ids']}:raise ValueError('输出部件排除头盔的校验失败。')
    if atlas['original_target_first_eight_rows_sha256']!=atlas['target_first_eight_rows_sha256']:raise ValueError('目标原有颜色数据被意外修改。')
    for e in entries:
        if e['type']==UNIT:validate_lod_links(toc[e['offset']:e['offset']+e['size']])
    affected=[]
    for k in catalog['armors']:
        if k['archive']==target_id:continue
        overlap={int(p['unit']) for p in k['pieces']}&unit_ids
        if overlap:affected.append(dict(archive=k['archive'],name=k['name'],shared_body_units=len(overlap)))
    conflicts,unreadable=core.collision_scan(data,{(e['id'],e['type']) for e in entries})
    out=outbase/('ArmorSwap_'+source_id[:8]+'_to_'+target_id[:8]+'_'+('Stocky' if body==0 else 'Slim')+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:5]);out.mkdir(parents=True,exist_ok=False)
    mod=out/'Experimental_Mod';mod.mkdir();name='9ba626afa44a3aa3.patch_0';files={name:toc,name+'.gpu_resources':gpu,name+'.stream':stream}
    hashes={}
    for fname,raw in files.items():(mod/fname).write_bytes(raw);hashes[fname]=hashlib.sha256(raw).hexdigest()
    report={'version':'0.8.1','experimental':True,'game_tested':False,'source':src['name'],'source_archive':source_id,'target':tgt['name'],'target_archive':target_id,'body':'Stocky' if body==0 else 'Slim','keep_source_colors':keep_source,'helmet_units_modified':0,'gameplay_resources_modified':False,'source_parts':len(sp),'target_parts':len(tp),'accessory_parts':sum(p['piece']==2 for p in sp.values()),'carrier_unit':str(carrier),'geometry':geometry,'palette_atlas':atlas,'shared_armor_units':affected,'installed_conflicts':conflicts,'unreadable_patches':unreadable,'notes':bank.notes,'sha256':hashes,'limitations':['General conversion has not been verified in game for every armor pair.','Other armor sharing target body Unit IDs can be affected.','Use only the selected body type; generate another package to switch body type.','Runtime target pattern-LUT bindings may affect some camouflage patterns.']}
    (out/'diagnostic_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    text=f'''盔甲外观替换 0.8.1 · 通用实验包
来源外观：{src['name_zh']} / {src['name']}
穿着目标：{tgt['name_zh']} / {tgt['name']}
适用体型：{'壮硕' if body==0 else '苗条'}
来源模型部件：{len(sp)}；其中附件：{report['accessory_parts']}。

关闭游戏，停用旧测试包，使用现有 Mod 管理器导入 Experimental_Mod 内三个文件。
只启用一个测试包，由管理器分配空闲 Patch 编号；不要覆盖已有 Mod。
本包只输出外观资源，没有写入游戏目录，也没有修改属性、被动或头盔模型。
切换体型需要按另一种体型重新生成并替换本包。
部分目标部件被其他盔甲共用，这些盔甲也可能受影响，详见诊断报告。
通用方案尚未逐一进游戏验证；部分图案仍可能受游戏的目标材质绑定影响。
异常时在管理器中停用本包即可撤回。
'''
    (out/'先读我.txt').write_text(text,encoding='utf-8-sig');zpath=outbase/(out.name+'.zip')
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(out))
    with zipfile.ZipFile(zpath) as z:
        if z.testzip() is not None:raise ValueError('ZIP 文件校验失败。')
    log('生成完成：'+str(zpath));log('头盔模型改动：0。请先按所选体型测试。')
    return zpath,report


def gui():
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox,scrolledtext
    import queue,threading,os
    catalog=load_catalog();kits=catalog['armors'];kits.sort(key=lambda k:(k['name'],k['variant']))
    def display(k):
        v=(' · 变体 '+str(k['variant'])) if k['variant'] else ''
        weight={0:'轻型',1:'中型',2:'重型'}.get(k['weight'],'盔甲')
        return k['name_zh']+' / '+k['name']+v+' · '+weight
    labels=[display(k) for k in kits];mapping={display(k):k for k in kits};byid={k['archive']:display(k) for k in kits}
    w=tk.Tk();w.title('HD2 盔甲外观替换 · 全盔甲选择版 0.8.1');w.geometry('1000x830');w.minsize(850,720)
    f=ttk.Frame(w,padding=18);f.pack(fill='both',expand=True)
    ttk.Label(f,text='选择想显示的盔甲，再选择要替换的盔甲',font=('Microsoft YaHei UI',17,'bold')).pack(anchor='w')
    ttk.Label(f,text=f'目录包含 {len(kits)} 套盔甲，支持中英文搜索；不提供头盔和披肩替换。').pack(anchor='w',pady=(5,12))
    source=tk.StringVar(value=byid.get(core.SOURCE,labels[0]));target=tk.StringVar(value=byid.get(core.TARGET,labels[1]))
    for title,var in [('来源外观（想显示成哪一套）',source),('穿着目标（替换哪一套）',target)]:
        frame=ttk.Frame(f);frame.pack(fill='x',pady=7);ttk.Label(frame,text=title,width=29).pack(side='left')
        box=ttk.Combobox(frame,textvariable=var,values=labels,height=16);box.pack(side='left',fill='x',expand=True)
        def filtered(event,combo=box,variable=var):
            if event.keysym in ('Up','Down','Return','Tab'):return
            q=variable.get().strip().casefold();combo.configure(values=[x for x in labels if q in x.casefold()] or labels)
        box.bind('<KeyRelease>',filtered)
    def swap():a,b=source.get(),target.get();source.set(b);target.set(a)
    ttk.Button(f,text='交换来源与目标',command=swap).pack(anchor='e',pady=3)
    body=tk.IntVar(value=0);colors=tk.BooleanVar(value=True);yellow=tk.BooleanVar(value=False);verified=tk.BooleanVar(value=True)
    options=ttk.LabelFrame(f,text='外观选项',padding=10);options.pack(fill='x',pady=10)
    row=ttk.Frame(options);row.pack(fill='x');ttk.Label(row,text='适用体型：').pack(side='left');ttk.Radiobutton(row,text='壮硕',value=0,variable=body).pack(side='left',padx=8);ttk.Radiobutton(row,text='苗条',value=1,variable=body).pack(side='left',padx=8)
    ttk.Radiobutton(options,text='保留来源盔甲的原版配色与迷彩',value=True,variable=colors).pack(anchor='w',pady=(6,0))
    ttk.Radiobutton(options,text='使用目标盔甲配色（额外附件优先保留来源配色）',value=False,variable=colors).pack(anchor='w')
    trim=ttk.Checkbutton(options,text='去除 PH-56 原版黄色饰边（仅 PH-56 来源有效）',variable=yellow);trim.pack(anchor='w',pady=(6,0))
    ttk.Checkbutton(options,text='PH-56 → B-01 时优先采用已验证成功的 0.7 方案',variable=verified).pack(anchor='w')
    ttk.Label(f,text='通用转换为实验功能。切换体型需重新生成；共用部件的其他盔甲可能受影响。',foreground='#97621a',wraplength=900).pack(anchor='w',pady=4)
    d=tk.StringVar(value=DEFAULT_DATA);o=tk.StringVar(value=str(ROOT/'Generated'))
    for title,var in [('游戏 data 文件夹',d),('生成文件保存到',o)]:
        row=ttk.Frame(f);row.pack(fill='x',pady=6);ttk.Label(row,text=title,width=22).pack(side='left');ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
        def browse(v=var):
            p=filedialog.askdirectory()
            if p:v.set(p)
        ttk.Button(row,text='浏览',command=browse).pack(side='left',padx=5)
    buttons=ttk.Frame(f);buttons.pack(fill='x',pady=10);console=scrolledtext.ScrolledText(f,height=12,wrap='word');console.pack(fill='both',expand=True)
    q=queue.Queue();active=False
    def run(check=False):
        nonlocal active
        if active:return
        s,t=mapping.get(source.get()),mapping.get(target.get())
        if s is None or t is None:messagebox.showerror('请选择盔甲','输入关键词后，请从下拉列表中选择完整的盔甲名称。');return
        args=(d.get().strip(),o.get().strip(),s['archive'],t['archive'],body.get(),colors.get(),yellow.get(),verified.get());active=True
        def worker():
            try:
                if check:
                    _,_,sk,tk,_,_,sp,tp,_=check_plan(args[0],args[2],args[3],args[4]);q.put('组合检查通过：'+sk['name']+' → '+tk['name']);q.put('来源部件 '+str(len(sp))+'，目标部件 '+str(len(tp))+'，头盔不参与替换。')
                else:build(*args,log=q.put)
            except Exception as e:q.put('未生成：'+str(e))
            finally:q.put(None)
        threading.Thread(target=worker,daemon=True).start()
    ttk.Button(buttons,text='检查所选组合',command=lambda:run(True)).pack(side='left',padx=4);ttk.Button(buttons,text='生成替换包',command=run).pack(side='left',padx=4)
    def poll():
        nonlocal active
        while True:
            try:v=q.get_nowait()
            except queue.Empty:break
            if v is None:active=False
            else:console.insert('end',v+'\n');console.see('end')
        w.after(100,poll)
    console.insert('end','完整解压后使用。程序只生成文件，不会自动安装。默认组合沿用已验证的 0.7 方案。\n')
    poll();w.mainloop()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--data',default=DEFAULT_DATA);p.add_argument('--out');p.add_argument('--source');p.add_argument('--target');p.add_argument('--body',choices=('stocky','slim'),default='stocky');p.add_argument('--target-colors',action='store_true');p.add_argument('--remove-yellow',action='store_true');p.add_argument('--generic',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--list',action='store_true');a=p.parse_args()
    if a.list:print(json.dumps(load_catalog()['armors'],ensure_ascii=False,indent=2))
    elif a.source and a.target:
        if a.check:check_plan(a.data,a.source,a.target,int(a.body=='slim'));print('PASS')
        elif a.out:build(a.data,a.out,a.source,a.target,int(a.body=='slim'),not a.target_colors,a.remove_yellow,not a.generic)
        else:p.error('需要 --out 输出目录')
    else:gui()
