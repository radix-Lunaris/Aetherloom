"""LittleSkin game accounts, separate from Aetherloom software credentials."""
from dataclasses import dataclass,field
import json,os,re,secrets,threading,urllib.request,urllib.error,uuid
from pathlib import Path

ISSUER='https://littleskin.cn/api/yggdrasil'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('LittleSkin认证请求不允许重定向')

def request(path,body=None):
    if path and not re.fullmatch(r'/authserver/(authenticate|refresh|invalidate)',path):raise ValueError('Unknown authentication endpoint')
    query=urllib.request.Request(ISSUER+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','User-Agent':'Aetherloom'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(query,timeout=25) as response:
            data=response.read(256*1024+1)
            if len(data)>256*1024:raise ValueError('LittleSkin响应过大')
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as error:
        # Never echo a provider response that might contain credentials.
        raise ValueError('LittleSkin登录失败或授权过期（HTTP '+str(error.code)+'），请检查账号并重新登录') from None
    except (OSError,urllib.error.URLError):raise ValueError('无法连接LittleSkin，请检查网络后重试') from None

def profile(value):
    name=value['name'];identity=uuid.UUID(value['id']).hex
    if not isinstance(name,str) or not re.fullmatch(r'[\w,\-.\[\]{}+=^]{1,16}',name) or len(name.encode('utf-16-le'))>32 or uuid.UUID(identity).int==0:raise ValueError('LittleSkin角色信息无效')
    return {'id':identity,'name':name}

@dataclass(frozen=True)
class GameAuth:
    name:str
    uuid:str
    access_token:str=field(repr=False)
    metadata:dict=field(repr=False)
    issuer:str=ISSUER

    def __post_init__(self):
        profile({'name':self.name,'id':self.uuid})
        if self.issuer!=ISSUER or not isinstance(self.access_token,str) or not self.access_token:raise ValueError('无效的LittleSkin游戏授权')

def dpapi(data,decrypt=False):
    """Current-user Windows DPAPI; never fall back to plaintext."""
    if os.name!='nt':raise ValueError('此平台仅支持会话内登录，不保存游戏令牌')
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    function=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('Windows无法解锁或保存LittleSkin登录，请重新登录')
    try:return ctypes.string_at(target.data,target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)

class GameAccounts:
    def __init__(self,directory,api=request,protect=dpapi):
        self.path=Path(directory)/'game-accounts.bin';self.api=api;self.protect=protect
        self.rows={};self.lock=threading.RLock();self.refresh_lock=threading.Lock();self.load_error=None
        if self.path.exists():
            try:self.rows=json.loads(self.protect(self.path.read_bytes(),True))
            except Exception:self.load_error='无法读取LittleSkin登录存储，请重新登录；原文件保留'

    def save(self):
        if os.name!='nt' and self.protect is dpapi:return
        encrypted=self.protect(json.dumps(self.rows).encode(),False)
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
        temp.write_bytes(encrypted);os.replace(temp,self.path)

    def login(self,username,password):
        result=self.api('/authserver/authenticate',{'username':username,'password':password,'agent':{'name':'Minecraft','version':1},'clientToken':secrets.token_hex(16),'requestUser':True})
        if not result.get('accessToken') or not result.get('clientToken'):raise ValueError('LittleSkin未返回有效授权')
        profiles=[profile(p) for p in result.get('availableProfiles',[])]
        if result.get('selectedProfile') and profile(result['selectedProfile']) not in profiles:profiles.append(profile(result['selectedProfile']))
        if not profiles:raise ValueError('此LittleSkin账号没有游戏角色，请先在LittleSkin创建角色')
        return result,profiles

    def add(self,result,selected):
        with self.refresh_lock:return self._add(result,selected)

    def _add(self,result,selected):
        selected=profile(selected)
        if result.get('selectedProfile') and profile(result['selectedProfile'])!=selected:raise ValueError('请重新登录以选择其他LittleSkin角色')
        if not result.get('selectedProfile'):
            result=self.api('/authserver/refresh',{'accessToken':result['accessToken'],'clientToken':result['clientToken'],'selectedProfile':selected,'requestUser':True})
        actual=profile(result['selectedProfile'])
        if actual!=selected:raise ValueError('LittleSkin返回的角色与选择不一致')
        with self.lock:
            key=next((k for k,row in self.rows.items() if row['profile']['id']==selected['id']),uuid.uuid4().hex)
            self.rows[key]={'profile':selected,'accessToken':result['accessToken'],'clientToken':result['clientToken']}
            self.save();return key

    def public(self,key):
        with self.lock:
            if key not in self.rows:raise ValueError('LittleSkin角色未登录，请添加账号后重新绑定')
            return dict(self.rows[key]['profile'])

    def remove(self,key):
        with self.refresh_lock:
            with self.lock:row=self.rows.get(key)
            if not row:return
            try:self.api('/authserver/invalidate',{'accessToken':row['accessToken'],'clientToken':row['clientToken']})
            except ValueError:pass
            with self.lock:self.rows.pop(key,None);self.save()

    def refresh(self,key,expected_name,expected_uuid):
        with self.refresh_lock:
            current=self.public(key)
            if current!={'name':expected_name,'id':uuid.UUID(expected_uuid).hex}:raise ValueError('LittleSkin角色与实例绑定不同，请重新绑定，不会按昵称合并玩家数据')
            with self.lock:row=dict(self.rows[key])
            result=self.api('/authserver/refresh',{'accessToken':row['accessToken'],'clientToken':row['clientToken'],'requestUser':True})
            updated=profile(result['selectedProfile'])
            if updated['id']!=current['id']:raise ValueError('LittleSkin授权角色UUID发生变化，拒绝启动')
            row.update(accessToken=result['accessToken'],clientToken=result['clientToken'],profile=updated)
            with self.lock:self.rows[key]=row;self.save()
            if updated!=current:raise ValueError('LittleSkin角色已改名，请重新绑定实例')
            metadata=self.api('')
            if not isinstance(metadata.get('skinDomains'),list) or not metadata.get('signaturePublickey'):raise ValueError('LittleSkin皮肤服务元数据无效')
            return GameAuth(updated['name'],updated['id'],row['accessToken'],metadata)
