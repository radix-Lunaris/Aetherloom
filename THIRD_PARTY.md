# Sources and licenses
Current Python implementation is original Aetherloom code. HMCL and PCL code is not included.
Desktop uses CustomTkinter 5.2.2 (MIT), Python tkinter/Tcl/Tk and Pillow; installed CustomTkinter license notices are included. Qt/PySide6 is no longer part of the desktop application.
Bundled runtime: Eclipse Temurin OpenJDK17, GPLv2 with Classpath Exception; preserve runtime/legal and runtime/NOTICE.
Planned imports (not integrated yet):
- CraftLink: GPLv3; local reviewed dev 8178a3df0e73a88c41bab70574014b98b1c36ffe. Pin and preserve notices when importing.
- MCsaves-sync: GPLv3; 17afc06e4ef19720afc43b725bac9baaa8d9b062; hash algorithm will not be inherited.
- shared-playerdata: MIT, Copyright 2026 radix-angelicae; baseline 2d0cf068ff252d7542d44536a677a2fdb247cff7. Preserve MIT notice with imported code.
Aetherloom distribution will include compatible source and notices. Java runtime redistribution and notices must be included when packaging.

