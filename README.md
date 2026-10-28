# HD2 Armor Swap / 护甲外观替换生成器

免费的《绝地潜兵 2》Windows 盔甲外观替换包生成工具，当前功能版本为 **1.2**。
此仓库提供应用源码与构建说明，供用户查看及 Nexus Mods 人工审核。

**这是换肤包生成器，不是帧率优化模组；没有测试或承诺提高游戏性能。**
工具读取本机原版游戏资源，生成可导入 Arsenal 的 ZIP。生成后即可关闭工具。
穿戴目标保留原本属性和被动。仓库不包含游戏模型、游戏纹理、Python 运行环境或生成的 Mod。

## 从源码运行

需要 Windows x64 和完整的 Python 3.12（包含 Tcl/Tk），无需安装 pip 依赖。
在仓库目录运行：

```text
python -I app/main.py
```

## 构建便携版

使用完整的 Windows x64 Python 3.12 及 .NET Framework C# 编译器：

```text
python build_portable.py
```

默认生成 `dist/HD2_Armor_Swap_v1_2_Nexus`。输出目录必须尚不存在。
标准库以普通文件保存在 `runtime/Lib`，不会生成内层标准库 ZIP。
完整构建和第三方组件说明见 [SOURCE_AND_BUILD.md](SOURCE_AND_BUILD.md)。

## 使用方法

1. 选择“想显示的外观”和“游戏中穿戴的护甲”，体型需与游戏一致。
2. “替换颜色表”使用来源配色；“不替换颜色表”使用穿戴目标配色。
3. 可选勾选“关闭 SS 系列头盔变色”，将 SS-33、SS-15、SS-500 头盔固定为各自默认配色。默认不勾选。
4. 确认游戏 `data` 路径，点击“生成 ZIP”。默认保存到当前 Windows 桌面。
5. 关闭游戏，在 Arsenal 停用旧的同目标换肤包，导入新生成的 ZIP，启用并部署。
6. 启动游戏，装备所选穿戴目标。不要把软件发行包当作 Mod 导入 Arsenal。

红斑处理、PH-56 去黄边和 SS-33 叶片修正按所选组合自动处理。
头盔模型不参与替换；头盔固定配色开关仅改动三款头盔的 12 份环境颜色表。
取消开关后，需要停用旧包、重新生成并部署，才能恢复原生头盔变色。

## 当前限制

- 来源护甲的可变迷彩功能尚不能迁移到普通穿戴目标。例如穿 RS-89 显示 SS-500 外观时仍为固定配色。
- 并非所有组合都已完成游戏内测试；共享资源可能影响其他护甲。
- 发布包包含 EXE/DLL 时仍可能触发 Nexus 审核。源码公开和取消嵌套压缩并不代表已获安全审核通过。
- 校验范围见 [VALIDATION.md](VALIDATION.md)，完整使用说明见 [README.txt](README.txt)。

该免费软件由B站Mr-Foxington/chatgpt制作。

---

## English

**HD2 Armor Swap is a free Windows armor appearance ZIP generator, not an FPS optimization mod.**
There is no measured or promised frame-rate improvement. The tool reads your local game assets,
creates an Arsenal-compatible mod ZIP, and can be closed after generation. The worn armor retains
its original stats and passive. This repository contains application sources, UI assets and catalogs;
it does not contain game models/textures, bundled Python binaries or generated game mods.

### Run / build

Use a full Windows x64 Python 3.12 installation with Tcl/Tk. No pip packages are required.
Run `python -I app/main.py`, or build a portable folder with `python build_portable.py`.
The build requires the .NET Framework C# compiler and produces an unpacked standard library in
`runtime/Lib`. See [source and build notes](SOURCE_AND_BUILD.md).

### Use

Choose the desired appearance, the armor you will actually wear, and the matching body type.
Select source colors or worn-target colors. Optionally freeze the SS-33, SS-15 and SS-500 helmets
at their own default colors. Generate the ZIP, close the game, disable the previous swap for that
target in Arsenal, then import, enable and deploy the generated ZIP. Equip the selected worn armor.
The output defaults to the current Windows desktop. Helmet models are not replaced.

Adaptive source bindings are not transferred to non-adaptive worn targets. Not every combination
has been tested in game. Shared body resources can affect other armor. Publishing source and
removing nested archives do not guarantee Nexus approval.

Created by Bilibili Mr-Foxington/chatgpt.
