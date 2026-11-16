import tempfile
import unittest
import sys
from unittest.mock import patch
from pathlib import Path
from aetherloom.bridge_control import BridgeControl
from aetherloom.launcher import offline_uuid
from aetherloom.shared_session import assets

class BridgeIdentityTests(unittest.TestCase):
    def test_managed_bridge_upgrade_preserves_old_mod_without_duplicate_id(self):
        import zipfile
        from aetherloom.shared_session import SharedSession
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resources=root/'assets';resources.mkdir();run=root/'run';(run/'mods').mkdir(parents=True)
            new=resources/'aetherloom-bridge-0.1.1.jar';new.write_bytes(b'new-managed-jar')
            old=run/'mods/aetherloom-bridge-0.1.0.jar'
            with zipfile.ZipFile(old,'w') as archive:archive.writestr('META-INF/mods.toml','[[mods]]\nmodId="aetherloom_bridge"\nversion="0.1.0"')
            original=old.read_bytes();session=object.__new__(SharedSession);session.backend='bridge'
            with patch('aetherloom.shared_session.assets',return_value=resources):
                session.install_control(run);session.install_control(run)
            self.assertFalse(old.exists());self.assertEqual((run/'mods'/new.name).read_bytes(),new.read_bytes())
            backups=list((run/'.aetherloom/disabled-mods').iterdir())
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),original)

    def test_single_file_build_uses_extracted_assets(self):
        with tempfile.TemporaryDirectory() as d,patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',d,create=True):
            self.assertEqual(assets(),Path(d)/'assets')

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
