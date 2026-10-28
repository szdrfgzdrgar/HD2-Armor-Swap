"""Build an unpacked Windows portable distribution using an installed Python 3.12.

Run from the published source bundle: python build_portable.py
No downloads, pip dependencies, obfuscation, or embedded archives are used.
"""
from pathlib import Path
import argparse,os,shutil,subprocess,sys

ROOT=Path(__file__).resolve().parent
ARCHIVES={'.zip','.7z','.rar','.tar','.gz','.bz2','.xz','.whl','.egg','.pyz','.cab','.tgz'}

def ignore(folder,names):
    return [name for name in names if name in {'site-packages','__pycache__','test','tests','idlelib','turtledemo','ensurepip'}
            or Path(name).suffix.lower() in ARCHIVES|{'.pyc','.pyo'}]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist/HD2_Armor_Swap_v1_2_Nexus')
    args=parser.parse_args()
    if os.name!='nt' or sys.version_info[:2]!=(3,12):
        raise SystemExit('Use a full Windows x64 Python 3.12 installation with Tcl/Tk.')
    installed=Path(sys.base_prefix);out=args.output.resolve()
    if out.exists():raise SystemExit('Output already exists; choose a new output folder.')
    if out==ROOT or any(p in out.parents for p in (ROOT/'app',installed)):
        raise SystemExit('Output must be outside app and Python installation folders.')
    for name in ('Lib','DLLs','tcl','python.exe','pythonw.exe','python312.dll'):
        if not (installed/name).exists():raise SystemExit('A full Python installation is required: missing '+name)
    compiler=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():raise SystemExit('Install the .NET Framework C# compiler, or build Launcher.cs with an equivalent C# compiler.')
    out.mkdir(parents=True)
    shutil.copytree(ROOT/'app',out/'app',ignore=ignore)
    runtime=out/'runtime';runtime.mkdir()
    for folder in ('Lib','DLLs','tcl'):
        shutil.copytree(installed/folder,runtime/folder,ignore=ignore)
    for name in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        if (installed/name).is_file():shutil.copy2(installed/name,runtime/name)
    (runtime/'python312._pth').write_text('Lib\nDLLs\n.\n../app\n',encoding='ascii')
    for name in ('README.txt','SOURCE_AND_BUILD.md'):
        shutil.copy2(ROOT/name,out/name)
    shortcut=ROOT/'创建桌面快捷方式.vbs'
    if shortcut.is_file():shutil.copy2(shortcut,out/shortcut.name)
    source=out/'source';source.mkdir()
    shutil.copy2(ROOT/'Launcher.cs',source/'Launcher.cs')
    shutil.copy2(ROOT/'build_portable.py',source/'build_portable.py')
    result=subprocess.run([str(compiler),'/nologo','/target:winexe','/optimize+',
        '/reference:System.Windows.Forms.dll','/out:'+str(out/'HD2ArmorSwap.exe'),
        '/win32icon:'+str(out/'app/assets/app.ico'),str(ROOT/'Launcher.cs')],capture_output=True,text=True)
    if result.returncode:raise SystemExit(result.stdout+result.stderr)
    assert not any(p.suffix.lower() in ARCHIVES for p in out.rglob('*') if p.is_file())
    print('Built '+str(out))
    print('ZIP this folder once for distribution; do not add other archives inside it.')

if __name__=='__main__':main()
