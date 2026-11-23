# Sources and licenses
Aetherloom application code includes original implementation and the following attributed upstream components. HMCL and PCL code is not included.
Desktop uses CustomTkinter 5.2.2 (MIT), Python tkinter/Tcl/Tk and Pillow; installed CustomTkinter license notices are included. Qt/PySide6 is no longer part of the desktop application.
Current dev distribution does not bundle a Java runtime. Existing Java is discovered in known installation/runtime locations or manually selected. An optional user-requested download installs Eclipse Temurin from the official Adoptium API; its SHA-256, size and platform are verified and the archive notices/legal files are retained. No Java binary is embedded in the client EXE. Historical v0.1.0 bundles Eclipse Temurin OpenJDK17 under GPLv2 with Classpath Exception and preserves runtime/legal and runtime/NOTICE.
Included / referenced components:
- CraftLink: GPLv3; local reviewed dev 8178a3df0e73a88c41bab70574014b98b1c36ffe. Unmodified transport modules are under aetherloom/vendor/craftlink, with GPL license and SOURCE.json SHA-256 pins. Account policy is adapted in management.py. Upstream stream tests are adapted in tests/test_craftlink_stream.py.
- MCsaves-sync (design reference only, no source included): GPLv3; 17afc06e4ef19720afc43b725bac9baaa8d9b062; hash algorithm will not be inherited.
- Save discovery follows the selected-instance saves/level.dat layout and metadata fields in MCsaves-sync client/core/scanner.py and nbt.py. Aetherloom's bounded NBT reader is original; no filesystem-wide scans or runtime region hashing are added.
- CraftLink STUN diagnostics: upstream core/stun.py at 8178a3df0e73a88c41bab70574014b98b1c36ffe, GPLv3. Vendored with import-only enum adaptation; exact hashes and changes are in vendor/craftlink/SOURCE.json. Status terminology follows upstream gui/presentation.py. The diagnostic socket's result does not assert the operational P2P socket's reachability.
- shared-playerdata: MIT, Copyright 2026 radix-angelicae; baseline 2d0cf068ff252d7542d44536a677a2fdb247cff7. Tag.java, NbtIo.java and Uuids.java are included unmodified under playerdata; MIT notice and SOURCE.json are preserved. The strict selected-world entrypoint is original adaptation.
Aetherloom distribution will include compatible source and notices. Build-time JDK/Gradle and user-provided game files retain their respective licenses.


Gradle wrapper 8.8 is from the official Forge 1.20.1-47.4.22 MDK; Gradle is Apache-2.0, https://github.com/gradle/gradle/blob/v8.8.0/LICENSE . websockets15.0.1 is BSD-3-Clause; PyMySQL1.1.2 is MIT; cryptography46.0.3 is Apache-2.0/BSD-3-Clause. Dependency distributions preserve their own notices.

Java management behavior reference (no HMCL source imported): HMCL JavaManager, JavaRuntime, GameJavaVersion and JavaVersionConstraint under https://github.com/HMCL-dev/HMCL . Original Python implementation remains in Aetherloom. Adoptium API reference: https://github.com/adoptium/api.adoptium.net/blob/main/docs/cookbook.adoc . Downloaded Temurin builds retain their GPLv2 with Classpath Exception terms and included third-party notices.

Single-file client: embedded project/dependency notices are accessible in the desktop license viewer. The two helper JARs and BUILD_INFO.json are embedded resources; no separate copies are retained as workspace deliverables.

Aetherloom Bridge 0.1.1: GPL-3.0-only; standalone source https://github.com/radix-Lunaris/Aetherloom-Bridge at 58b988891d2f96101b810ecfc0984aaeb2b0dbd5. The vendored bridge/SOURCE.json pins source hashes. Targets Minecraft 1.20.1 / Forge 47, tested against 47.4.22; not a universal cross-version Mod. It does not include the separate MIT shared-playerdata helper.

authlib-injector1.2.8: unmodified upstream build56, source commit5437f5b465ee3f5be0a1e5e1ae3c50978114f6fb, https://github.com/yushijinhun/authlib-injector/tree/5437f5b465ee3f5be0a1e5e1ae3c50978114f6fb . AGPLv3-or-later with AUTHLIB-INJECTOR exception (unaltered binary bundling and Java Agent use). Corresponding source is available at that upstream commit. Full license and embedded dependency notices are preserved in aetherloom/vendor/authlib and the EXE license viewer; SOURCE.json pins URL/SHA-256. Used for LittleSkin Yggdrasil game identity/skins, independently of Aetherloom software login.

## Agent 多加载器适配与 STUN

ASM 9.8 来自官方 Maven Central，采用 BSD 3-Clause。许可证和哈希位于 `aetherloom/vendor/asm/`。构建时重定位至私有命名空间并内嵌 EXE。Fabric intermediary 的 CC0 声明、Mojang 映射声明和 Forge MCPConfig 来源随派生别名提供，见 `agent/resources/MAPPINGS-SOURCE.json` 与 `MAPPINGS-NOTICE.txt`。CraftLink 双端口 STUN responder 按 GPL 来源适配，版本及本地修改见 `aetherloom/vendor/craftlink/SOURCE.json`。

历史控制别名另使用 Ornithe Calamus（CC0-1.0）。来源、输入哈希与派生别名哈希见 `agent/resources/HISTORICAL-MAPPINGS-SOURCE.json`。


MCSync 区块与 NBT 处理来自 b31d0f9，原许可证及来源信息位于 aetherloom/vendor/mcsync。CraftLink punch.py 来自 7d77067，逐文件来源见对应 SOURCE.json。上游许可证版本保留。

应用 UDP 转发、UdpHub 应用数据报分流及 UDP 中继基于 CraftLink dev 1fd395671474d15f1f24a4404699befb3c4c4754，使用 Aetherloom HTTPS 账号、会话代次和短期端点授权。
