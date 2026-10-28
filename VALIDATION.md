# Validation scope / 校验范围

Version: 1.2.0. This describes local checks, not an antivirus certification.

- UI: Chinese/English switching, exact requested notice, hidden automatic fixes, both color choices, and SS helmet switch routing.
- Portable launcher/runtime: startup and Tcl/Tk initialization passed.
- SS helmet freeze: all 12 environment LUTs match their respective original default colors, including mip data.
- 17 prior generated-asset fixtures: body resources remain unchanged when the optional helmet LUT overrides are added; disabling the option preserves original files.
- 2 full generated packages: generic SS-33-to-RS-89 and the validated PH-56/B-01 path passed ZIP/manifest/hash checks.
- Unpacked standard library: startup and actual generation passed; the three emitted patch files were byte-identical to the corresponding v1.2 output.
- Public build script: rebuilt a portable folder from a full Python 3.12 installation; the rebuilt launcher passed startup checks.
- Distribution ZIPs: CRC passed; no nested archives in the revised portable/source packages.

No antivirus scan or Nexus approval is claimed. The SS helmet freeze and all possible armor combinations
have not been certified through in-game testing. No game installation/mod deployment was changed by
these checks. Private local paths and generated game assets are omitted from this repository.

中文：以上为本机启动、生成文件和资源一致性校验，不代表杀毒认证或 Nexus 放行。
头盔效果和所有护甲组合仍需游戏内实测；本仓库不包含测试用游戏资源与个人路径。
