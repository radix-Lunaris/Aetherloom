import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from dataclasses import replace
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
            source.write_text('public class Main { public static void main(String[] args) throws Exception { java.nio.file.Files.writeString(java.nio.file.Path.of("started.txt"), String.join("|",args)); java.nio.file.Files.writeString(java.nio.file.Path.of("jvm.txt"), System.getProperty("ignoreList")); }}',encoding="utf-8")
            subprocess.run(["javac","--release","17",str(source)],check=True,capture_output=True)
            base_id='原版游戏 Primary'
            base=root/'versions'/base_id;base.mkdir()
            with zipfile.ZipFile(base/(base_id+'.jar'),"w") as archive:
                archive.write(Path(d)/"Main.class","Main.class")
            (base/(base_id+'.json')).write_text(json.dumps({"id":base_id,"mainClass":"Main",
                "assetIndex":{"id":"test"},"javaVersion":{"majorVersion":17},
                "arguments":{"jvm":["-DignoreList=forge-,${version_name}.jar,${primary_jar_name}"],"game":["--username","${auth_player_name}","--gameDir","${game_directory}","--clientId","${clientid}","--xuid","${auth_xuid}","--primaryJar","${primary_jar}","--primaryName","${primary_jar_name}","--libraries","${libraries_directory}","--separator","${file_separator}"]}}),encoding="utf-8")
            (run/"forge.json").write_text(json.dumps({"id":"forge","inheritsFrom":base_id}),encoding="utf-8")
            indexes=root/"assets/indexes";indexes.mkdir(parents=True)
            (indexes/"test.json").write_text('{"objects":{}}')
            process=launch(root,"forge",java,"OfflineUser",run,512)
            code=process.wait(timeout=20)
            logs=list((run/".aetherloom/logs").glob("*.log"))
            self.assertEqual(code,0,"\\n".join(p.read_text(encoding="utf-8",errors="replace") for p in logs))
            from aetherloom.runtime import inspect_java
            # A valid Java25 selection must reach process creation even when
            # the installed profile recommends Java17; use the real test VM
            # with a different reported major to exercise this old hard gate.
            selected=replace(inspect_java(java),major=25,version='25.0.3')
            with patch('aetherloom.runtime.inspect_java',return_value=selected):
                other=launch(root,"forge",java,"OfflineUser",run,512)
                self.assertEqual(other.wait(timeout=20),0)
            self.assertIn("OfflineUser",(run/"started.txt").read_text(encoding="utf-8"))
            arguments=(run/"started.txt").read_text(encoding="utf-8").split('|')
            self.assertEqual(Path(arguments[arguments.index('--gameDir')+1]).resolve(),run.resolve())
            primary=Path(arguments[arguments.index('--primaryJar')+1])
            primary_name=arguments[arguments.index('--primaryName')+1]
            self.assertTrue(primary.samefile(base/(base_id+'.jar')))
            self.assertEqual(primary_name,primary.name)
            self.assertIn(primary_name,(run/'jvm.txt').read_text(encoding='utf-8'))
            self.assertNotEqual(primary_name,'forge.jar')
            self.assertEqual(arguments[arguments.index('--separator')+1],__import__('os').sep)
            self.assertEqual(len(list((run/".aetherloom/logs").glob("*.log"))),2)
            (base/(base_id+'.jar')).unlink()
            with self.assertRaises(LaunchError):
                prepare(root,"forge",java,"OfflineUser",run)

