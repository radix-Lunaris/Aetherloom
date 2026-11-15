import hashlib
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from aetherloom.cloud import CloudWorld
from aetherloom.server import create_app,add_user


class CloudTests(unittest.TestCase):
    def test_world_roundtrip_and_candidate_requires_idle_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);app=create_app(root/'server')
            for name,role in [('owner','player'),('friend','player'),('global-admin','admin')]:add_user(app.state.store,name,'123456',role)
            with TestClient(app) as client:
                def api_for(name):
                    token=client.post('/api/login',json={'username':name,'password':'123456'}).json()['token']
                    def api(path,body=None,method=None,headers=None,raw=False):
                        opts={'headers':dict({'Authorization':'Bearer '+token},**(headers or {}))}
                        if isinstance(body,bytes):opts['content']=body
                        elif body is not None:opts['json']=body
                        result=client.request(method or ('POST' if body is not None else 'GET'),path,**opts)
                        if result.status_code>=400:raise ValueError(str(result.status_code)+': '+result.text)
                        return result.content if raw else result.json()
                    return api
                owner,friend,admin=map(api_for,('owner','friend','global-admin'))
                room=owner('/api/rooms',{'name':'one world','world':'world'})['id'];base='/api/rooms/'+room
                friend(base+'/join',{})
                world=root/'world';world.mkdir();(world/'level.dat').write_bytes(b'saved-fixture')
                (world/'region').mkdir();(world/'region/r.0.0.mca').write_bytes(b'R'*(513*1024))
                cloud=CloudWorld(owner,root/'cache');lease=owner(base+'/claim',{})
                credentials={k:lease[k] for k in ('token','epoch')}
                head=cloud.upload(room,world,credentials,None)
                downloaded=root/'checkout';CloudWorld(friend,root/'friend-cache').download(room,downloaded)
                self.assertEqual((downloaded/'region/r.0.0.mca').read_bytes(),(world/'region/r.0.0.mca').read_bytes())
                (world/'level.dat').write_bytes(b'recovery-copy')
                candidate=cloud.candidate(room,world,head)
                self.assertEqual(owner(base+'/head')['version'],head)
                lease=friend(base+'/claim',{})
                with self.assertRaisesRegex(ValueError,'409'):owner(base+'/recoveries/'+candidate+'/approve',{'expected_head':head})
                friend(base+'/cancel',{k:lease[k] for k in ('token','epoch')})
                with self.assertRaisesRegex(ValueError,'403'):admin(base+'/recoveries/'+candidate+'/approve',{'expected_head':head})
                with self.assertRaisesRegex(ValueError,'409'):owner(base+'/recoveries/'+candidate+'/approve',{'expected_head':'stale-review'})
                restored=owner(base+'/recoveries/'+candidate+'/approve',{'expected_head':head})['version']
                self.assertNotEqual(restored,head)
                CloudWorld(friend,root/'friend-cache').download(room,downloaded)
                self.assertEqual((downloaded/'level.dat').read_bytes(),b'recovery-copy')
                with app.state.store.connect() as c:
                    self.assertTrue(c.execute('SELECT 1 FROM versions WHERE id=?',(head,)).fetchone())
