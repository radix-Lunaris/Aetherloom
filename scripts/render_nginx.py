"""Render Nginx configuration from a private deployment profile; never print secrets."""
import argparse,json,re
from pathlib import Path
from urllib.parse import urlsplit

p=argparse.ArgumentParser()
p.add_argument('--profile',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--panel-port',type=int,default=38443)
p.add_argument('--api-port',type=int,default=47192)
a=p.parse_args()
profile=json.loads(a.profile.read_text(encoding='utf-8'))
domain=urlsplit(profile['api_url']).hostname or ''
path=profile['panel_path']
if not re.fullmatch(r'[a-z0-9.-]{1,253}',domain) or not re.fullmatch(r'[A-Za-z0-9]{16}',path):
    p.error('Invalid domain or panel path')
if not 1024<=a.panel_port<=65535:p.error('Panel port must be a high port')
if not 1024<=a.api_port<=65535 or a.api_port==a.panel_port:p.error('API requires a separate high port')
template=(Path(__file__).resolve().parent.parent/'server/nginx.conf.template').read_text(encoding='utf-8')
output=template.replace('__DOMAIN__',domain).replace('__PANEL_PATH__',path).replace('__PANEL_PORT__',str(a.panel_port))
output=output.replace('__API_PORT__',str(a.api_port))
with a.output.open('w',encoding='utf-8') as f:f.write(output)
print('Nginx configuration written; keep it private')
