import tempfile
import unittest
from fastapi.testclient import TestClient
from aetherloom.server import create_app,add_user


class RoomOptionsTests(unittest.TestCase):
    def test_scoped_account_options_and_diagnostics_never_expose_capabilities(self):
        with tempfile.TemporaryDirectory() as d:
            app=create_app(d)
            for name,role in [('owner','player'),('member','player'),('global','admin')]:
                add_user(app.state.store,name,'123456',role)
            with TestClient(app) as client:
                def login(name):
                    token=client.post('/api/login',json={'username':name,'password':'123456'}).json()['token']
                    return {'Authorization':'Bearer '+token}
                owner,member,admin=map(login,('owner','member','global'))
                room=client.post('/api/rooms',headers=owner,json={}).json()['id'];base='/api/rooms/'+room
                options=client.get(base+'/account-options',headers=owner).json()
                self.assertEqual({o['name'] for o in options},{'owner','member','global'})
                self.assertTrue(all(set(o)=={'name'} for o in options))
                self.assertEqual(client.get(base+'/account-options',headers=member).status_code,403)
                self.assertEqual(client.get(base+'/account-options',headers=admin).status_code,403)
                self.assertEqual(client.get(base+'/account-options').status_code,401)
                diagnostic=client.get(base+'/diagnostics',headers=owner).json()
                self.assertEqual(diagnostic['streams'],[])
                self.assertNotIn('token',diagnostic)
                self.assertEqual(client.get(base+'/diagnostics',headers=member).status_code,403)
                client.post(base+'/join',headers=member,json={})
                lease=client.post(base+'/claim',headers=owner,json={}).json()
                credentials={k:lease[k] for k in ('token','epoch')}
                client.post(base+'/ready',headers=owner,json=credentials)
                connection=client.post(base+'/connections',headers=member,json={}).json()
                result=client.get(base+'/diagnostics',headers=owner)
                self.assertEqual(len(result.json()['streams']),2)
                self.assertNotIn(connection['resume'],result.text)
                self.assertNotIn(connection['network']['shared'],result.text)
                identity={'name':'Guest','uuid':'81f14300-fbc1-4a46-88f0-0d90db478198','actor':'spoofed'}
                custom=client.post(base+'/connections',headers=member,json={'identity':identity})
                self.assertEqual(custom.status_code,200)
                self.assertEqual(custom.json()['identity']['actor'],'member')
                changed=client.post(base+'/connections',headers=member,json={'identity':dict(identity,uuid='91f14300-fbc1-4a46-88f0-0d90db478198')})
                self.assertEqual(changed.status_code,409)
                invalid=client.post(base+'/connections',headers=member,json={'identity':dict(identity,uuid=123)})
                self.assertLess(invalid.status_code,500)
