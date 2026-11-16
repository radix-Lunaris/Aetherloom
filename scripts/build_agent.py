"""Build the dependency-free Java 8 agent with an existing development JDK."""
from pathlib import Path
import os,shutil,subprocess,zipfile

def build(root=None):
    root=Path(root or Path(__file__).resolve().parent.parent)
    javac=Path(os.environ['JAVA_HOME'])/'bin'/('javac.exe' if os.name=='nt' else 'javac') if os.environ.get('JAVA_HOME') else shutil.which('javac')
    if not javac:raise RuntimeError('Existing build JDK required; no automatic Java installation')
    classes=root/'agent/build/classes';classes.mkdir(parents=True,exist_ok=True)
    version=subprocess.run([str(javac),'-version'],capture_output=True,text=True,check=True)
    flags=['-source','8','-target','8'] if '1.8.' in version.stdout+version.stderr else ['--release','8']
    subprocess.run([str(javac),*flags,'-encoding','UTF-8','-d',str(classes),*[str(p) for p in (root/'agent/src').rglob('*.java')]],check=True)
    jar=root/'assets/aetherloom-agent.jar';jar.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\r\nPremain-Class: online.superyk7hero.aetherloom.agent.Agent\r\nCan-Redefine-Classes: false\r\nCan-Retransform-Classes: false\r\n\r\n')
        archive.write(root/'LICENSE','META-INF/LICENSE')
        for parent in (classes,root/'agent/resources'):
            for path in parent.rglob('*'):
                if path.is_file():archive.write(path,path.relative_to(parent).as_posix())
    print(jar)
    return jar

if __name__=='__main__':build()
