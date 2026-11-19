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
                self.assertEqual(send('stats',players=2),200);self.assertEqual(control.world_players,2)
                for count in (-1,True,'2',10001):
                    with self.assertRaises(urllib.error.HTTPError):send('stats',players=count)
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

    def test_existing_default_binding_automatically_selects_installed_loader(self):
        from unittest.mock import patch
        binding = {'root':'installed', 'version':'renamed pack', 'control_backend':'bridge'}
        for loader, version, release, expected in (
            ('forge','47.4.22','1.20.1','bridge'),
            ('forge','43.4.12','1.19.2','agent'),
            ('neoforge','21.1.264','1.21.1','agent'),
            ('fabric','0.20.1','1.21.11','agent'),
            ('quilt','0.30.2','1.21.1','agent'),
        ):
            with self.subTest(loader=loader, release=release), patch('aetherloom.environment.describe',
                return_value={'minecraft':release,'loader':loader,'loader_version':version}):
                self.assertEqual(select_backend(binding),expected)

    def test_vanilla_requires_a_control_mapping_or_named_runtime(self):
        from unittest.mock import patch
        binding = {'root':'installed', 'version':'vanilla', 'control_backend':'auto'}
        for version, supported in (
            ('1.2.5',False), ('1.7.5',True), ('1.7.10',True), ('1.8.5',True), ('1.13.2',True), ('1.14.3',True), ('1.14.4',True),
            ('1.19.2',True), ('1.21.11',True), ('26.3',True),
        ):
            with self.subTest(version=version), patch('aetherloom.environment.describe',
                return_value={'minecraft':version,'loader':'vanilla','loader_version':''}):
                if supported:
                    self.assertEqual(select_backend(binding),'agent')
                else:
                    with self.assertRaisesRegex(ValueError,'仍可离线启动'):
                        select_backend(binding)

    def test_legacy_controller_has_exact_bundled_namespaces(self):
        import hashlib
        from aetherloom.vanilla_control import LEGACY_LAN_RELEASES
        folder=Path(__file__).resolve().parents[1]/'agent/resources'
        source=json.loads((folder/'LEGACY-MAPPINGS-SOURCE.json').read_text(encoding='utf-8'))
        self.assertEqual(set(LEGACY_LAN_RELEASES),{row['version'] for row in source['versions']})
        for row in source['versions']:
            for flavor in ('vanilla','fabric'):
                with self.subTest(version=row['version'], flavor=flavor):
                    file=folder/f"legacy-{flavor}-{row['version']}.properties"
                    data=file.read_text(encoding='ascii').encode('ascii')
                    self.assertEqual(hashlib.sha256(data).hexdigest(),row[flavor+'_sha256'])

    def test_legacy_fabric_requires_matching_intermediary(self):
        from unittest.mock import patch
        binding = {'root':'installed', 'version':'renamed', 'control_backend':'auto'}
        env = {'minecraft':'1.8.5','loader':'fabric','loader_version':'0.19.3'}
        with patch('aetherloom.environment.describe',return_value=env), patch('aetherloom.launcher.manifest') as manifest:
            manifest.return_value={'libraries':[{'name':'net.legacyfabric:intermediary:1.8.5'}]}
            self.assertEqual(select_backend(binding),'agent')
            manifest.return_value={'libraries':[{'name':'net.legacyfabric:intermediary:1.8.6'}]}
            with self.assertRaisesRegex(ValueError,'Intermediary'):
                select_backend(binding)

    def test_historical_aliases_use_exact_raw_client_and_thread_hook(self):
        import hashlib
        from aetherloom.vanilla_control import CALAMUS_VANILLA_RELEASES, FABRIC_114_RELEASES
        folder=Path(__file__).resolve().parents[1]/'agent/resources'
        records=json.loads((folder/'HISTORICAL-MAPPINGS-SOURCE.json').read_text(encoding='utf-8'))['versions']
        self.assertEqual({row['version'] for row in records},CALAMUS_VANILLA_RELEASES|FABRIC_114_RELEASES)
        for row in records:
            version=row['version']
            self.assertEqual('fabric_sha256' in row, version in FABRIC_114_RELEASES)
            for flavor in ('vanilla','fabric'):
                if flavor+'_sha256' not in row:
                    continue
                with self.subTest(version=version, flavor=flavor):
                    file=folder/f'legacy-{flavor}-{version}.properties'
                    data=file.read_text(encoding='ascii')
                    self.assertEqual(hashlib.sha256(data.encode('ascii')).hexdigest(),row[flavor+'_sha256'])
                    properties=dict(line.split('=',1) for line in data.splitlines())
                    client=properties['class.net.minecraft.client.Minecraft']
                    self.assertIn(client+'.legacyClientTick',properties)

    def test_legacy_name_identity_cannot_be_reassigned(self):
        from aetherloom.vanilla_control import name_data_identity
        self.assertEqual(name_data_identity({'name':'host','uuid':offline_uuid('host')},'1.7.5'),'host')
        self.assertIsNone(name_data_identity({'name':'Host'},'1.7.6'))
        for binding in ({'name':'Host'}, {'name':'host','uuid':offline_uuid('other')},
                        {'name':'host','game_account':'test'}):
            with self.assertRaises(ValueError):
                name_data_identity(binding,'1.7.5')
