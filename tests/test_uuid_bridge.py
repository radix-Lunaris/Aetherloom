import tempfile
import unittest
from pathlib import Path
from aetherloom.bridge_control import BridgeControl
from aetherloom.launcher import offline_uuid

class BridgeIdentityTests(unittest.TestCase):
    def test_registered_identity_cannot_alias_host_or_change_member(self):
        with tempfile.TemporaryDirectory() as d:
            control=BridgeControl(Path(d)/'world',offline_uuid('Host'),game_name='Host')
            try:
                identity={'name':'Guest','uuid':'81f14300-fbc1-4a46-88f0-0d90db478198','actor':'software-account'}
                control.register_peer(identity)
                control.register_peer(identity)
                self.assertEqual(control.peer_identities['guest']['uuid'],identity['uuid'])
                for invalid in (dict(identity,name='Host'),dict(identity,uuid=offline_uuid('Host')),dict(identity,actor='another-account'),dict(identity,name='Other')):
                    with self.assertRaises(ValueError):control.register_peer(invalid)
            finally:control.close()
