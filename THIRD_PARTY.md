# Sources and licenses
Aetherloom application code includes original implementation and the following attributed upstream components. HMCL and PCL code is not included.
Desktop uses CustomTkinter 5.2.2 (MIT), Python tkinter/Tcl/Tk and Pillow; installed CustomTkinter license notices are included. Qt/PySide6 is no longer part of the desktop application.
Current dev distribution does not bundle a Java runtime. Existing Java is discovered in known installation/runtime locations or manually selected. An optional user-requested download installs Eclipse Temurin from the official Adoptium API; its SHA-256, size and platform are verified and the archive notices/legal files are retained. No Java binary is added to the client ZIP. Historical v0.1.0 bundles Eclipse Temurin OpenJDK17 under GPLv2 with Classpath Exception and preserves runtime/legal and runtime/NOTICE.
Included / referenced components:
- CraftLink: GPLv3; local reviewed dev 8178a3df0e73a88c41bab70574014b98b1c36ffe. Unmodified transport modules are under aetherloom/vendor/craftlink, with GPL license and SOURCE.json SHA-256 pins. Account policy is adapted in management.py. Upstream stream tests are adapted in tests/test_craftlink_stream.py.
- MCsaves-sync (design reference only, no source included): GPLv3; 17afc06e4ef19720afc43b725bac9baaa8d9b062; hash algorithm will not be inherited.
- shared-playerdata: MIT, Copyright 2026 radix-angelicae; baseline 2d0cf068ff252d7542d44536a677a2fdb247cff7. Tag.java, NbtIo.java and Uuids.java are included unmodified under playerdata; MIT notice and SOURCE.json are preserved. The strict selected-world entrypoint is original adaptation.
Aetherloom distribution will include compatible source and notices. Build-time JDK/Gradle and user-provided game files retain their respective licenses.


Gradle wrapper 8.8 is from the official Forge 1.20.1-47.4.22 MDK; Gradle is Apache-2.0, https://github.com/gradle/gradle/blob/v8.8.0/LICENSE . websockets15.0.1 is BSD-3-Clause; PyMySQL1.1.2 is MIT; cryptography46.0.3 is Apache-2.0/BSD-3-Clause. Dependency distributions preserve their own notices.

Java management behavior reference (no HMCL source imported): HMCL JavaManager, JavaRuntime, GameJavaVersion and JavaVersionConstraint under https://github.com/HMCL-dev/HMCL . Original Python implementation remains in Aetherloom. Adoptium API reference: https://github.com/adoptium/api.adoptium.net/blob/main/docs/cookbook.adoc . Downloaded Temurin builds retain their GPLv2 with Classpath Exception terms and included third-party notices.
