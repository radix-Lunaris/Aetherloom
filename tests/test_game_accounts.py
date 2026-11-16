import io,json,os,tempfile,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from aetherloom.game_accounts import GameAccounts,GameAuth,dpapi,ISSUER,profile
from aetherloom.environment import encode,decode,authentication,validate_account
from aetherloom.process_log import collect

ID='81f14300fbc14a4688f00d90db478198'

class AccountTests(unittest.TestCase):
    def test_littleskin_names_and_uuid_lookup_do_not_use_offline_name_rules(self):
        self.assertEqual(profile({'name':'测试-角色','id':ID})['name'],'测试-角色')
        with self.assertRaises(ValueError):profile({'name':'bad/name','id':ID})
        from aetherloom.bridge_control import BridgeControl
        from aetherloom.launcher import offline_uuid
        import urllib.request
        with tempfile.TemporaryDirectory() as directory:
            control=BridgeControl(Path(directory)/'world',offline_uuid('Host'))
            try:
                control.register_peer({'name':'LS'+ID[:14],'uuid':ID,'actor':'member'})
                endpoint=json.loads(control.config.read_text())['endpoint']+'/identity/by-uuid/'+ID
                query=urllib.request.Request(endpoint,headers={'Authorization':'Bearer '+control.token})
                with urllib.request.urlopen(query) as response:self.assertEqual(uuid.UUID(json.load(response)['uuid']).hex,ID)
            finally:control.close()

    def test_role_selection_refresh_identity_and_logout(self):
        selected={'name':'Guest','id':ID};calls=[]
        def api(path,body=None):
            calls.append((path,body))
            if path=='':return {'skinDomains':['littleskin.cn'],'signaturePublickey':'test-public-key'}
            if path.endswith('authenticate'):return {'accessToken':'first-secret','clientToken':'client-secret','availableProfiles':[selected]}
            if path.endswith('refresh'):return {'accessToken':'rotated-secret','clientToken':'client-secret','selectedProfile':selected}
            if path.endswith('invalidate'):return {}
            raise AssertionError(path)
        # Test codec only; Windows DPAPI is exercised separately below.
        def codec(data,decrypt=False):return bytes(b^0xa5 for b in data)
        with tempfile.TemporaryDirectory() as directory:
            accounts=GameAccounts(directory,api,codec)
            result,profiles=accounts.login('email','password-never-stored')
            key=accounts.add(result,profiles[0]);auth=accounts.refresh(key,'Guest',ID)
            self.assertEqual(auth.uuid,ID);self.assertNotIn('rotated-secret',repr(auth))
            raw=accounts.path.read_bytes()
            for secret in (b'first-secret',b'rotated-secret',b'password-never-stored'):self.assertNotIn(secret,raw)
            reloaded=GameAccounts(directory,api,codec);self.assertEqual(reloaded.public(key),selected)
            with self.assertRaisesRegex(ValueError,'绑定不同'):reloaded.refresh(key,'Other',ID)
            with self.assertRaises(ValueError):GameAuth('Guest',ID,'token',{},issuer='https://untrusted.invalid')
            accounts.remove(key);self.assertNotIn(key,accounts.rows)

    @unittest.skipUnless(os.name=='nt','Windows credential encryption')
    def test_current_user_dpapi_roundtrip(self):
        secret=b'private-test-token';encrypted=dpapi(secret)
        self.assertNotIn(secret,encrypted);self.assertEqual(dpapi(encrypted,True),secret)

    def test_room_policy_does_not_change_game_environment_or_merge_identities(self):
        environment={'minecraft':'1.20.1','loader':'forge','loader_version':'47.4.22'}
        external=encode(dict(environment,authentication='littleskin'))
        self.assertEqual(decode(external),environment);self.assertEqual(authentication(external),'littleskin')
        with self.assertRaises(ValueError):validate_account({},external)
        validate_account({'game_account':'saved-account'},external)
        with self.assertRaises(ValueError):validate_account({'game_account':'saved-account'},encode(environment))
        self.assertEqual(authentication('1.20.1 Forge47.4.22'),'offline')

    def test_game_output_redaction_across_chunks(self):
        class Stream:
            def __init__(self):self.chunks=iter([b'prefix top-',b'secret suffix top-secret\n',b''])
            def read1(self,size):return next(self.chunks)
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            process=SimpleNamespace(stdout=Stream());path=Path(directory)/'game.log'
            collect(process,path,['top-secret']);process.aetherloom_log_thread.join(3)
            self.assertEqual(path.read_bytes(),b'prefix [REDACTED] suffix [REDACTED]\n')
