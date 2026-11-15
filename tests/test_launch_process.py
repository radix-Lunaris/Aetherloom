import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from aetherloom.launcher import launch,LaunchError,prepare

@unittest.skipUnless(shutil.which("javac") and shutil.which("jar"),"JDK required for process test")
class LaunchProcessTests(unittest.TestCase):
    def test_direct_java_process_with_unicode_isolated_directory(self):
        bundled=Path(__file__).resolve().parent.parent/"runtime/bin/java.exe"
        java=bundled if bundled.exists() else Path(shutil.which("java"))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"游戏目录"
            run=root/"versions"/"forge"
            run.mkdir(parents=True)
            source=Path(d)/"Main.java"
            source.write_text('public class Main { public static void main(String[] args) throws Exception { java.nio.file.Files.writeString(java.nio.file.Path.of("started.txt"), String.join("|",args)); }}',encoding="utf-8")
            subprocess.run(["javac","--release","17",str(source)],check=True,capture_output=True)
            base=root/"versions/base";base.mkdir()
            with zipfile.ZipFile(base/"base.jar","w") as archive:
                archive.write(Path(d)/"Main.class","Main.class")
            (base/"base.json").write_text(json.dumps({"id":"base","mainClass":"Main",
                "assetIndex":{"id":"test"},"javaVersion":{"majorVersion":17},
                "arguments":{"game":["--username","${auth_player_name}","--gameDir","${game_directory}","--clientId","${clientid}","--xuid","${auth_xuid}"]}}),encoding="utf-8")
            (run/"forge.json").write_text(json.dumps({"id":"forge","inheritsFrom":"base"}),encoding="utf-8")
            indexes=root/"assets/indexes";indexes.mkdir(parents=True)
            (indexes/"test.json").write_text('{"objects":{}}')
            process=launch(root,"forge",java,"OfflineUser",run,512)
            code=process.wait(timeout=20)
            logs=list((run/".aetherloom/logs").glob("*.log"))
            self.assertEqual(code,0,"\\n".join(p.read_text(encoding="utf-8",errors="replace") for p in logs))
            self.assertIn("OfflineUser",(run/"started.txt").read_text(encoding="utf-8"))
            arguments=(run/"started.txt").read_text(encoding="utf-8").split('|')
            self.assertEqual(Path(arguments[arguments.index('--gameDir')+1]).resolve(),run.resolve())
            self.assertEqual(len(list((run/".aetherloom/logs").glob("*.log"))),1)
            (base/"base.jar").unlink()
            with self.assertRaises(LaunchError):
                prepare(root,"forge",java,"OfflineUser",run)

