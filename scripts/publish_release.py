"""Publish one verified iteration from dev without copying local artifacts.

Requires existing Git credentials. Secrets remain in memory; GitHub mutations
are restricted to this repository. Usage: python scripts/publish_release.py stage
then, after the same source commit passes CI, run with `publish`.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,tarfile,tomllib,urllib.request,urllib.parse,urllib.error
from PyInstaller.archive.readers import CArchiveReader

root=Path(__file__).resolve().parent.parent
repo='radix-Lunaris/Aetherloom'
parser=argparse.ArgumentParser();parser.add_argument('action',choices=['verify','stage','publish']);parser.add_argument('--branch',choices=['dev','experiment/java-agent'],default='dev')
args=parser.parse_args()
version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
experimental=bool(re.search(r'(?:a|b|rc)\d+$',version))
if args.branch=='experiment/java-agent' and not experimental:raise SystemExit('Experimental branch and prerelease version must match')
tag='v'+version
expected=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():
    raise SystemExit('Commit source changes before building/publishing')
folder=root/'release'
names=['Aetherloom.exe','Aetherloom-Server.tar.gz','SHA256SUMS.txt']
assets=[]
for name in names:
    path=folder/name
    if not path.is_file():raise SystemExit('Missing release artifact: '+name)
    assets.append({'name':name,'size':path.stat().st_size,'digest':'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()})
with tarfile.open(folder/names[1],'r:gz') as archive:
    server=json.load(archive.extractfile('BUILD_INFO.json'))
    if any(n=='.env' or '__pycache__' in n for n in archive.getnames()):raise SystemExit('Private/cache content in server artifact')
client_archive=CArchiveReader(str(folder/names[0]))
client=json.loads(client_archive.extract('BUILD_INFO.json').decode('utf-8-sig'))
for info in (client,server):
    if info['version']!=version or info['source_commit']!=expected:raise SystemExit('Build provenance mismatch; rebuild release')
if client.get('bundled_java') is not False:raise SystemExit('Unexpected Java bundle')
manifest=dict(line.split('  ',1)[::-1] for line in (folder/names[2]).read_text().splitlines() if line)
for asset in assets[:2]:
    if manifest.get(asset['name'])!=asset['digest'].removeprefix('sha256:'):raise SystemExit('SHA256SUMS mismatch')
if args.action=='verify':
    print(json.dumps({'tag':tag,'source_commit':expected,'artifacts':assets}));raise SystemExit(0)

credential=subprocess.run(['git','credential','fill'],cwd=root,input='protocol=https\nhost=github.com\npath='+repo+'.git\n\n',capture_output=True,text=True,timeout=30,check=True)
fields=dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
secret=fields.get('password')
if not secret:raise SystemExit('No existing Git credential; nothing published')

class ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        parts=urllib.parse.urlsplit(newurl)
        if parts.scheme!='https' or parts.hostname not in ('api.github.com','uploads.github.com') or not parts.path.startswith('/repos/'+repo+'/'):
            raise ValueError('Refusing credential redirect')
        return super().redirect_request(request,fp,code,msg,headers,newurl)

opener=urllib.request.build_opener(ScopedRedirect())
def api(path,body=None,method=None,data=None,ctype='application/json'):
    url=path if path.startswith('https://') else 'https://api.github.com/repos/'+repo+path
    parts=urllib.parse.urlsplit(url)
    if parts.scheme!='https' or parts.hostname not in ('api.github.com','uploads.github.com') or not parts.path.startswith('/repos/'+repo+'/'):
        raise ValueError('Unexpected repository/API scope')
    headers={'Authorization':'Bearer '+secret,'Accept':'application/vnd.github+json','User-Agent':'Aetherloom-release','X-GitHub-Api-Version':'2022-11-28'}
    if body is not None:data=json.dumps(body,ensure_ascii=False).encode('utf-8')
    if data is not None:headers['Content-Type']=ctype
    try:
        with opener.open(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=600) as response:
            raw=response.read();return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        try:message=json.load(error).get('message','Request rejected')
        except Exception:message='Request rejected'
        raise RuntimeError('GitHub API '+str(error.code)+': '+str(message)) from None

if api('/branches/'+urllib.parse.quote(args.branch,safe=''))['commit']['sha']!=expected:raise SystemExit('Remote source branch moved; reconcile before release')
tag_commit=subprocess.check_output(['git','rev-parse',tag+'^{commit}'],cwd=root,text=True).strip()
if tag_commit!=expected:raise SystemExit('Tag differs from verified source')
remote_tag=subprocess.check_output(['git','ls-remote','origin','refs/tags/'+tag+'^{}','refs/tags/'+tag],cwd=root,text=True)
if expected not in remote_tag:raise SystemExit('Push the matching annotated tag before staging')
release=next((r for r in api('/releases?per_page=100') if r['tag_name']==tag),None)
if args.action=='stage':
    if release and not release['draft']:raise SystemExit('Published versions are immutable; increment version')
    if not release:
        release=api('/releases',{'tag_name':tag,'target_commitish':expected,'name':'Aetherloom '+tag,
            'body':(root/'RELEASE_NOTES.md').read_text(encoding='utf-8')+'\n\nSource commit: `'+expected+'`','draft':True,'prerelease':experimental},method='POST')
    for asset in assets:
        old=next((a for a in release['assets'] if a['name']==asset['name']),None)
        if old and old.get('digest')==asset['digest'] and old['size']==asset['size']:continue
        if old:api('/releases/assets/'+str(old['id']),method='DELETE')
        upload=release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':asset['name']})
        uploaded=api(upload,method='POST',data=(folder/asset['name']).read_bytes(),ctype='application/octet-stream')
        if uploaded.get('digest')!=asset['digest'] or uploaded['size']!=asset['size'] or uploaded['state']!='uploaded':raise RuntimeError('Upload verification failed')
        print('Verified upload:',asset['name'],flush=True)
else:
    if not release:raise SystemExit('Stage the release first')
    runs=api('/actions/runs?'+urllib.parse.urlencode({'branch':args.branch,'per_page':20}))['workflow_runs']
    if not any(r['head_sha']==expected and r['name']=='Core checks' and r['conclusion']=='success' for r in runs):raise SystemExit('Verified source CI has not succeeded; draft preserved')
    for asset in assets:
        old=next((a for a in release['assets'] if a['name']==asset['name']),None)
        if not old or old.get('digest')!=asset['digest'] or old['size']!=asset['size']:raise RuntimeError('Draft artifact mismatch')
    if release['draft']:release=api('/releases/'+str(release['id']),{'draft':False,'prerelease':experimental,'make_latest':'false' if experimental else 'true'},method='PATCH')
release=api('/releases/'+str(release['id']))
receipt={'tag':tag,'source_commit':expected,'branch':args.branch,'prerelease':release['prerelease'],'url':release['html_url'],'draft':release['draft'],'published_at':release['published_at'],
         'assets':[{'name':a['name'],'size':a['size'],'digest':a.get('digest'),'url':a['browser_download_url']} for a in release['assets']]}
(root/'.local').mkdir(exist_ok=True)
(root/'.local'/('release-'+tag+'.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({'url':receipt['url'],'draft':receipt['draft'],'source_commit':expected,'verified_asset_count':len(receipt['assets'])}))
