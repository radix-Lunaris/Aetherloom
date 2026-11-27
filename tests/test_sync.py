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
            (dest/'stale.dat').write_bytes(b'keep in backup')
            (dest/'level.dat').write_bytes(b'old local')
            materialize(dest,m,s)
            self.assertFalse((dest/'stale.dat').exists())
            backups=list((dest/'.aetherloom/backups').rglob('stale.dat'))
            self.assertEqual(backups[0].read_bytes(),b'keep in backup')
            (dest/'.aetherloom/incomplete').write_text('interrupted')
            with self.assertRaises(ValueError):materialize(dest,m,s)
            m["level.dat"]["hash"]="0"*64
            with self.assertRaises(ValueError):
                materialize(root/"bad",m,s)


    def test_pruning_publishes_a_copy_without_mutating_source(self):
        from unittest.mock import patch
        from aetherloom.world_prune import clean_copy
        from aetherloom.vendor.mcsync.chunk_prune import PruneReport,RegionReport,ChunkVerdict
        with tempfile.TemporaryDirectory() as directory:
            world=Path(directory)/'source'
            (world/'region').mkdir(parents=True)
            (world/'level.dat').write_bytes(b'world')
            region=world/'region/r.0.0.mca'
            original=b'terrain'
            region.write_bytes(original)
            report=PruneReport(regions=[RegionReport(str(region),kind='region',
                prune=1,verdicts={1:ChunkVerdict(1,reason='prune')})])
            with patch('aetherloom.world_prune.chunk_prune.scan',return_value=report), patch(
                'aetherloom.world_prune.chunk_prune.parse_region',
                return_value=RegionReport('',verdicts={1:ChunkVerdict(1,data=b'data')})):
                plan=clean_copy(world,1)
                copy=clean_copy(world,1,plan)
            self.assertEqual(region.read_bytes(),original)
            self.assertFalse((copy/'region/r.0.0.mca').exists())
            authority=Authority(Path(directory)/'cache')
            self.assertNotIn('region/r.0.0.mca',snapshot(copy,authority))

    def test_original_cleanup_preserves_an_independent_backup(self):
        from unittest.mock import patch
        from aetherloom.world_prune import clean_copy
        from aetherloom.vendor.mcsync.chunk_prune import PruneReport,RegionReport,ChunkVerdict
        with tempfile.TemporaryDirectory() as directory:
            world=Path(directory)/'source'
            (world/'region').mkdir(parents=True)
            (world/'level.dat').write_bytes(b'world')
            region=world/'region/r.0.0.mca'
            region.write_bytes(b'original terrain')
            report=PruneReport(save_dir=str(world),regions=[RegionReport(str(region),kind='region',
                prune=1,verdicts={1:ChunkVerdict(1,reason='prune')})])
            with patch('aetherloom.world_prune.chunk_prune.scan',return_value=report), patch(
                'aetherloom.world_prune.chunk_prune.parse_region',
                return_value=RegionReport('',total=1,verdicts={1:ChunkVerdict(1,data=b'data')})):
                plan=clean_copy(world,1,dimensions={'Overworld'})
                result=clean_copy(world,1,plan,dimensions={'Overworld'},in_place=True)
            self.assertTrue(result['ok'])
            self.assertFalse(region.exists())
            self.assertEqual((Path(result['backup'])/'region'/region.name).read_bytes(),b'original terrain')
