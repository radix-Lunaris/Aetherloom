"""Build the Java 8 agent with pinned, privately relocated ASM."""
from pathlib import Path
import os,shutil,subprocess,zipfile,hashlib,urllib.request,struct

ASM_SHA256='8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281'
ASM_URL='https://repo.maven.apache.org/maven2/org/ow2/asm/asm/9.7.1/asm-9.7.1.jar'
OLD=b'org/objectweb/asm';NEW=b'online/superyk7hero/aetherloom/agent/internal/asm'

def relocate(data):
    """Relocate only constant-pool UTF8 entries, preserving bytecode/frames."""
    out=bytearray(data[:10]);pos=10;count=int.from_bytes(data[8:10],'big');i=1
    while i<count:
        tag=data[pos];pos+=1;out.append(tag)
        if tag==1:
            size=int.from_bytes(data[pos:pos+2],'big');pos+=2
            value=data[pos:pos+size].replace(OLD,NEW).replace(OLD.replace(b'/',b'.'),NEW.replace(b'/',b'.'));pos+=size
            out.extend(struct.pack('>H',len(value)));out.extend(value)
        else:
            size={3:4,4:4,5:8,6:8,7:2,8:2,9:4,10:4,11:4,12:4,15:3,16:2,17:4,18:4,19:2,20:2}[tag]
            out.extend(data[pos:pos+size]);pos+=size
            if tag in (5,6):i+=1
        i+=1
    return bytes(out)+data[pos:]

def build(root=None):
    root=Path(root or Path(__file__).resolve().parent.parent)
    javac=Path(os.environ['JAVA_HOME'])/'bin'/('javac.exe' if os.name=='nt' else 'javac') if os.environ.get('JAVA_HOME') else shutil.which('javac')
    if not javac:raise RuntimeError('Existing build JDK required; no automatic Java installation')
    asm=root/'.local/build-deps/asm-9.7.1.jar';asm.parent.mkdir(parents=True,exist_ok=True)
    if not asm.exists():
        with urllib.request.urlopen(ASM_URL,timeout=60) as response:data=response.read(1024*1024)
        if hashlib.sha256(data).hexdigest()!=ASM_SHA256:raise ValueError('ASM dependency hash mismatch')
        asm.write_bytes(data)
    if hashlib.sha256(asm.read_bytes()).hexdigest()!=ASM_SHA256:raise ValueError('ASM dependency hash mismatch')
    classes=root/'agent/build/classes';classes.mkdir(parents=True,exist_ok=True)
    version=subprocess.run([str(javac),'-version'],capture_output=True,text=True,check=True)
    flags=['-source','8','-target','8'] if '1.8.' in version.stdout+version.stderr else ['--release','8']
    subprocess.run([str(javac),*flags,'-classpath',str(asm),'-encoding','UTF-8','-d',str(classes),*[str(p) for p in (root/'agent/src').rglob('*.java')]],check=True)
    jar=root/'assets/aetherloom-agent.jar';jar.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\r\nPremain-Class: online.superyk7hero.aetherloom.agent.Agent\r\nCan-Redefine-Classes: false\r\nCan-Retransform-Classes: false\r\n\r\n')
        archive.write(root/'LICENSE','META-INF/LICENSE')
        archive.write(root/'aetherloom/vendor/asm/ASM-LICENSE.txt','META-INF/ASM-LICENSE.txt')
        for parent in (classes,root/'agent/resources'):
            for path in parent.rglob('*'):
                if path.is_file():
                    data=path.read_bytes()
                    archive.writestr(path.relative_to(parent).as_posix(),relocate(data) if path.suffix=='.class' else data)
        with zipfile.ZipFile(asm) as library:
            for name in library.namelist():
                if name.startswith('org/objectweb/asm/') and name.endswith('.class'):
                    archive.writestr(name.replace(OLD.decode(),NEW.decode()),relocate(library.read(name)))
    print(jar)
    return jar

if __name__=='__main__':build()
