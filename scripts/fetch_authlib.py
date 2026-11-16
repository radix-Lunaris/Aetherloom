"""Fetch the pinned, unmodified authlib-injector only at build time."""
from pathlib import Path
import hashlib,urllib.request

SHA256='9c7f4343e6c82034958ffb48c14a2cb0c85928be7283103ce17da00c6d5a7b10'
URL='https://authlib-injector.yushi.moe/artifact/56/authlib-injector-1.2.8.jar'

def fetch():
    root=Path(__file__).resolve().parent.parent;target=root/'assets/authlib-injector.jar'
    target.parent.mkdir(exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==SHA256:return target
    with urllib.request.urlopen(URL,timeout=60) as response:data=response.read(4*1024*1024)
    if hashlib.sha256(data).hexdigest()!=SHA256:raise ValueError('Pinned authlib-injector SHA-256 mismatch')
    temp=target.with_suffix('.part');temp.write_bytes(data);temp.replace(target)
    print('Verified authlib-injector 1.2.8');return target

if __name__=='__main__':fetch()
