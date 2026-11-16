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
from .launcher import launch,offline_uuid,game_uuid
from .network import Network
from .world_lock import closed_world
from .runtime import hidden_process
from .environment import describe,validate


def assets():
    base=Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent)) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
    return base/'assets'


def repair(world,java,identity,saved=False):
    helper=assets()/'aetherloom-playerdata.jar'
    if not helper.is_file():raise ValueError('交付包缺少玩家数据辅助模块，禁止共享开服')
    with closed_world(world):
        result=subprocess.run([java,'-Xmx128M','-jar',str(helper),'saved' if saved else 'prepare',str(world),str(uuid.UUID(identity))],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90,**hidden_process())
        if result.returncode:raise ValueError('玩家数据检查失败：'+(result.stderr or result.stdout).strip())


class SharedSession:
    def __init__(self,url,token,cache,room,binding,notify,confirm_recovery=False):
        self.api=API(url,token);self.cloud=CloudWorld(self.api,cache,progress=lambda text:notify('status',text),on_progress=lambda state:notify('progress',state))
        self.room,self.binding,self.notify=room,binding,notify
        self.confirm_recovery=confirm_recovery;self.process=None;self.stop=False
        self.path_states={};self.data_states={}
        self.session_info={'room':room,'role':'待确认','phase':'created','mode':'AUTO','host':None,'epoch':None,'lan_port':None,'players':0,'message':'尚未开始连接'}
        self.start_timeout=max(120,min(1800,int(binding.get('launch_timeout',900))))
        def status(state):
            self.notify('network',state)
            if state.get('channel')!='data':return
            self.data_states[state['session_id']]=state
            peers={entry.get('peer') for entry in self.data_states.values() if entry.get('switch_phase')!='ended' and (entry.get('relay_ready') or entry.get('direct_ready'))}
            if self.session_info['phase'] in ('ready','active'):
                phase='active' if peers or self.session_info['role']=='Player' else 'ready'
                self.state(phase,players=len(peers))
            path=state.get('active_path')
            if self.path_states.get(state['session_id'])!=path:
                self.path_states[state['session_id']]=path
                self.notify('status','联机路径：'+{'relay':'中继','direct':'已验证P2P直连','reconnecting':'正在重连','none':'通道已关闭'}.get(path,str(path)))
        self.network=Network(url,token,self.api,on_status=status)
        self.bridge=None;self.guard=None

    def state(self,phase,**fields):
        self.session_info.update(fields,phase=phase)
        self.notify('session',dict(self.session_info))

    def game(self,**kwargs):
        b=self.binding
        process=launch(b['root'],b['version'],b['java'],b['name'],b['run'],int(b['memory']),custom_uuid=b.get('uuid'),before_start=self.guard.check if self.guard else None,managed=True,**kwargs)
        self.process=process;self.notify('process',process)
        return process

    async def prepare_java(self):
        if self.binding.get('java_mode')=='auto':
            from .runtime import find_runtimes,required_java,choose_java
            from .launcher import manifest
            b=self.binding
            self.notify('status','正在为共享实例自动选择 Java')
            required=required_java(manifest(Path(b['root']),b['version']))
            runtimes=await asyncio.to_thread(find_runtimes,b['root'],self.cloud.cache.root.parent/'java',known=[b.get('java')])
            best=choose_java(runtimes,required)
            if not best:raise ValueError(f'共享实例需要 Java {required} x64，请先在本地游戏中下载推荐运行时')
            b['java']=best.path

    async def run(self):
        base='/api/rooms/'+self.room
        try:
            self.state('preflight',message='正在检查本地环境、账号权限和云端权威版本')
            await self.prepare_java()
            self.notify('status','正在核验房间权限和权威版本信息')
            items=await asyncio.to_thread(self.api,'/api/rooms')
            room=next((r for r in items if r['id']==self.room),None)
            if not room:raise ValueError('共享房间不存在')
            self.state('preflight',host=room.get('host'),mode=room.get('mode','AUTO'),epoch=room.get('epoch'))
            validate(describe(self.binding['root'],self.binding['version']),room.get('environment'))
            await asyncio.to_thread(self.api,base+'/join',{})
            head_info=await asyncio.to_thread(self.api,base+'/head')
            if not head_info.get('version'):raise ValueError('此房间尚未发布权威存档')
            self.notify('status','权威版本已确认 '+head_info['version'][:10]+'，正在确认 Host 身份')
            if room['host'] and room['expires']>time.time():
                if room['state']!='ready':raise ValueError('Host正在准备或上传，列表会自动更新，请稍后再在线启动')
                self.state('connecting',role='Player',message='发现现有Host，正在建立本地代理')
                port=await self.network.listen(self.room,{'name':self.binding['name'],'uuid':game_uuid(self.binding['name'],self.binding.get('uuid'))})
                self.notify('status','已建立本地联机代理，正在启动加入游戏')
                b=self.binding
                jar=assets()/'aetherloom-bridge-0.1.0.jar'
                if not jar.is_file():raise ValueError('交付包缺少Forge联机Bridge')
                mods=Path(b['run'])/'mods';mods.mkdir(exist_ok=True);shutil.copy2(jar,mods/jar.name)
                self.bridge=BridgeControl(b['world'],game_uuid(b['name'],b.get('uuid')),join='127.0.0.1:'+str(port),config_dir=Path(b['run'])/'.aetherloom/control')
                self.state('loading',message='正在启动游戏；等待Forge入服确认')
                await asyncio.to_thread(self.game,bridge_file=self.bridge.config)
                deadline=time.monotonic()+self.start_timeout
                while not self.bridge.ready.is_set():
                    if self.bridge.error:raise ValueError(self.bridge.error)
                    if self.stop:return
                    if self.process.poll() is not None or time.monotonic()>deadline:raise ValueError('玩家未能自动加入，请查看Forge握手日志')
                    await asyncio.sleep(.25)
                self.state('active',message='已自动加入Host共享世界')
                self.notify('status','已自动加入共享世界')
                checked=0
                while self.process.poll() is None and not self.stop:
                    if time.monotonic()-checked>5:
                        await asyncio.to_thread(self.api,base+'/membership')
                        current=next((r for r in await asyncio.to_thread(self.api,'/api/rooms') if r['id']==self.room),None)
                        if not current or current['epoch']!=room['epoch'] or current['expires']<=time.time() or current['state']!='ready':
                            self.state('ended',message='Host已结束，正在关闭当前Player游戏')
                            self.notify('status','Host会话已结束，联机通道已关闭；请等待保存后重新开始')
                            return
                        checked=time.monotonic()
                    await asyncio.sleep(.5)
                self.state('complete',message='Player已退出，不上传共同世界')
                return
            b=self.binding;world=Path(b['world']).resolve()
            if (world/'.aetherloom/pending-session.json').exists():
                raise ValueError('此设备保留未处理的Host会话，请先提交恢复候选或另选绑定目录，禁止覆盖旧进度')
            bridge_jar=assets()/'aetherloom-bridge-0.1.0.jar'
            if not bridge_jar.is_file():raise ValueError('交付包缺少Forge游戏Bridge，禁止把空房间标记为就绪')
            if world.parent!=(Path(b['run']).resolve()/'saves'):
                raise ValueError('共享世界必须位于所选运行目录的saves下，请重新绑定')
            self.notify('status','正在申请唯一 Host 租约')
            self.state('claiming',role='Host候选',message='正在原子申请唯一Host租约')
            lease=await asyncio.to_thread(self.api,base+'/claim',{'confirm_recovery':self.confirm_recovery})
            self.state('syncing',role='Host',epoch=lease['epoch'],message='租约已取得，正在同步权威世界')
            self.guard=LeaseGuard(self.api,self.room,lease)
            credentials=self.guard.lease
            pending=world/'.aetherloom/pending-session.json'
            try:
                self.notify('status','正在校验并同步云端权威存档')
                head=await asyncio.to_thread(self.cloud.download,self.room,world)
                if head!=lease['head']:raise ValueError('云端版本与租约基准不一致')
                identity=game_uuid(b['name'],b.get('uuid'))
                self.notify('status','权威存档同步完成，正在校验玩家数据并启动世界')
                await asyncio.to_thread(repair,world,b['java'],identity)
                mods=Path(b['run'])/'mods';mods.mkdir(exist_ok=True)
                shutil.copy2(bridge_jar,mods/bridge_jar.name)
                self.bridge=BridgeControl(world,identity,game_name=b['name'])
                pending.parent.mkdir(parents=True,exist_ok=True)
                pending.write_text(json.dumps({'room':self.room,'parent':head,'epoch':lease['epoch'],'identity':identity,'state':'loading'}),encoding='utf-8')
                self.guard.check()
                self.state('loading',message='正在加载指定世界，等待Bridge与LAN就绪')
                await asyncio.to_thread(self.game,quick_play=('Singleplayer',world.name),bridge_file=self.bridge.config)
                deadline=time.monotonic()+self.start_timeout
                while not self.bridge.ready.is_set():
                    if self.bridge.error:raise ValueError(self.bridge.error)
                    self.guard.check()
                    if self.stop:self.bridge.stop=True
                    if self.process.poll() is not None or time.monotonic()>deadline:raise ValueError('游戏未报告世界/LAN就绪，本地数据保留，请检查游戏日志')
                    await asyncio.sleep(.25)
                self.guard.check()
                host_task=self.network.spawn(self.network.host(self.room,self.bridge.port,on_identity=self.bridge.register_peer))
                await asyncio.to_thread(self.api,base+'/ready',credentials)
                self.state('ready',lan_port=self.bridge.port,message='Host世界与LAN已就绪，等待其他玩家连接；尚无隧道流时不会显示已中继或已直连')
                self.notify('status','Host已就绪，正在等待其他玩家连接')
                while not self.bridge.saved.is_set():
                    self.guard.check()
                    if self.stop:self.bridge.stop=True
                    if self.process.poll() is not None:raise ValueError('Host未报告正常保存，保留本地待恢复数据，云端版本未改变')
                    await asyncio.sleep(.25)
                self.state('saving',message='已收到正常保存事件，正在结束联机通道')
                host_task.cancel();await self.network.close()
                await asyncio.to_thread(self.api,base+'/uploading',credentials)
                self.state('uploading',message='等待文件锁释放并增量上传最终存档')
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
                self.state('complete',players=0,message='最终存档已确认上传，Host租约已释放')
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
        except BaseException as error:
            self.state('failed',message=str(error) or '会话已取消；保留本地数据')
            raise
        finally:
            if self.bridge and self.process and self.process.poll() is None:
                # Bridge performs normal disconnect/save, then exits Minecraft.
                self.bridge.stop=True
                deadline=time.monotonic()+15
                while self.process.poll() is None and time.monotonic()<deadline:
                    await asyncio.sleep(.25)
                if self.process.poll() is None:
                    self.notify('status','游戏仍在结束，请等待；不会强杀可能正在保存的进程')
            await self.network.close()
            if self.guard:self.guard.close()
            if self.bridge:await asyncio.to_thread(self.bridge.close)
            if self.session_info['phase'] not in ('failed','complete','ended'):
                self.state('ended',players=0,message='共享会话已结束')


class OfflineInspection(SharedSession):
    """Keep the interrupted original; inspect a copy without publishing LAN."""
    async def run(self):
        self.state('inspection',role='离线恢复检查',message='不占Host、不建立LAN或隧道')
        await self.prepare_java()
        source=Path(self.binding['world']).resolve()
        pending=source/'.aetherloom/pending-session.json'
        if not pending.is_file():raise ValueError('此绑定目录没有待恢复的Host会话')
        original=json.loads(pending.read_text(encoding='utf-8'))
        identity=game_uuid(self.binding['name'],self.binding.get('uuid'))
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
            deadline=time.monotonic()+self.start_timeout
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
            self.state('complete',message='恢复候选已上传，等待管理员审批')
            self.notify('status','恢复候选已上传，权威存档未改变；请Owner或实例管理员审批 · '+candidate[:12])
        finally:
            await asyncio.to_thread(self.bridge.close)
