import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aetherloom.cloud import CloudWorld
from aetherloom.shared_session import SharedSession
from aetherloom.sync import snapshot
from aetherloom.store import Authority


class ProgressTests(unittest.TestCase):
    def test_incremental_upload_and_failed_commit_never_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);world=root/'world';world.mkdir()
            (world/'level.dat').write_bytes(b'saved')
            (world/'region').mkdir();(world/'region/r.0.0.mca').write_bytes(b'A'*262144+b'B'*262144)
            stored=set();sent=[];events=[];fail=False
            def api(path,body=None,**kwargs):
                if path.endswith('/missing'):return {'missing':[h for h in body['hashes'] if h not in stored]}
                if '/blobs/' in path:
                    h=path.rsplit('/',1)[1];stored.add(h);sent.append(len(body));return {}
                if path.endswith('/commit'):
                    if fail:raise ValueError('commit rejected')
                    return {'version':'committed'}
                raise AssertionError(path)
            cloud=CloudWorld(api,root/'cache',on_progress=events.append)
            cloud.upload('room',world,{'token':'test','epoch':1},None)
            self.assertEqual(sum(sent),524293)
            self.assertEqual(events[-1]['percent'],100)
            self.assertEqual([e['percent'] for e in events],sorted(e['percent'] for e in events))
            sent.clear();events.clear()
            cloud.upload('room',world,{'token':'test','epoch':2},'committed')
            self.assertEqual(sent,[])
            self.assertEqual(events[-1]['stage'],'complete')
            (world/'region/r.0.0.mca').write_bytes(b'A'*262144+b'C'*262144)
            sent.clear();events.clear();fail=True
            with self.assertRaisesRegex(ValueError,'commit rejected'):
                cloud.upload('room',world,{'token':'test','epoch':3},'committed')
            self.assertEqual(sent,[262144])
            self.assertTrue(all(e['percent']<100 for e in events))

    def test_download_cache_reuse_and_corruption_does_not_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();(source/'level.dat').write_bytes(b'world')
            store=Authority(root/'server');manifest=snapshot(source,store)
            requests=[];events=[];corrupt=False
            def api(path,**kwargs):
                if path.endswith('/head'):return {'version':'head','manifest':manifest}
                h=path.rsplit('/',1)[1];requests.append(h)
                return b'corrupted' if corrupt else (store.root/'blobs'/h[:2]/h).read_bytes()
            cloud=CloudWorld(api,root/'cache',on_progress=events.append)
            cloud.download('room',root/'checkout')
            self.assertEqual(len(requests),1);self.assertEqual(events[-1]['percent'],100)
            before=(root/'checkout/level.dat').stat().st_mtime_ns
            requests.clear();events.clear();cloud.download('room',root/'checkout')
            self.assertEqual(requests,[])
            self.assertEqual((root/'checkout/level.dat').stat().st_mtime_ns,before)
            self.assertEqual([e['percent'] for e in events],sorted(e['percent'] for e in events))
            events.clear()
            CloudWorld(api,root/'cold-cache',on_progress=events.append).download('room',root/'checkout')
            self.assertEqual(requests,[])
            corrupt=True;events.clear()
            with self.assertRaisesRegex(ValueError,'校验失败'):
                CloudWorld(api,root/'bad-cache',on_progress=events.append).download('room',root/'bad-checkout')
            self.assertTrue(all(e['percent']<100 for e in events))
            self.assertFalse((root/'bad-checkout/level.dat').exists())

    def test_session_summary_survives_without_streams_and_reports_preflight_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            events=[];callbacks={}
            class Network:
                def __init__(self,*args,on_status,**kwargs):callbacks['network']=on_status
                async def close(self):pass
            with patch('aetherloom.shared_session.Network',Network):
                session=SharedSession('https://unused.invalid','test',Path(directory)/'cache','room',{},lambda *event:events.append(event))
            self.assertEqual(session.start_timeout,900)
            session.state('ready',role='Host',lan_port=25565)
            self.assertEqual(events[-1][1]['players'],0)
            self.assertEqual(events[-1][1]['phase'],'ready')
            callbacks['network']({'session_id':'one','channel':'data','peer':'member','relay_ready':True})
            self.assertEqual(session.session_info['players'],1)
            callbacks['network']({'session_id':'one','channel':'data','peer':'member','switch_phase':'ended'})
            self.assertEqual(session.session_info['phase'],'ready');self.assertEqual(session.session_info['players'],0)
            with patch.object(session,'prepare_java',side_effect=ValueError('no Java')):
                with self.assertRaisesRegex(ValueError,'no Java'):asyncio.run(session.run())
            self.assertEqual(events[-1][1]['phase'],'failed')
            self.assertIn('no Java',events[-1][1]['message'])
