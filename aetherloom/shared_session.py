"""Managed Host/Player lifecycle; only Bridge-confirmed closed saves may commit."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from .bridge_control import BridgeControl
from .cloud import API,CloudWorld,LeaseGuard
from .launcher import launch,offline_uuid
from .network import Network
from .world_lock import closed_world


def assets():
    base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
    return base/'assets'


def repair(world,java,identity,saved=False):
    helper=assets()/'aetherloom-playerdata.jar'
    if not helper.is_file():raise ValueError('交付包缺少玩家数据辅助模块，禁止共享开服')
    with closed_world(world):
        result=subprocess.run([java,'-Xmx128M','-jar',str(helper),'saved' if saved else 'prepare',str(world),str(uuid.UUID(identity))],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        if result.returncode:raise ValueError('玩家数据检查失败：'+(result.stderr or result.stdout).strip())


class SharedSession:
    def __init__(self,url,token,cache,room,binding,notify,confirm_recovery=False):
        self.api=API(url,token);self.cloud=CloudWorld(self.api,cache)
        self.room,self.binding,self.notify=room,binding,notify
        self.confirm_recovery=confirm_recovery;self.process=None;self.stop=False
        self.path_states={}
        def status(state):
            if state.get('channel')!='data':return
            path=state.get('active_path')
            if self.path_states.get(state['session_id'])!=path:
                self.path_states[state['session_id']]=path
                self.notify('status','联机路径：'+{'relay':'中继','direct':'已验证P2P直连','reconnecting':'正在重连','none':'通道已关闭'}.get(path,str(path)))
        self.network=Network(url,token,self.api,on_status=status)
        self.bridge=None;self.guard=None

    def game(self,**kwargs):
        b=self.binding
        process=launch(b['root'],b['version'],b['java'],b['name'],b['run'],int(b['memory']),before_start=self.guard.check if self.guard else None,managed=True,**kwargs)
        self.process=process;self.notify('process',process)
        return process

    async def run(self):
        base='/api/rooms/'+self.room
        try:
            items=await asyncio.to_thread(self.api,'/api/rooms')
            room=next((r for r in items if r['id']==self.room),None)
            if not room:raise ValueError('共享房间不存在')
            if room['host'] and room['expires']>time.time():
                if room['state']!='ready':raise ValueError('Host正在准备或上传，请稍后刷新')
                await asyncio.to_thread(self.api,base+'/join',{})
                port=await self.network.listen(self.room)
                self.notify('status','已建立本地联机代理，正在启动加入游戏')
                b=self.binding
                jar=assets()/'aetherloom-bridge-0.1.0.jar'
                if not jar.is_file():raise ValueError('交付包缺少Forge联机Bridge')
                mods=Path(b['run'])/'mods';mods.mkdir(exist_ok=True);shutil.copy2(jar,mods/jar.name)
                self.bridge=BridgeControl(b['world'],offline_uuid(b['name']),join='127.0.0.1:'+str(port),config_dir=Path(b['run'])/'.aetherloom/control')
                await asyncio.to_thread(self.game,bridge_file=self.bridge.config)
                deadline=time.monotonic()+180
                while not self.bridge.ready.is_set():
                    if self.bridge.error:raise ValueError(self.bridge.error)
                    if self.stop:return
                    if self.process.poll() is not None or time.monotonic()>deadline:raise ValueError('玩家未能自动加入，请查看Forge握手日志')
                    await asyncio.sleep(.25)
                self.notify('status','已自动加入共享世界')
                checked=0
                while self.process.poll() is None and not self.stop:
                    if time.monotonic()-checked>5:
                        await asyncio.to_thread(self.api,base+'/membership')
                        current=next((r for r in await asyncio.to_thread(self.api,'/api/rooms') if r['id']==self.room),None)
                        if not current or current['epoch']!=room['epoch'] or current['expires']<=time.time() or current['state']!='ready':
                            self.notify('status','Host会话已结束，联机通道已关闭；请等待保存后重新开始')
                            return
                        checked=time.monotonic()
                    await asyncio.sleep(.5)
                return
            b=self.binding;world=Path(b['world']).resolve()
            if (world/'.aetherloom/pending-session.json').exists():
                raise ValueError('此设备保留未处理的Host会话，请先提交恢复候选或另选绑定目录，禁止覆盖旧进度')
            bridge_jar=assets()/'aetherloom-bridge-0.1.0.jar'
            if not bridge_jar.is_file():raise ValueError('交付包缺少Forge游戏Bridge，禁止把空房间标记为就绪')
            if world.parent!=(Path(b['run']).resolve()/'saves'):
                raise ValueError('共享世界必须位于所选运行目录的saves下，请重新绑定')
            from .launcher import manifest
            descriptor=manifest(Path(b['root']),b['version'])
            libraries=[item['name'] for item in descriptor.get('libraries',[])]
            if not any(name.startswith('net.minecraftforge:forge:1.20.1-47.4.22') for name in libraries):
                args=descriptor.get('arguments',{}).get('game',[])
                if not ('1.20.1' in args and '47.4.22' in args):
                    raise ValueError('共享Host首版需要Minecraft 1.20.1 / Forge 47.4.22；普通启动不受此限制')
            lease=await asyncio.to_thread(self.api,base+'/claim',{'confirm_recovery':self.confirm_recovery})
            self.guard=LeaseGuard(self.api,self.room,lease)
            credentials=self.guard.lease
            pending=world/'.aetherloom/pending-session.json'
            try:
                self.notify('status','正在校验并同步云端权威存档')
                head=await asyncio.to_thread(self.cloud.download,self.room,world)
                if head!=lease['head']:raise ValueError('云端版本与租约基准不一致')
                identity=offline_uuid(b['name'])
                await asyncio.to_thread(repair,world,b['java'],identity)
                mods=Path(b['run'])/'mods';mods.mkdir(exist_ok=True)
                shutil.copy2(bridge_jar,mods/bridge_jar.name)
                self.bridge=BridgeControl(world,identity)
                pending.parent.mkdir(parents=True,exist_ok=True)
                pending.write_text(json.dumps({'room':self.room,'parent':head,'epoch':lease['epoch'],'identity':identity,'state':'loading'}),encoding='utf-8')
                self.guard.check()
                await asyncio.to_thread(self.game,quick_play=('Singleplayer',world.name),bridge_file=self.bridge.config)
                deadline=time.monotonic()+180
                while not self.bridge.ready.is_set():
                    if self.bridge.error:raise ValueError(self.bridge.error)
                    self.guard.check()
                    if self.stop:self.bridge.stop=True
                    if self.process.poll() is not None or time.monotonic()>deadline:raise ValueError('游戏未报告世界/LAN就绪，本地数据保留，请检查游戏日志')
                    await asyncio.sleep(.25)
                self.guard.check()
                host_task=self.network.spawn(self.network.host(self.room,self.bridge.port))
                await asyncio.to_thread(self.api,base+'/ready',credentials)
                self.notify('status','共享世界已就绪 · 当前使用中继通道')
                while not self.bridge.saved.is_set():
                    self.guard.check()
                    if self.stop:self.bridge.stop=True
                    if self.process.poll() is not None:raise ValueError('Host未报告正常保存，保留本地待恢复数据，云端版本未改变')
                    await asyncio.sleep(.25)
                host_task.cancel();await self.network.close()
                await asyncio.to_thread(self.api,base+'/uploading',credentials)
                self.notify('status','游戏已保存，正在等待存档关闭并上传')
                deadline=time.monotonic()+30
                while True:
                    try:
                        await asyncio.to_thread(repair,world,b['java'],identity,True)
                        break
                    except ValueError as e:
                        if '仍被游戏占用' not in str(e) or time.monotonic()>deadline:raise
                        await asyncio.sleep(.25)
                self.guard.check()
                version=await asyncio.to_thread(self.cloud.upload,self.room,world,credentials,head)
                pending.unlink(missing_ok=True)
                self.notify('status','最终存档上传成功，下一位玩家现在可以接管 · '+version[:10])
            except BaseException:
                if self.bridge:
                    self.bridge.stop=True
                    deadline=time.monotonic()+10
                    while self.process and self.process.poll() is None and not self.bridge.saved.is_set() and time.monotonic()<deadline:
                        await asyncio.sleep(.25)
                    if self.process and self.process.poll() is None and not self.bridge.saved.is_set():
                        self.process.terminate()
                if not self.process:
                    # No game process was created, so no world could have been loaded.
                    await asyncio.to_thread(self.api,base+'/cancel',credentials)
                raise
        finally:
            await self.network.close()
            if self.guard:self.guard.close()
            if self.bridge:await asyncio.to_thread(self.bridge.close)


class OfflineInspection(SharedSession):
    """Keep the interrupted original; inspect a copy without publishing LAN."""
    async def run(self):
        source=Path(self.binding['world']).resolve()
        pending=source/'.aetherloom/pending-session.json'
        if not pending.is_file():raise ValueError('此绑定目录没有待恢复的Host会话')
        original=json.loads(pending.read_text(encoding='utf-8'))
        identity=offline_uuid(self.binding['name'])
        if original['identity']!=identity:raise ValueError('离线检查需要使用原Host的离线游戏身份；请先调整并重新绑定')
        if original.get('candidate'):raise ValueError('恢复候选已上传：'+original['candidate']+'，请等待实例管理员审批')
        world=source.parent/('Aetherloom-Recovery-'+uuid.uuid4().hex)
        def copy():
            with closed_world(source):
                if any(p.is_symlink() for p in source.rglob('*')):raise ValueError('恢复存档包含符号链接，拒绝复制')
                shutil.copytree(source,world,ignore=shutil.ignore_patterns('.aetherloom','session.lock'))
        await asyncio.to_thread(copy)
        self.notify('status','已保留原始存档；正在打开独立离线检查副本，不开LAN、不占Host')
        jar=assets()/'aetherloom-bridge-0.1.0.jar'
        if not jar.is_file():raise ValueError('缺少游戏Bridge')
        mods=Path(self.binding['run'])/'mods';mods.mkdir(exist_ok=True);shutil.copy2(jar,mods/jar.name)
        self.bridge=BridgeControl(world,identity,inspect=True)
        try:
            await asyncio.to_thread(self.game,quick_play=('Singleplayer',world.name),bridge_file=self.bridge.config)
            deadline=time.monotonic()+180
            while not self.bridge.ready.is_set():
                if self.bridge.error:raise ValueError(self.bridge.error)
                if self.process.poll() is not None or time.monotonic()>deadline:raise ValueError('离线检查未加载，原始数据与检查副本均保留')
                await asyncio.sleep(.25)
            self.notify('status','请检查恢复世界；正常保存退出后只上传恢复候选，等待管理员审批')
            while not self.bridge.saved.is_set():
                if self.stop:self.bridge.stop=True
                if self.process.poll() is not None:raise ValueError('检查副本未正常保存，不能上传候选')
                await asyncio.sleep(.25)
            deadline=time.monotonic()+30
            while True:
                try:await asyncio.to_thread(repair,world,self.binding['java'],identity,True);break
                except ValueError as e:
                    if '仍被游戏占用' not in str(e) or time.monotonic()>deadline:raise
                    await asyncio.sleep(.25)
            candidate=await asyncio.to_thread(self.cloud.candidate,self.room,world,original.get('parent'))
            original['candidate']=candidate;original['inspection']=str(world)
            pending.write_text(json.dumps(original),encoding='utf-8')
            self.notify('status','恢复候选已上传，权威存档未改变；请Owner或实例管理员审批 · '+candidate[:12])
        finally:
            await asyncio.to_thread(self.bridge.close)
