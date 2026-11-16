import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from aetherloom.bridge_control import BridgeControl
from aetherloom.game_control import agent_config,CAPABILITIES,select_backend
from aetherloom.launcher import offline_uuid

class AgentControlTests(unittest.TestCase):
    def test_capabilities_identity_and_save_barriers(self):
        with tempfile.TemporaryDirectory() as directory:
            control=BridgeControl(Path(directory)/'世界',offline_uuid('Host'),backend='agent')
            try:
                config=json.loads(control.config.read_text())
                def send(event,**extra):
                    body=dict(event=event,world=str(control.world),uuid=control.identity,port=25565,**extra)
                    request=urllib.request.Request(config['endpoint'],data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+control.token,'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=3) as response:return response.status
                for event in ('saved','ready'):
                    with self.assertRaises(urllib.error.HTTPError):send(event)
                with self.assertRaises(urllib.error.HTTPError):send('capabilities',protocol=2,component='agent',capabilities=list(CAPABILITIES))
                self.assertFalse(control.ready.is_set())
                self.assertEqual(send('capabilities',protocol=1,component='agent',capabilities=list(CAPABILITIES)),200)
                self.assertEqual(send('ready'),200)
                self.assertEqual(send('saved'),200);self.assertTrue(control.saved.is_set())
                self.assertEqual(send('error'),200)
                for event in ('saved','ready'):
                    with self.assertRaises(urllib.error.HTTPError):send(event)
                path=agent_config(control);text=path.read_text(encoding='ascii')
                self.assertIn('adapter=1.20.1-forge',text);self.assertIn('\\u4e16',text)
            finally:control.close()
            self.assertFalse(path.exists());self.assertFalse(control.config.exists())

    def test_stable_backend_is_default_and_invalid_is_rejected(self):
        self.assertEqual(select_backend({}),'bridge')
        self.assertEqual(select_backend({'control_backend':'agent'}),'agent')
        with self.assertRaises(ValueError):select_backend({'control_backend':'guess'})
