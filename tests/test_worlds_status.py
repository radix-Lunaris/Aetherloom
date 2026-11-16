import gzip
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aetherloom.worlds import discover,level_info,Reader
from aetherloom.network_status import nat_values
from aetherloom.vendor.craftlink.nat_types import NatSub,Filter
from aetherloom.environment import validate


def text(value):
    data=value.encode('utf-8');return struct.pack('>H',len(data))+data


def metadata(name='共同世界',version='1.20.1',played=1000):
    string=lambda key,value:b'\x08'+text(key)+text(value)
    return (b'\x0a\x00\x00\x0a'+text('Data')+string('LevelName',name)+
            b'\x0a'+text('Version')+string('Name',version)+b'\x00'+
            b'\x04'+text('LastPlayed')+struct.pack('>q',played)+
            b'\x03'+text('GameType')+struct.pack('>i',1)+b'\x01'+text('Difficulty')+b'\x02\x00\x00')


class WorldDiscoveryTests(unittest.TestCase):
    def test_selected_saves_only_metadata_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'所选实例';saves=run/'saves';saves.mkdir(parents=True)
            for folder,raw in [('中文世界',gzip.compress(metadata(played=2000))),('旧世界',zlib.compress(metadata(played=1000))),('损坏',b'broken')]:
                world=saves/folder;world.mkdir();(world/'level.dat').write_bytes(raw)
                (world/'region').mkdir();(world/'region/r.0.0.mca').touch()
            outside=root/'其他实例';outside.mkdir();(outside/'level.dat').write_bytes(metadata())
            (saves/'非世界').mkdir()
            original=Path.read_bytes;reads=[]
            def read(path):reads.append(path);return original(path)
            with patch.object(Path,'read_bytes',read):rows=discover(run)
            self.assertEqual([r['folder'] for r in rows],['中文世界','旧世界','损坏'])
            self.assertTrue(all(p.name=='level.dat' and p.parent.parent==saves for p in reads))
            self.assertEqual(rows[0]['game_version'],'1.20.1');self.assertEqual(rows[0]['gametype'],'创造')
            self.assertTrue(rows[2]['error']);self.assertFalse(rows[0]['error'])

    def test_bounded_compression_truncation_and_nbt_depth(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'level.dat'
            path.write_bytes(zlib.compress(metadata())[:-2])
            with self.assertRaises(ValueError):level_info(path)
            path.write_bytes(gzip.compress(b'x'*(16*1024*1024+1)))
            with self.assertRaisesRegex(ValueError,'过大'):level_info(path)
            with self.assertRaisesRegex(ValueError,'过深'):Reader(b'').payload(10,65)
            with self.assertRaises(ValueError):Reader(struct.pack('>i',-1)).payload(7)


class StatusAndCompatibilityTests(unittest.TestCase):
    def profile(self,sub,filtering):
        return SimpleNamespace(nat_type=sub,filtering=filtering,public=('203.0.113.1',12345),responded_servers=2,asked=3,pool_size=8)

    def test_craftlink_nat_filter_semantics_without_guessing(self):
        cases=[(NatSub.CONE,Filter.EIF,'NAT1/2','入站宽松'),
               (NatSub.CONE,Filter.ADF_OR_EIF,'NAT1/2','入站中等'),
               (NatSub.CONE,Filter.APDF,'NAT3','入站严格'),
               (NatSub.CONE,Filter.UNKNOWN,'过滤未测','入站未测'),
               (NatSub.HARD,Filter.UNKNOWN,'NAT4','入站未测'),
               (NatSub.UNKNOWN,Filter.UNKNOWN,'未知','入站未测')]
        for sub,filtering,nat,inbound in cases:
            with self.subTest(sub=sub,filtering=filtering):
                value=nat_values(self.profile(sub,filtering))
                self.assertIn(nat,value['nat']);self.assertEqual(value['inbound'],inbound)
                self.assertIn('2/3',value['detail']);self.assertIn('独立诊断套接字',value['detail'])

    def test_forge_patch_not_pinned_but_game_and_major_are(self):
        local=dict(minecraft='1.20.1',loader='forge',loader_version='47.4.22')
        validate(local,dict(local,loader_version='47.3.0'))
        with self.assertRaises(ValueError):validate(local,dict(local,loader_version='48.0.1'))
        modern=dict(minecraft='1.21.1',loader='forge',loader_version='52.1.16')
        validate(modern,dict(modern,loader_version='52.0.0'),backend='agent')
        with self.assertRaises(ValueError):validate(modern,modern,backend='bridge')
