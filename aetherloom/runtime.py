"""Java discovery and compatibility without depending on another launcher."""
import os
from pathlib import Path
import re
import subprocess
import platform
import functools
import itertools
import concurrent.futures
from dataclasses import dataclass


def hidden_process():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def java_major(java):
    result = subprocess.run([str(java), '-version'], capture_output=True, text=True,
                            errors='replace', timeout=10, **hidden_process())
    match = re.search(r'version "(\d+)(?:\.(\d+))?', result.stderr + result.stdout)
    if result.returncode or not match:
        raise ValueError('无法读取 Java 版本')
    return int(match[2] if match[1] == '1' else match[1])


def discover_java(root, required=17):
    """Known layouts only, depth <= 5, <= 2048 directories, no links or PATH scan.

    Never runs arbitrary executables found while browsing: candidates must have a
    Java release descriptor alongside bin/java. Manual paths remain available.
    """
    root = Path(root).resolve()
    if not root.is_dir(): return []
    found = []
    pending = [(root, 0)]
    visited = 0
    while pending and visited < 2048:
        folder, depth = pending.pop(0)
        visited += 1
        binary = folder / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        release = folder / 'release'
        if binary.is_file() and release.is_file() and not binary.is_symlink():
            try:
                metadata = release.read_text(encoding='utf-8', errors='replace')
                version = re.search(r'JAVA_VERSION="(\d+)(?:\.(\d+))?', metadata)
                major = int(version[2] if version[1] == '1' else version[1]) if version else 0
                if major >= required:
                    found.append((major, str(binary)))
                continue
            except (OSError, ValueError): pass
        if depth >= 5: continue
        try:
            for child in sorted(folder.iterdir()):
                if visited+len(pending)>=2048:break
                if child.is_symlink() or (hasattr(child, 'is_junction') and child.is_junction()): continue
                if not child.is_dir(): continue
                if depth == 0 and not (any(word in child.name.lower() for word in ('java','jdk','jre','runtime','temurin','mojang','loom','graal','corretto','zulu','liberica','windows-','linux-','mac-')) or child.name[:1].isdigit()): continue
                if child.name.lower() in ('saves','assets','libraries','mods','versions','.git'): continue
                if root not in child.resolve().parents: continue
                pending.append((child, depth + 1))
        except OSError: continue
    return [path for _, path in sorted(found, key=lambda item: (item[0] != required, item[0], item[1]))]


@dataclass(frozen=True)
class JavaRuntime:
    path: str
    version: str
    major: int
    bits: int
    architecture: str
    vendor: str = ''
    source: str = ''
    experimental: bool = False


def required_java(manifest):
    """Prefer the installed manifest's declaration; conservative release fallback."""
    value=manifest.get('javaVersion',{}).get('majorVersion')
    if isinstance(value,int) and 8<=value<=99:return value
    # Forge merged manifests may use a friendly client id.
    args=manifest.get('arguments',{}).get('game',[])
    version=manifest.get('_client',manifest.get('id',''))
    if '--fml.mcVersion' in args:
        index=args.index('--fml.mcVersion')
        if index+1<len(args):version=args[index+1]
    for item in manifest.get('libraries',[]):
        name=item.get('name','')
        if name.startswith('net.minecraftforge:forge:'):version=name.split(':')[2].split('-')[0]
    match=re.fullmatch(r'(\d+)\.(\d+)(?:\.(\d+))?',str(version))
    if not match:raise ValueError('版本未声明 Java 要求，无法自动判断；请在外部补全版本元数据')
    number=tuple(int(n or 0) for n in match.groups())
    if number>=(26,1,0):return 25
    if number>=(1,20,5):return 21
    if number>=(1,18,0):return 17
    if number>=(1,17,0):return 16
    return 8


def _probe(path):
    result=subprocess.run([path,'-XshowSettings:properties','-version'],capture_output=True,
                          text=True,errors='replace',timeout=4,**hidden_process())
    text=result.stdout+'\n'+result.stderr
    props=dict(re.findall(r'^\s*([\w.]+)\s*=\s*(.*?)\s*$',text,re.M))
    version=props.get('java.version')
    if not version:
        match=re.search(r'version "([^\"]+)"',text)
        version=match[1] if match else ''
    match=re.match(r'(\d+)(?:\.(\d+))?',version)
    if result.returncode or not match:raise ValueError('无法执行或识别 Java：'+path)
    major=int(match[2] if match[1]=='1' else match[1])
    arch=props.get('os.arch','').lower()
    bits=int(props.get('sun.arch.data.model','64' if arch in ('amd64','x86_64','aarch64','arm64') else '0'))
    build=version+' '+props.get('java.vm.name','')+' '+props.get('java.runtime.version','')
    return JavaRuntime(path,version,major,bits,arch,props.get('java.vendor',''),experimental=bool(re.search(r'(?i)(?:-ea|\bloom\b|internal|snapshot)',build)))


@functools.lru_cache(maxsize=256)
def _cached_probe(path,signature):return _probe(path)


def inspect_java(path,refresh=False):
    binary=Path(path).resolve(strict=True)
    stat=binary.stat();release=binary.parent.parent/'release'
    release_stat=release.stat() if release.is_file() else None
    signature=(stat.st_size,stat.st_mtime_ns,release_stat.st_mtime_ns if release_stat else 0)
    return _probe(str(binary)) if refresh else _cached_probe(str(binary),signature)


def launch_compatibility(runtime):
    """Hard platform checks only; users may override Java version advice."""
    if runtime.bits!=64:return '需要64位 Java'
    if runtime.architecture not in ('amd64','x86_64','x64'):return '需要 x64 Java'
    return ''


def compatibility(runtime,required):
    reason=launch_compatibility(runtime)
    if reason:return reason
    if runtime.experimental:return '测试版／实验版，不自动选用'
    if runtime.major!=required:return f'此实例推荐 Java {required}，当前为 {runtime.major}'
    return ''


def choose_java(runtimes,required):
    candidates=[r for r in runtimes if not compatibility(r,required)]
    def key(runtime):
        version=tuple(int(n) for n in re.findall(r'\d+',runtime.version))
        return version,runtime.source=='Aetherloom',runtime.path
    return max(candidates,key=key,default=None)


def registry_java_homes():
    if os.name!='nt':return []
    import winreg
    found=[]
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            for name in ('Java Runtime Environment','Java Development Kit','JRE','JDK'):
                try:
                    with winreg.OpenKey(hive,'SOFTWARE\\JavaSoft\\'+name,0,winreg.KEY_READ|view) as key:
                        for i in range(min(winreg.QueryInfoKey(key)[0],64)):
                            with winreg.OpenKey(key,winreg.EnumKey(key,i)) as child:
                                try:found.append(Path(winreg.QueryValueEx(child,'JavaHome')[0]))
                                except OSError:pass
                except OSError:pass
    return found


def search_locations(root,managed_dir=None,env=None,home=None):
    env=os.environ if env is None else env;home=Path.home() if home is None else Path(home)
    locations=[];direct=[]
    def add(path,source):
        if path:locations.append((Path(path),source))
    add(root,'游戏目录')
    if managed_dir:add(managed_dir,'Aetherloom')
    for parent in itertools.islice(Path(root).resolve().parents,5):
        for child in ('runtime','java','Java','jre','jdk','PCL/Java'):add(parent/child,'游戏目录附近')
    for key in ('JAVA_HOME','JDK_HOME','JRE_HOME'):
        if env.get(key):add(env[key],key)
    for folder in env.get('PATH','').split(os.pathsep)[:128]:
        if folder and os.path.isabs(folder) and '\\common files\\oracle\\java\\' not in folder.lower():
            direct.append((Path(folder)/('java.exe' if os.name=='nt' else 'java'),'PATH'))
    add(home/'.jdks','用户 .jdks')
    appdata=Path(env.get('APPDATA') or home/'AppData/Roaming')
    local=Path(env.get('LOCALAPPDATA') or home/'AppData/Local')
    add(appdata/'hmcl/java','HMCL 运行时目录')
    add(appdata/'.hmcl/java','HMCL 运行时目录')
    add(home/'.hmcl/java','HMCL 运行时目录')
    add(appdata/'.minecraft/runtime','Minecraft 运行时')
    add(home/'.minecraft/runtime','Minecraft 运行时')
    add(local/'Packages/Microsoft.4297127D64EC6_8wekyb3d8bbwe/LocalCache/Local/runtime','Minecraft 运行时')
    for base in dict.fromkeys(filter(None,(env.get('ProgramFiles'),env.get('ProgramW6432'),env.get('ProgramFiles(x86)')))):
        for vendor in ('Java','Microsoft','Eclipse Adoptium','Eclipse Foundation','AdoptOpenJDK','Amazon Corretto','BellSoft','Zulu','Semeru','SapMachine'):
            add(Path(base)/vendor,'系统安装目录')
        add(Path(base)/'Minecraft Launcher/runtime','Minecraft 运行时')
    if os.name=='nt':
        for path in registry_java_homes():add(path,'注册表')
    else:
        for path in ('/usr/lib/jvm','/usr/java','/Library/Java/JavaVirtualMachines'):add(path,'系统安装目录')
        add(home/'.sdkman/candidates/java','SDKMAN')
    return locations,direct


def find_runtimes(root,managed_dir=None,known=(),locations=None):
    """Known locations only. No disks, saves, mods, account caches or PATH recursion."""
    roots,direct=search_locations(root,managed_dir) if locations is None else (locations,[])
    paths={}
    for path in known:
        if path and Path(path).is_file():paths.setdefault(str(Path(path).resolve()),'已指定')
    for folder,source in roots:
        for path in discover_java(folder,required=0):paths.setdefault(path,source)
        if len(paths)>=64:break
    for path,source in direct:
        if path.is_file():paths.setdefault(str(path.resolve()),source)
    found=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(inspect_java,path):source for path,source in list(paths.items())[:64]}
        for job in concurrent.futures.as_completed(jobs):
            try:
                info=job.result()
                found.append(JavaRuntime(**dict(info.__dict__,source=jobs[job])))
            except (OSError,ValueError,subprocess.SubprocessError):pass
    return sorted(found,key=lambda r:(r.major,r.version,r.path))
