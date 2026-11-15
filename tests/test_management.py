import tempfile
import unittest
from fastapi.testclient import TestClient
from aetherloom.server import create_app, add_user


class ManagementTests(unittest.TestCase):
    def test_policy_tokens_and_persistent_room(self):
        with tempfile.TemporaryDirectory() as d:
            app=create_app(d)
            for name,role in [('root','root'),('admin','admin'),('friend','player'),('other','player')]:
                add_user(app.state.store,name,'123456',role)
            with TestClient(app) as c:
                def login(name,password='123456'):
                    r=c.post('/api/login',json=dict(username=name,password=password))
                    self.assertEqual(r.status_code,200,r.text)
                    return {'Authorization':'Bearer '+r.json()['token']}
                root,admin,friend,other=[login(n) for n in ('root','admin','friend','other')]
                self.assertEqual(c.patch('/api/users/root',headers=root,json={'password':'abcdef'}).status_code,403)
                self.assertEqual(c.patch('/api/users/friend',headers=admin,json={'role':'admin'}).status_code,403)
                self.assertEqual(c.patch('/api/users/other',headers=friend,json={'username':'stolen'}).status_code,403)
                self.assertEqual(c.post('/api/users',headers=root,json=dict(username='short',password='12345')).status_code,400)
                room=c.post('/api/rooms',headers=friend,json=dict(name='共同存档',environment='1.20.1 Forge',world='我们的世界')).json()['id']
                self.assertEqual(c.patch('/api/users/friend',headers=admin,json={'username':'renamed'}).status_code,200)
                self.assertEqual(c.get('/api/rooms',headers=friend).json()[0]['owner'],'renamed')
                self.assertEqual(c.delete('/api/users/renamed',headers=root).status_code,409)
                self.assertEqual(c.delete('/api/rooms/'+room,headers=admin).status_code,403)
                self.assertEqual(c.post('/api/rooms/'+room+'/join',headers=other).status_code,200)
                self.assertEqual(c.post('/api/rooms/'+room+'/members',headers=friend,json=dict(username='other',role='admin')).status_code,200)
                self.assertEqual(c.patch('/api/rooms/'+room,headers=other,json={'name':'改名世界'}).status_code,200)
                lease=c.post('/api/rooms/'+room+'/claim',headers=friend,json={}).json()
                self.assertEqual(c.delete('/api/rooms/'+room,headers=root).status_code,409)
                self.assertEqual(c.post('/api/rooms/'+room+'/commit',headers=friend,json=dict(token=lease['token'],epoch=lease['epoch'],parent=None,manifest={})).status_code,200)
                self.assertEqual(c.delete('/api/rooms/'+room,headers=root).status_code,200)
                self.assertEqual(c.patch('/api/users/renamed',headers=root,json={'password':'abcdef'}).status_code,200)
                self.assertEqual(c.get('/api/rooms',headers=friend).status_code,401)
                login('renamed','abcdef')
                self.assertEqual(c.delete('/api/users/renamed',headers=admin).status_code,200)
                self.assertEqual(c.post('/api/login',json=dict(username='renamed',password='abcdef')).status_code,401)
                self.assertTrue(c.get('/api/audit',headers=root).json())

    def test_self_service_shared_monthly_budget(self):
        with tempfile.TemporaryDirectory() as d:
            app=create_app(d);add_user(app.state.store,'friend','123456','player')
            with TestClient(app) as c:
                token=c.post('/api/login',json=dict(username='friend',password='123456')).json()['token']
                headers={'Authorization':'Bearer '+token}
                for name in ('friend1','friend2','friend3'):
                    self.assertEqual(c.patch('/api/me',headers=headers,json={'username':name}).status_code,200)
                self.assertEqual(c.patch('/api/me',headers=headers,json={'password':'abcdef'}).status_code,429)
