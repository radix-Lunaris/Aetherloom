from pathlib import Path
import tempfile
import unittest
from aetherloom.store import Authority
from aetherloom.sync import snapshot, materialize

class SyncTests(unittest.TestCase):
    def test_roundtrip_dedup_and_backups(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            world=root/"world"
            world.mkdir()
            (world/"level.dat").write_bytes(b"world")
            (world/"old.spd_backup").write_bytes(b"backup")
            (world/"session.lock").write_bytes(b"locked")
            s=Authority(root/"store")
            m=snapshot(world,s)
            self.assertNotIn("session.lock",m)
            self.assertIn("old.spd_backup",m)
            blobs=list((s.root/"blobs").rglob("*"))
            self.assertEqual(snapshot(world,s),m)
            self.assertEqual(list((s.root/"blobs").rglob("*")),blobs)
            dest=root/"download"
            materialize(dest,m,s)
            self.assertEqual((dest/"level.dat").read_bytes(),b"world")
            self.assertFalse((dest/".aetherloom/incomplete").exists())
            m["level.dat"]["hash"]="0"*64
            with self.assertRaises(ValueError):
                materialize(root/"bad",m,s)

