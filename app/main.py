from pathlib import Path
import os, sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
runtime = ROOT.parent / 'runtime'
if (runtime/'tcl/tcl8.6').is_dir():
    os.environ['TCL_LIBRARY'] = str(runtime/'tcl/tcl8.6')
    os.environ['TK_LIBRARY'] = str(runtime/'tcl/tk8.6')
import argparse, ctypes, json, queue, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import release_engine as engine
from i18n import tr


class ArmorApp:
    def __init__(self, root, lang='zh'):
        self.root=root; self.lang=lang; self.active=False; self.queue=queue.Queue(); self.records=[]; self.bindings=[]
        self.kits=sorted(engine.catalog()['armors'],key=lambda k:(k['name'],k['variant']))
        self.by_id={k['archive']:k for k in self.kits}
        self.source_id=engine.SS33; self.target_id=engine.RS89
        self.source=tk.StringVar(); self.target=tk.StringVar(); self.body=tk.IntVar(value=0)
        self.colors=tk.BooleanVar(value=True); self.hide_caps=tk.BooleanVar(value=True)
        self.leaf=tk.BooleanVar(value=True); self.trim=tk.BooleanVar(value=True)
        self.freeze_helmets=tk.BooleanVar(value=False)
        self.data=tk.StringVar(value=engine.backend.DEFAULT_DATA); self.output=tk.StringVar(value=str(engine.desktop_directory()))
        self.filename=tk.StringVar(); self.status=tk.StringVar(); self.map={}
        self.root.geometry(f"1000x{min(820,self.root.winfo_screenheight()-80)}"); self.root.minsize(900,720)
        self.root.configure(bg='#111820')
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MrFoxington.HD2ArmorSwap.1')
            self.root.iconbitmap(str(ROOT/'assets/app.ico'))
        except Exception: pass
        self.style=ttk.Style(root); self.style.theme_use('clam')
        self.style.configure('.',font=('Microsoft YaHei UI',10),background='#111820',foreground='#edf1f5')
        self.style.configure('TFrame',background='#111820'); self.style.configure('Card.TFrame',background='#1c2632')
        self.style.configure('TLabel',background='#111820',foreground='#edf1f5')
        self.style.configure('Muted.TLabel',foreground='#b5c0ce'); self.style.configure('Card.TLabel',background='#1c2632')
        self.style.configure('TButton',padding=(14,7),background='#2a394a',foreground='#edf1f5',borderwidth=0)
        self.style.map('TButton',background=[('active','#3b4b5f'),('disabled','#26303c')],foreground=[('disabled','#8390a2')])
        self.style.configure('Accent.TButton',background='#f4d645',foreground='#171b20',font=('Microsoft YaHei UI',10,'bold'))
        self.style.map('Accent.TButton',background=[('active','#ffe57a'),('disabled','#6b6339')],foreground=[('disabled','#c8c5b2')])
        self.style.configure('TEntry',fieldbackground='#243242',foreground='#f3f5f7',insertcolor='white',padding=6)
        self.style.configure('TCombobox',fieldbackground='#243242',foreground='#f3f5f7',padding=6,arrowsize=16)
        self.style.map('TCombobox',fieldbackground=[('readonly','#243242')],foreground=[('readonly','#f3f5f7')])
        self.style.configure('TRadiobutton',background='#1c2632',foreground='#edf1f5',padding=3)
        self.style.configure('TCheckbutton',background='#1c2632',foreground='#edf1f5',padding=3)
        self.style.map('TCheckbutton',foreground=[('disabled','#738092')]); self.style.configure('TLabelframe',background='#1c2632',bordercolor='#344354')
        self.style.configure('TLabelframe.Label',background='#111820',foreground='#cbd5e1')
        self.root.option_add('*TCombobox*Listbox.background','#243242'); self.root.option_add('*TCombobox*Listbox.foreground','#f3f5f7')
        self.root.option_add('*TCombobox*Listbox.selectBackground','#526479')
        self.root.columnconfigure(0,weight=1); self.root.rowconfigure(1,weight=1)
        header=ttk.Frame(root,padding=(24,18,24,10)); header.grid(row=0,column=0,sticky='ew'); header.columnconfigure(0,weight=1)
        heading=ttk.Frame(header); heading.grid(row=0,column=0,sticky='w')
        self.heading=ttk.Label(heading,font=('Microsoft YaHei UI',20,'bold')); self.heading.pack(side='left')
        ttk.Label(heading,text='  v1.2',foreground='#f4d645').pack(side='left',padx=12)
        self.language_button=ttk.Button(header,command=self.toggle_language); self.language_button.grid(row=0,column=1)
        self.label(header,'subtitle',style='Muted.TLabel',wraplength=880).grid(row=1,column=0,columnspan=2,sticky='w',pady=(5,0))
        main=ttk.Frame(root,padding=(24,0,24,8)); main.grid(row=1,column=0,sticky='nsew'); main.columnconfigure(1,weight=1); main.rowconfigure(9,weight=1)
        self.label(main,'source').grid(row=0,column=0,sticky='w',padx=(0,14),pady=5)
        self.source_box=ttk.Combobox(main,textvariable=self.source,height=13); self.source_box.grid(row=0,column=1,sticky='ew',pady=5)
        self.label(main,'target').grid(row=1,column=0,sticky='w',padx=(0,14),pady=5)
        self.target_box=ttk.Combobox(main,textvariable=self.target,height=13); self.target_box.grid(row=1,column=1,sticky='ew',pady=5)
        self.swap_button=self.button(main,'swap',self.swap); self.swap_button.grid(row=0,column=2,rowspan=2,padx=(10,0))
        for box,var,which in [(self.source_box,self.source,'source'),(self.target_box,self.target,'target')]:
            box.bind('<<ComboboxSelected>>',lambda e,w=which:self.selection_changed(w))
            box.bind('<KeyRelease>',lambda e,b=box,v=var:self.filter_box(e,b,v))
        options=ttk.LabelFrame(main,padding=(12,6)); options.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(10,8)); self.bindings.append((options,'options'))
        options.columnconfigure(1,weight=1)
        self.label(options,'body',style='Card.TLabel').grid(row=0,column=0,sticky='w',padx=(0,10))
        bodies=ttk.Frame(options,style='Card.TFrame'); bodies.grid(row=0,column=1,sticky='w')
        self.radio(bodies,'stocky',self.body,0).pack(side='left',padx=(0,15)); self.radio(bodies,'slim',self.body,1).pack(side='left')
        colors=ttk.Frame(options,style='Card.TFrame'); colors.grid(row=1,column=0,columnspan=2,sticky='w',pady=(3,0))
        self.radio(colors,'source_colors',self.colors,True).pack(side='left',padx=(0,16)); self.radio(colors,'target_colors',self.colors,False).pack(side='left')
        self.helmet_check=self.check(options,'freeze_ss_helmets',self.freeze_helmets)
        self.helmet_check.grid(row=2,column=0,columnspan=2,sticky='w',pady=(3,1))
        self.adaptive_label=ttk.Label(options,style='Card.TLabel',wraplength=850,foreground='#f4d645')
        self.adaptive_label.grid(row=3,column=0,columnspan=2,sticky='w',pady=(2,1))
        self.label(main,'data').grid(row=3,column=0,sticky='w',padx=(0,14),pady=4)
        ttk.Entry(main,textvariable=self.data).grid(row=3,column=1,sticky='ew',pady=4)
        self.button(main,'browse',lambda:self.browse(self.data,'pick_data')).grid(row=3,column=2,padx=(10,0))
        self.label(main,'output').grid(row=4,column=0,sticky='w',padx=(0,14),pady=4)
        ttk.Entry(main,textvariable=self.output).grid(row=4,column=1,sticky='ew',pady=4)
        self.button(main,'browse',lambda:self.browse(self.output,'pick_output')).grid(row=4,column=2,padx=(10,0))
        preview=ttk.Frame(main); preview.grid(row=5,column=0,columnspan=3,sticky='ew',pady=(5,3)); preview.columnconfigure(1,weight=1)
        self.label(preview,'filename',style='Muted.TLabel').grid(row=0,column=0,sticky='nw',padx=(0,12))
        ttk.Label(preview,textvariable=self.filename,style='Muted.TLabel',wraplength=720).grid(row=0,column=1,sticky='w')
        self.label(main,'zip_only',style='Muted.TLabel',wraplength=900).grid(row=6,column=0,columnspan=3,sticky='w',pady=(0,7))
        actions=ttk.Frame(main); actions.grid(row=7,column=0,columnspan=3,sticky='ew'); actions.columnconfigure(2,weight=1)
        self.generate_button=self.button(actions,'generate',lambda:self.run(False),style='Accent.TButton'); self.generate_button.grid(row=0,column=0,padx=(0,8))
        self.check_button=self.button(actions,'check',lambda:self.run(True)); self.check_button.grid(row=0,column=1)
        self.button(actions,'desktop',self.reset_output).grid(row=0,column=3,padx=(8,8)); self.button(actions,'open',self.open_output).grid(row=0,column=4)
        ttk.Label(main,textvariable=self.status,foreground='#f4d645').grid(row=8,column=0,columnspan=3,sticky='w',pady=(8,4))
        self.console=scrolledtext.ScrolledText(main,height=5,wrap='word',font=('Microsoft YaHei UI',9),bg='#0b1118',fg='#c8d4e2',insertbackground='white',borderwidth=0,padx=10,pady=8)
        self.console.grid(row=9,column=0,columnspan=3,sticky='nsew'); self.console.configure(state='disabled')
        footer=ttk.Frame(root,padding=(24,7,24,12)); footer.grid(row=2,column=0,sticky='ew'); footer.columnconfigure(1,weight=1)
        self.credit_image=tk.PhotoImage(file=str(ROOT/'assets/credit.png')); ttk.Label(footer,image=self.credit_image).grid(row=0,column=0,rowspan=2,padx=(0,14))
        self.credit_label=ttk.Label(footer,font=('Microsoft YaHei UI',10),wraplength=820); self.credit_label.grid(row=0,column=1,sticky='sw',pady=(0,3))
        self.notice=self.label(footer,'notice',style='Muted.TLabel',wraplength=820); self.notice.grid(row=1,column=1,sticky='nw')
        self.body.trace_add('write',lambda *a:self.update_preview()); self.colors.trace_add('write',lambda *a:self.option_changed()); self.trim.trace_add('write',lambda *a:self.update_preview())
        self.freeze_helmets.trace_add('write',lambda *a:self.update_preview())
        self.refresh_language(); self.log('no_install'); self.root.after(100,self.poll)

    def label(self,parent,key,**kw):
        w=ttk.Label(parent,**kw); self.bindings.append((w,key)); return w
    def button(self,parent,key,command,**kw):
        w=ttk.Button(parent,command=command,**kw); self.bindings.append((w,key)); return w
    def radio(self,parent,key,variable,value):
        w=ttk.Radiobutton(parent,variable=variable,value=value); self.bindings.append((w,key)); return w
    def check(self,parent,key,variable):
        w=ttk.Checkbutton(parent,variable=variable); self.bindings.append((w,key)); return w
    def display(self,k):
        weight=tr(self.lang,{0:'light',1:'medium',2:'heavy'}.get(k['weight'],'medium'))
        return f"{engine.armor_name(k,self.lang)} · {weight}"
    def refresh_language(self):
        self.root.title(tr(self.lang,'title')+' 1.2'); self.heading.configure(text=tr(self.lang,'heading'))
        self.language_button.configure(text='English' if self.lang=='zh' else '中文')
        for w,key in self.bindings:w.configure(text=tr(self.lang,key))
        self.credit_label.configure(text=tr(self.lang,'credit'))
        self.map={self.display(k):k for k in self.kits}; self.labels=list(self.map)
        for box in (self.source_box,self.target_box):box.configure(values=self.labels)
        self.source.set(self.display(self.by_id[self.source_id])); self.target.set(self.display(self.by_id[self.target_id]))
        self.status.set(tr(self.lang,'working' if self.active else 'ready')); self.option_changed(); self.render_log()
    def toggle_language(self):
        self.capture_selections(); self.lang='en' if self.lang=='zh' else 'zh'; self.refresh_language()
    def capture_selections(self):
        if self.source.get() in self.map:self.source_id=self.map[self.source.get()]['archive']
        if self.target.get() in self.map:self.target_id=self.map[self.target.get()]['archive']
    def selection_changed(self,which=None):
        self.capture_selections(); self.option_changed()
    def filter_box(self,event,box,var):
        if event.keysym in ('Up','Down','Return','Tab','Escape'):return
        q=var.get().strip().casefold(); result=[self.display(k) for k in self.kits if q in (k['name']+' '+k['name_zh']+' '+self.display(k)).casefold()]
        box.configure(values=result or self.labels)
    def option_changed(self):
        self.adaptive_label.configure(text=tr(self.lang,'adaptive_notice'))
        self.update_preview()
    def update_preview(self):
        if not hasattr(self,'filename'):return
        self.filename.set(engine.output_name(self.by_id[self.source_id],self.by_id[self.target_id],self.body.get(),self.lang,self.colors.get(),self.trim.get(),freeze_ss_helmets=self.freeze_helmets.get()))
    def swap(self):
        self.capture_selections(); self.source_id,self.target_id=self.target_id,self.source_id; self.refresh_language()
    def browse(self,var,title):
        p=filedialog.askdirectory(title=tr(self.lang,title),initialdir=var.get() if Path(var.get()).is_dir() else str(engine.desktop_directory()))
        if p:var.set(p)
    def reset_output(self):self.output.set(str(engine.desktop_directory()))
    def open_output(self):
        p=Path(self.output.get().strip())
        if p.is_dir():os.startfile(str(p))
    def log(self,key,**values):self.records.append((key,values)); self.render_log()
    def render_log(self):
        if not hasattr(self,'console'):return
        self.console.configure(state='normal'); self.console.delete('1.0','end')
        for key,values in self.records:self.console.insert('end',tr(self.lang,key,**values)+'\n')
        self.console.see('end'); self.console.configure(state='disabled')
    def error_text(self,e):
        if isinstance(e,engine.UserError):return tr(self.lang,e.code if e.code in ('same_armor','output_in_game','too_many_outputs','bad_zip','helmet_guard','leaf_profile_changed') else 'choose')
        return tr(self.lang,'unknown_error',detail=str(e))
    def run(self,check=False):
        if self.active:return
        source,target=self.map.get(self.source.get()),self.map.get(self.target.get())
        if not source or not target:messagebox.showerror(tr(self.lang,'error_title'),tr(self.lang,'choose'));return
        if source['archive']==target['archive']:messagebox.showerror(tr(self.lang,'error_title'),tr(self.lang,'same_armor'));return
        self.capture_selections()
        if not self.data.get().strip() or not self.output.get().strip():messagebox.showerror(tr(self.lang,'error_title'),tr(self.lang,'invalid_paths'));return
        args=(self.data.get().strip(),self.output.get().strip(),source['archive'],target['archive'],self.body.get(),self.colors.get(),self.trim.get() and source['archive']==engine.core.SOURCE and self.colors.get(),self.hide_caps.get(),self.leaf.get() and source['archive']==engine.SS33,self.lang)
        freeze_helmets=self.freeze_helmets.get()
        self.active=True; self.status.set(tr(self.lang,'working')); self.generate_button.configure(state='disabled'); self.check_button.configure(state='disabled')
        def worker():
            try:
                if check:
                    _,_,s,t,_,_,sp,tp,_=engine.backend.check_plan(args[0],args[2],args[3],args[4])
                    self.queue.put(('checked',{'target':t['name'],'source':s['name'],'parts':len(sp)}))
                else:
                    path,report=engine.build_release(*args,progress=lambda key,**kw:self.queue.put((key,kw)),freeze_ss_helmets=freeze_helmets)
                    if report['release_profile']['notes']:self.queue.put(('leaf_skipped',{}))
                    if report['ss_helmet_colors']['enabled']:self.queue.put(('ss_helmets_frozen',{}))
            except Exception as e:self.queue.put(('exception',e))
            finally:self.queue.put((None,None))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        while True:
            try:key,values=self.queue.get_nowait()
            except queue.Empty:break
            if key is None:
                self.active=False; self.generate_button.configure(state='normal'); self.check_button.configure(state='normal'); self.status.set(tr(self.lang,'ready'))
            elif key=='exception':self.log('failed',error=self.error_text(values))
            else:self.log(key,**values)
        self.root.after(100,self.poll)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--lang',choices=('zh','en'),default='zh'); p.add_argument('--gui-smoke'); p.add_argument('--check-runtime'); p.add_argument('--layout-audit')
    args=p.parse_args()
    if args.check_runtime:
        root=tk.Tk(); root.withdraw(); app=ArmorApp(root,args.lang); root.update()
        src,tgt=app.source_id,app.target_id; app.toggle_language(); assert (src,tgt)==(app.source_id,app.target_id); assert len(app.map)==137
        app.swap(); assert app.source_id==tgt and app.target_id==src; app.swap()
        assert app.credit_image.width()==64 and len(app.source_box['values'])==137
        Path(args.check_runtime).write_text(json.dumps({'passed':True,'version':engine.VERSION,'desktop':str(engine.desktop_directory()),'language_switch':True,'selection_preserved':True,'armor_count':len(app.map),'footer_image_loaded':True,'icon_exists':(ROOT/'assets/app.ico').is_file(),'python_executable':sys.executable,'python_prefix':sys.prefix,'tcl_library':str(root.tk.call('info','library'))},ensure_ascii=False,indent=2),encoding='utf8'); root.destroy(); return
    root=tk.Tk(); app=ArmorApp(root,args.lang)
    if args.layout_audit:
        checks=[]
        for language in ('zh','en'):
            app.lang=language; app.refresh_language(); root.update_idletasks(); root.update()
            bounds={}
            for name,w in [('generate',app.generate_button),('source',app.source_box),('target',app.target_box),('language',app.language_button),('credit',app.credit_label),('notice',app.notice),('console',app.console),('helmet_toggle',app.helmet_check),('adaptive_notice',app.adaptive_label)]:
                x,y=w.winfo_rootx()-root.winfo_rootx(),w.winfo_rooty()-root.winfo_rooty()
                width,height=w.winfo_width(),w.winfo_height()
                assert x>=0 and y>=0 and x+width<=root.winfo_width()+1 and y+height<=root.winfo_height()+1,(language,name,x,y,width,height,root.winfo_geometry())
                bounds[name]=[x,y,width,height]
            checks.append({'lang':language,'window':[root.winfo_width(),root.winfo_height()],'all_controls_inside_window':True,'bounds':bounds})
        Path(args.layout_audit).write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8'); root.destroy(); return
    if args.gui_smoke:
        def finish():
            Path(args.gui_smoke).write_text(json.dumps({'title':root.title(),'lang':app.lang,'footer':app.credit_label['text'],'filename':app.filename.get()},ensure_ascii=False,indent=2),encoding='utf8'); root.destroy()
        root.after(1800,finish)
    root.mainloop()

if __name__=='__main__':main()
