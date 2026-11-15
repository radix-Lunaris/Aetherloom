import hashlib
from pathlib import Path
import tempfile
import unittest
try:
    from fastapi.testclient import TestClient
    from aetherloom.server import create_app, add_user
    AVAILABLE=True
except ImportError:
    AVAILABLE=False

@unittest.skipUnless(AVAILABLE,"Install server dependencies")
class ServerTests(unittest.TestCase):
    def test_auth_roles_and_lease_upload(self):
        with tempfile.TemporaryDirectory() as d:
            app=create_app(d);s=app.state.store
            add_user(s,"root","a-long-root-password","root")
            with TestClient(app) as c:
                self.assertEqual(c.get("/api/rooms").status_code,401)
                self.assertEqual(c.post("/api/login",json={"username":"root","password":"wrong"}).status_code,401)
                token=c.post("/api/login",json={"username":"root","password":"a-long-root-password"}).json()["token"]
                headers={"Authorization":"Bearer "+token}
                self.assertEqual(c.post("/api/users",headers=headers,json={"username":"friend","password":"another-long-password","role":"player"}).status_code,200)
                f=c.post("/api/login",json={"username":"friend","password":"another-long-password"}).json()["token"]
                self.assertEqual(c.get("/api/status",headers={"Authorization":"Bearer "+f}).status_code,403)
                room=c.post("/api/rooms",headers=headers).json()["id"]
                lease=c.post(f"/api/rooms/{room}/claim",headers=headers,json={}).json()
                data=b"saved world";h=hashlib.sha256(data).hexdigest()
                upload=dict(headers,**{"X-Lease":lease["token"],"X-Epoch":str(lease["epoch"])})
                self.assertEqual(c.put(f"/api/rooms/{room}/blobs/{h}",headers=upload,content=b"bad").status_code,400)
                self.assertEqual(c.put(f"/api/rooms/{room}/blobs/{h}",headers=upload,content=data).status_code,200)
                body=dict(lease,parent=None,manifest={"level.dat":{"size":len(data),"pieces":[[0,len(data),h]]}})
                body.pop("head")
                self.assertEqual(c.post(f"/api/rooms/{room}/commit",headers=headers,json=body).status_code,200)
                self.assertEqual(c.post(f"/api/rooms/{room}/renew",headers=headers,json={"token":lease["token"],"epoch":lease["epoch"]}).status_code,409)
                self.assertEqual(c.post("/api/logout",headers=headers).status_code,200)
                self.assertEqual(c.get("/api/rooms",headers=headers).status_code,401)

