Nexus 发布包装调整 / Nexus distribution packaging
功能仍为 1.2，EXE、DLL 和 app 代码与原版一致。
内层 runtime/python312.zip 已实际展开为 runtime/Lib，并更新运行路径。
不是将压缩文件改名；包内不含第二层压缩文件。
完整解压后运行 HD2ArmorSwap.exe，无需另行安装 Python。
此调整不代表已获 Nexus 审核通过。EXE/DLL 或扫描结果仍可能触发人工审核。
源码与构建步骤见 SOURCE_AND_BUILD.md。

Functionality remains v1.2. The EXE, DLLs and app code are unchanged.
The inner standard-library ZIP has been extracted to runtime/Lib; import paths are updated.
There are no renamed/disguised archives. This does not guarantee Nexus approval.
Run HD2ArmorSwap.exe after extracting the complete package. See SOURCE_AND_BUILD.md.

HD2 护甲外观替换 1.2 / HD2 Armor Swap 1.2
该免费软件由B站Mr-Foxington/chatgpt制作

1.2 更新
- 新增“关闭 SS 系列头盔变色（SS-33 / SS-15 / SS-500）”勾选开关，默认不勾选。
- 勾选后点“生成 ZIP”，生成包同时把三款头盔固定为各自默认配色；不替换头盔模型，也不覆盖盔甲配色。
- 取消开关不会自动撤销已部署的 Mod。请在 Arsenal 停用旧包，再取消勾选、重新生成并部署。
- 删掉界面中“与 0.3 版一致……”那行说明。
- 界面黄色提示统一为“可变迷彩功能因技术原因无法实现”。
- 此开关是固定头盔颜色，不会把护甲的环境变色迁移到普通穿戴目标。
- 数据和生成文件经过校验，头盔效果仍需游戏内验证。

保留的 1.1 功能与当前限制
- 红斑处理、PH-56 去黄边、SS-33 叶片修正默认开启，按所选护甲自动应用，界面隐藏这三个开关。
- 恢复 0.3 版含义明确的两种配色选择：
  “替换颜色表”：使用来源外观的配色。
  “不替换颜色表”：使用游戏中穿戴目标的配色。
- 三套原生可变色盔甲为 SS-33、SS-15、SS-500。
  穿戴目标是其中一套时，本版为原生环境切换补齐森林、沙漠、冰雪、猩红四组颜色表。
  来源也为可变色护甲且选择替换颜色表时，使用来源相应的四组配色。
  来源为普通固定配色护甲时，选择“不替换颜色表”才保留穿戴目标的环境配色变化。
  以上已通过生成文件、部件绑定和四组配色的数据校验，尚未完成游戏内验证。
- 穿戴 RS-89 等普通护甲、显示 SS-500/SS-33/SS-15 外观时，仍不能迁移原生环境变色。
  本版会明确显示“只能生成固定配色”，输出文件名也标注“固定配色”。
  例如：穿 RS-89 显示 SS-500 的原始诉求，目前仍未实现自动环境变色。
  没有用静态配色伪装成该功能已完成。该方向需要另外实现、验证与当前游戏兼容的运行时绑定。
  本软件包不安装或依赖运行时加载器，也不改动游戏配置。

使用方法
1. 将整个 ZIP 解压到一个可以写入的文件夹。
2. 双击 HD2ArmorSwap.exe。运行环境已随包附带，无需安装 Python。
   app 和 runtime 文件夹必须与 EXE 放在一起，不能只单独移动 EXE。
3. 想在桌面启动时，双击“创建桌面快捷方式.vbs”，快捷方式使用图 2 的图标。
4. “想显示的外观”选择来源，“游戏中穿戴的护甲”选择你要穿的目标。
5. 选择实际体型和配色，检查游戏 data 路径，再点“生成 ZIP”。
6. 默认保存到 Windows 当前桌面，支持 OneDrive 重定向的桌面。
   文件名格式为“穿戴目标护甲_显示来源外观_体型.zip”。
   已有同名文件自动增加编号，不覆盖旧包。默认只输出一个 ZIP，不留解压目录。
7. 关闭游戏，在 Arsenal 中停用旧的同目标替换包，再直接导入生成的 ZIP。
   请勿把 HD2_Armor_Swap_v1_2_Nexus.zip（软件包）作为游戏 Mod 导入。

软件右上角的 English / 中文按钮可以切换界面，不会清空已选护甲。
下拉列表支持中英文搜索。目录包含 137 项独立盔甲档案（含变体），不包含头盔和披肩。
7 项暂无本地化名称的游戏资源用编号显示，可能属于未使用或预留内容。

整合内容
- PH-56 → B-01 自动沿用已确认的围巾、配色和去多余图案方案。
- 通用整套部件及附件组装，包含远近模型引用越界防护。
- 保留部件的网格设置，不给无顶点颜色的模型强行填充白色。
- 自动隐藏伤口断面绘制，修复额外红斑。
- SS-33 保留已确认的领口/胸前原版两层蒙版处理。
  两种配色选择均自动应用叶片处理。其他叶片/特效部件仍需游戏内验证。
  若目标与头盔共用颜色表，会跳过这项配色修改以保护头盔。
  此方案还保留叶片最高细节设置，远处可能有更多渲染开销。
- 生成包包含 Arsenal Version 1 manifest.json，可直接导入。

说明
程序只生成外观包，不自动部署，不修改属性、被动或头盔模型。
共享部件或配色表可能使其他盔甲同时受影响，诊断报告保存在生成的 ZIP 内。
不是所有护甲组合均已完成游戏内测试。切换体型后请重新生成对应包。
所有中间文件在软件文件夹的临时目录内生成并在完成后清理。
此软件免费。软件内图片按本次用户提供的原图缩放使用。

English quick start
Version 1.2 adds an optional SS-33 / SS-15 / SS-500 helmet color freeze switch (off by default).
Check it before generating a ZIP to include twelve fixed-default environment LUT overrides.
To restore native helmet color changes, disable the old mod, uncheck it, regenerate and deploy.
The marked help sentence is removed; the yellow notice is updated as requested.
Version 1.1 functionality is retained: the app automatically applies and hides the three compatibility fixes. The two color modes
select source colors or worn-target colors, matching the intent of v0.3.
Native adaptive targets SS-33, SS-15 and SS-500 receive four expanded environment LUTs.
Use worn-target colors to retain a native adaptive target's colors when the source is static.
Adaptive-to-adaptive swaps can use source environment LUTs. These paths need in-game testing.
Source adaptive bindings are NOT transferred to non-adaptive targets: RS-89 worn with an
SS-500 look is still FIXED COLOR. The GUI, output filename and generated README state this.
This package does not include/install a runtime loader or claim that limitation is solved.
Extract the entire ZIP, then run HD2ArmorSwap.exe. No Python installation is needed.
Keep app and runtime beside the EXE. Run the included VBS to create a desktop shortcut.
Choose the appearance to display, then the armor to wear. Select the body type and colors.
The output defaults to the actual Windows desktop, including redirected OneDrive desktops.
Only a ZIP is produced; duplicate names are numbered. Import the generated ZIP into Arsenal.
The application distribution ZIP is not a game mod. Disable previous replacements first.
Helmet/cape models are excluded. The optional SS helmet switch only freezes the three helmets' environment palettes. No automatic mod installation or gameplay/stat changes are made.
The SS-33 profile preserves the accepted collar/torso mask fix; not every special effect or
armor pair has been tested in game. Shared resources can affect other armor.

Source references / attribution
Armor metadata and format reference: https://github.com/xypwn/filediver
Unit/material format reference: https://github.com/Boxofbiscuits97/HD2SDK-CommunityEdition
LUT/mask layout reference: https://github.com/ARoese/Helldivers-2-IDMask-Edit
The bundled Python license is in runtime/LICENSE.txt; Tcl/Tk notices are retained under runtime/tcl.
