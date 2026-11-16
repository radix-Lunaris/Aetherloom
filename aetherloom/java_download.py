"""User-requested Temurin Windows x64 runtime install, verified and atomic."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import threading
import urllib.request
import urllib.error
from urllib.parse import urlencode,urlsplit
import uuid
import zipfile
from .runtime import inspect_java,compatibility

MAX_ARCHIVE=512*1024**2
MAX_EXPANDED=1536*1024**2
WINDOWS_RUNTIME_INSTALL=os.name=='nt'


def trusted_url(url):
    parts=urlsplit(url)
    host=(parts.hostname or '').lower()
    if parts.scheme!='https' or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError('Java 下载地址必须使用官方 HTTPS')
    if host not in ('api.adoptium.net','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'):
        raise ValueError('拒绝非官方 Java 下载地址')
    if host=='github.com' and not re.match(r'^/adoptium/temurin\d+-binaries/releases/download/',parts.path):
        raise ValueError('拒绝未知 Java 发布仓库')
    return url


class TrustedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        trusted_url(newurl)
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def open_url(url):
    trusted_url(url)
    opener=urllib.request.build_opener(TrustedRedirect())
    return opener.open(urllib.request.Request(url,headers={'User-Agent':'Aetherloom-Java-Manager','Accept':'application/json, application/octet-stream'}),timeout=20)


def release_package(major,open_request=open_url):
    if major not in (8,16,17,21,25):raise ValueError(f'暂不提供 Java {major} 一键下载，请手动指定')
    for kind in ('jre','jdk'):
        query=urlencode(dict(architecture='x64',image_type=kind,os='windows',vendor='eclipse'))
        try:
            with open_request(f'https://api.adoptium.net/v3/assets/latest/{major}/hotspot?'+query) as response:
                data=response.read(2*1024**2+1)
        except urllib.error.HTTPError as error:
            if error.code==404:continue
            raise
        if len(data)>2*1024**2:raise ValueError('Java 发布信息过大')
        for item in json.loads(data):
            binary=item.get('binary',{});version=item.get('version',{})
            if binary.get('architecture')!='x64' or binary.get('os')!='windows' or binary.get('image_type')!=kind:continue
            if version.get('major')!=major or version.get('pre'):continue
            package=binary['package'];size=int(package['size']);checksum=package['checksum'].lower()
            if not 0<size<=MAX_ARCHIVE or not re.fullmatch('[a-f0-9]{64}',checksum):raise ValueError('Java 校验信息无效')
            link=trusted_url(package['link'])
            if not urlsplit(link).path.endswith('.zip'):continue
            return {'url':link,'size':size,'sha256':checksum,'major':major,'version':version.get('semver',str(major))}
    raise ValueError(f'官方未提供 Java {major} Windows x64 ZIP，请手动指定')


def check_cancel(cancel):
    if cancel.is_set():raise ValueError('Java 下载已取消')


def extract_zip(archive,output,cancel):
    """Validate ALL entries before writing. No links, escapes or overwrites."""
    output=Path(output).resolve();total=0;targets=set();entries=[]
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>20000:raise ValueError('Java 归档文件数量超限')
        for entry in z.infolist():
            check_cancel(cancel)
            name=entry.filename.replace('\\','/')
            path=PurePosixPath(name)
            if path.is_absolute() or not path.parts or any(p in ('.','..') or ':' in p or p.endswith(('.',' ')) for p in path.parts):
                raise ValueError('Java 归档路径无效')
            if any(re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',p) for p in path.parts):
                raise ValueError('Java 归档包含保留设备名')
            if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Java 归档不允许符号链接')
            destination=output.joinpath(*path.parts)
            key=str(destination).casefold()
            if key in targets:raise ValueError('Java 归档包含重复路径')
            targets.add(key)
            total+=entry.file_size
            if total>MAX_EXPANDED:raise ValueError('Java 解压大小超限')
            entries.append((entry,destination))
        if shutil.disk_usage(output).free<total+64*1024**2:raise ValueError('磁盘空间不足，无法安装 Java')
        for entry,destination in entries:
            check_cancel(cancel)
            if entry.is_dir():destination.mkdir(parents=True,exist_ok=True);continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            with z.open(entry) as source,destination.open('xb') as target:
                while chunk:=source.read(1024**2):
                    check_cancel(cancel);target.write(chunk)


def install_runtime(major,directory,progress=None,cancel=None,open_request=open_url,package=None,probe=inspect_java):
    if not WINDOWS_RUNTIME_INSTALL:raise ValueError('一键安装目前仅提供 Windows x64')
    progress=progress or (lambda text:None);cancel=cancel or threading.Event()
    progress(f'正在查询官方 Temurin Java {major} Windows x64 发行版')
    package=package or release_package(major,open_request)
    if package['major']!=major:raise ValueError('Java 下载主版本不匹配')
    trusted_url(package['url'])
    check_cancel(cancel)
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    target=root/('temurin-'+str(major)+'-'+package['sha256'][:16])
    if target.exists():
        for path in target.glob('*/bin/java.exe'):
            info=probe(path)
            if not compatibility(info,major):return str(path)
        raise ValueError('已有 Java 缓存不完整，请手动检查缓存目录')
    if shutil.disk_usage(root).free<package['size']*4+128*1024**2:raise ValueError('磁盘空间不足，Java 下载尚未开始')
    stage=root/('.install-'+uuid.uuid4().hex);stage.mkdir()
    try:
        archive=stage/'runtime.zip.part';digest=hashlib.sha256();received=0;last=-1
        with open_request(package['url']) as response,archive.open('xb') as output:
            while chunk:=response.read(1024**2):
                check_cancel(cancel);received+=len(chunk)
                if received>package['size'] or received>MAX_ARCHIVE:raise ValueError('Java 下载大小超限')
                digest.update(chunk);output.write(chunk)
                percent=int(received*100/package['size'])
                if percent!=last:
                    progress(f'下载 Java {major}：{received/1024**2:.1f} / {package["size"]/1024**2:.1f} MiB（{percent}%）');last=percent
        check_cancel(cancel)
        if received!=package['size'] or digest.hexdigest()!=package['sha256']:
            raise ValueError('Java SHA-256 或大小校验失败，未安装')
        progress('Java 下载校验通过，正在解压到独立运行时目录')
        unpacked=stage/'unpacked';unpacked.mkdir();extract_zip(archive,unpacked,cancel)
        candidates=list(unpacked.glob('*/bin/java.exe'))
        if len(candidates)!=1:raise ValueError('Java 归档布局异常')
        info=probe(candidates[0])
        reason=compatibility(info,major)
        if reason:raise ValueError('下载后的 Java 检查失败：'+reason)
        (unpacked/'AETHERLOOM_DOWNLOAD.json').write_text(json.dumps(package,indent=2),encoding='utf-8')
        relative=candidates[0].relative_to(unpacked)
        check_cancel(cancel)
        unpacked.rename(target)
        progress(f'Temurin Java {major} 安装完成，已保留原始许可文件')
        return str(target/relative)
    finally:
        # Only the uniquely created staging directory is removed, never a Java
        # supplied by the user or another launcher.
        shutil.rmtree(stage)
