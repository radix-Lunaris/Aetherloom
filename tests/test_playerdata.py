from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'),'JDK required')
class PlayerDataTests(unittest.TestCase):
    def test_selected_world_repair_and_conflicts(self):
        project=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);classes=root/'classes';classes.mkdir()
            sources=list((project/'playerdata/src').rglob('*.java'))
            compile=subprocess.run(['javac','--release','17','-encoding','UTF-8','-d',str(classes),*[str(p) for p in sources]],capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,compile.stderr)
            run=subprocess.run(['java','-ea','-cp',str(classes),'org.sharedplayerdata.core.RepairChecks',str(root/'worlds')],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('Repair checks passed',run.stdout)
