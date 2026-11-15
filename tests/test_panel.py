import os,tempfile,unittest
from unittest.mock import patch
try:
    from fastapi.testclient import TestClient
    from aetherloom.server import create_app,add_user
    AVAILABLE=True
except ImportError:AVAILABLE=False

@unittest.skipUnless(AVAILABLE,'Install server dependencies')
class PanelTests(unittest.TestCase):
    def test_panel_login_and_admin_boundaries(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'AETHERLOOM_PANEL':'1'}):
            app=create_app(d)
            add_user(app.state.store,'root','a-panel-root-password','root')
            add_user(app.state.store,'player','a-panel-user-password','player')
            with TestClient(app) as c:
                page=c.get('/')
                self.assertIn('Aetherloom',page.text)
                self.assertIn("frame-ancestors 'none'",page.headers['content-security-policy'])
                self.assertEqual(c.get('/panel.js').status_code,200)
                self.assertEqual(c.get('/panel.css').status_code,200)
                self.assertEqual(c.get('/docs').status_code,404)
                self.assertEqual(c.get('/openapi.json').status_code,404)
                self.assertEqual(c.get('/api/users').status_code,401)
                p=c.post('/api/login',json={'username':'player','password':'a-panel-user-password'}).json()
                self.assertEqual(c.get('/api/users',headers={'Authorization':'Bearer '+p['token']}).status_code,403)
                r=c.post('/api/login',json={'username':'root','password':'a-panel-root-password'}).json()
                result=c.get('/api/users',headers={'Authorization':'Bearer '+r['token']})
                self.assertEqual(result.status_code,200)
                self.assertEqual(set(result.json()[0]),{'name','role','disabled'})
                for _ in range(10):self.assertEqual(c.post('/api/login',json={'username':'nobody','password':'wrong'}).status_code,401)
                self.assertEqual(c.post('/api/login',json={'username':'nobody','password':'wrong'}).status_code,429)
