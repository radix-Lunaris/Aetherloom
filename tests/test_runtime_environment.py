import json
from pathlib import Path
import tempfile
import unittest
from aetherloom.runtime import discover_java
from aetherloom.environment import describe, encode, validate
from aetherloom.diagnostics import safe


class InstalledProfileTests(unittest.TestCase):
    def test_runtime_discovery_is_scoped_and_selects_required_major(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'game';root.mkdir()
            for folder,version in [('runtime/java17','17.0.1'),('java/jdk21','21.0.1'),('saves/jdk17','17.0.1')]:
                home=root/folder;(home/'bin').mkdir(parents=True)
                (home/'bin'/('java.exe' if __import__('os').name=='nt' else 'java')).touch()
                (home/'release').write_text('JAVA_VERSION="'+version+'"')
            results=discover_java(root,17)
            self.assertEqual(len(results),2)
            self.assertIn('java17',results[0])
            self.assertEqual(len(discover_java(root,21)),1)
            self.assertEqual(discover_java(root/'missing'),[])

    def test_renamed_inherited_forge_identity_and_wrong_version_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,data in [('1.20.1',{'id':'1.20.1','libraries':[]}),('我的实例',{'inheritsFrom':'1.20.1','libraries':[{'name':'net.minecraftforge:forge:1.20.1-47.4.22'}]})]:
                folder=root/'versions'/name;folder.mkdir(parents=True)
                (folder/(name+'.json')).write_text(json.dumps(data))
            identity=describe(root,'我的实例')
            validate(identity,encode(identity))
            validate(identity,'1.20.1 Forge 47.4.22')
            with self.assertRaisesRegex(ValueError,'不匹配'):
                validate(dict(identity,minecraft='1.21.1'),encode(identity))
            with self.assertRaisesRegex(ValueError,'明确版本声明'):validate(identity,'a friendly old profile')

    def test_diagnostics_redacts_credentials(self):
        text=safe('Bearer abc password=hello token="secret" resume:another')
        for secret in ('abc','hello','secret','another'):self.assertNotIn(secret,text)
