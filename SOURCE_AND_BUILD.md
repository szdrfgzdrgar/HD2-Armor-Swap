# HD2 Armor Swap 1.2: source and build notes

## What this package contains

The application source is the readable Python files in `app/` (including the
resource parsers and generators). `Launcher.cs` is the complete source of the
small C# launcher: it starts the bundled `runtime/pythonw.exe -I app/main.py`,
passes arguments through and waits for exit. The launcher does not contain the
armor generator or any packed/encrypted payload.

The optional desktop-shortcut VBS in the portable package is plaintext. It only
creates a shortcut to HD2ArmorSwap.exe using Windows Script Host. Users may
create their own shortcut instead. The tool itself does not deploy game mods.

All application assets/catalogs needed to run or rebuild are in `app/`.
No extracted game models, game textures, generated mod ZIPs or game files are
bundled. The application reads assets from the user's local game installation.
The two artwork files were supplied for this tool by Mr-Foxington.

## Run from source without compiling

1. Install a full Windows x64 Python 3.12 distribution with Tcl/Tk.
2. Extract the complete source package.
3. In this folder run: `python -I app/main.py`
4. No pip packages, network downloads or installers are invoked by the app.

The source-only ZIP contains no EXE, DLL, PYD or nested archive. It requires
the user to install Python separately; it is not the self-contained portable build.

## Rebuild a portable folder

Use a full Windows x64 Python 3.12 installation with `Lib`, `DLLs` and `tcl`.
The distributed runtime reports Python 3.12.14. With the .NET Framework C#
compiler installed, run from this source folder:

```
python build_portable.py
```

It creates `dist/HD2_Armor_Swap_v1_2_Nexus` without modifying the Python
installation. The output must not already exist. It copies readable stdlib
files into runtime/Lib, writes python312._pth and invokes the C# compiler with:

```
csc.exe /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll /out:HD2ArmorSwap.exe /win32icon:app/assets/app.ico Launcher.cs
```

The included script uses absolute paths for these arguments and locates
csc.exe under the Windows .NET Framework directory. Build results can differ
by Python/compiler version; byte-for-byte reproducible third-party binaries
are not claimed. No code obfuscation or self-extracting executable is used.
Create one ordinary outer ZIP of the resulting folder. Do not put another
ZIP/7z/RAR/WHL inside it.

## Third-party runtime

Python EXE/DLL/PYD and Tcl/Tk files in the portable build are copied unchanged
from the existing Python runtime. Their licenses are retained in runtime/
and runtime/tcl. Their publicly available upstream sources/build guides are:

- CPython: https://github.com/python/cpython
- Windows build guide: https://github.com/python/cpython/tree/3.12/PCbuild
- Tcl: https://core.tcl-lang.org/tcl/
- Tk: https://core.tcl-lang.org/tk/

Microsoft Visual C++ runtime DLLs are Microsoft components. Rebuilding the
application does not rebuild these third-party components.

## Nexus review

Unpacking the standard library addresses the nested-archive issue. Executable
files or scanner findings can still require review. Do not rename executable
or archive extensions, password-protect the package or obscure its contents.
If the upload remains quarantined, provide Nexus support with the mod-page
link, a public repository containing this complete source, and these build
steps. This source bundle is prepared for publication; no repository or support
email has been published/sent automatically.

中文说明：本次只调整发布结构，功能仍为 1.2。Python 标准库已展开为普通
文件夹，启动路径随之调整。附完整应用源码、启动器源码和通用构建脚本。
源码包需自行安装 Python；便携包仍包含 EXE/DLL，是否放行由 Nexus 审核决定。
若需人工审核，请先把源码公开到 GitHub 等平台，再将公开链接、模组页链接
及此构建说明提交给 Nexus 支持团队。不要删除原隔离文件来替代人工复核。
