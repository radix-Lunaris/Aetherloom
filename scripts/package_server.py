"""Create the minimal Docker upload bundle, excluding caches and local state."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parent.parent
output=root/"dist/Aetherloom-Server.zip"
output.parent.mkdir(exist_ok=True)
files=[root/x for x in ("compose.yaml",".dockerignore","LICENSE","THIRD_PARTY.md","DEPLOY.md")]
for directory in ("aetherloom","server"):
    files.extend(p for p in (root/directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix!=".pyc")
with ZipFile(output,"w",ZIP_DEFLATED) as z:
    for p in files:
        z.write(p,p.relative_to(root))
print(output)

