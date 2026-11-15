"""Create the minimal Docker upload bundle, excluding caches and local state."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import datetime,json,subprocess,tomllib

root=Path(__file__).resolve().parent.parent
output=root/"dist/Aetherloom-Server.zip"
output.parent.mkdir(exist_ok=True)
files=[root/x for x in ("compose.yaml","compose.offline.yaml",".dockerignore",".env.example","LICENSE","THIRD_PARTY.md","DEPLOY.md","PLAY.md")]
files += [root/'scripts'/x for x in ('render_nginx.py','check_mysql.py')]
for directory in ("aetherloom","server"):
    files.extend(p for p in (root/directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix!=".pyc")
with ZipFile(output,"w",ZIP_DEFLATED) as z:
    for p in files:
        z.write(p,p.relative_to(root))
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True)
    z.writestr('BUILD_INFO.json',json.dumps({'version':tomllib.loads((root/'pyproject.toml').read_text())['project']['version'],
        'source_commit':commit.stdout.strip() if commit.returncode==0 else None,
        'built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
print(output)

