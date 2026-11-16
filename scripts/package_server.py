"""One Docker upload artifact under release; never copies client binaries."""
from pathlib import Path
import datetime,io,json,subprocess,tarfile,tomllib

root=Path(__file__).resolve().parent.parent
output=root/'release/Aetherloom-Server.tar.gz'
output.parent.mkdir(exist_ok=True)
files=[root/x for x in ('compose.yaml','compose.offline.yaml','.dockerignore','.env.example','LICENSE','THIRD_PARTY.md','DEPLOY.md','PLAY.md')]
files += [root/'scripts'/x for x in ('render_nginx.py','check_mysql.py')]
for directory in ('aetherloom','server'):
    files.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
with tarfile.open(output,'w:gz') as archive:
    for path in files:archive.add(path,arcname=path.relative_to(root),recursive=False)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    data=json.dumps({'version':tomllib.loads((root/'pyproject.toml').read_text())['project']['version'],
        'source_commit':commit,'built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2).encode()
    info=tarfile.TarInfo('BUILD_INFO.json');info.size=len(data);info.mode=0o644
    archive.addfile(info,io.BytesIO(data))
print(output)
