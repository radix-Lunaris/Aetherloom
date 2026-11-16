import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
from aetherloom.runtime import JavaRuntime,choose_java,required_java,find_runtimes,search_locations,_probe,launch_compatibility,compatibility
from aetherloom.java_download import install_runtime,extract_zip,trusted_url,release_package
from aetherloom.shared_session import SharedSession


def java(path,major=17,version='17.0.21',bits=64,experimental=False):
    return JavaRuntime(str(path),version,major,bits,'amd64','Eclipse Adoptium','test',experimental)


class JavaManagerTests(unittest.TestCase):
    def test_manual_version_override_keeps_platform_checks(self):
        for major in (8,11,17,21,25):
            runtime=java('user-choice',major,experimental=True)
            self.assertEqual(launch_compatibility(runtime),'')
            self.assertTrue(compatibility(runtime,17))
        self.assertTrue(launch_compatibility(java('x86',bits=32)))
        self.assertTrue(launch_compatibility(JavaRuntime('arm','25',25,64,'aarch64')))

    def test_selects_stable_matching_major_and_architecture(self):
        candidates=[java('old',version='17.0.15'),java('current'),java('loom',25,'25-loom',experimental=True),java('newest',25,'25.0.3'),java('x86',version='17.0.99',bits=32)]
        self.assertEqual(choose_java(candidates,17).path,'current')
        self.assertEqual(choose_java(candidates,25).path,'newest')
        self.assertIsNone(choose_java(candidates,21))
        self.assertEqual(required_java({'javaVersion':{'majorVersion':21},'_client':'friendly'}),21)
        self.assertEqual(required_java({'id':'1.20.1'}),17)
        self.assertEqual(required_java({'id':'1.20.5'}),21)
        self.assertEqual(required_java({'id':'26.1'}),25)
        self.assertEqual(required_java({'id':'1.8.9'}),8)
        with self.assertRaises(ValueError):required_java({'id':'unknown-pack'})

    def test_known_locations_include_screenshot_paths_without_home_or_disk_scan(self):
        roots,direct=search_locations('/games/minecraft',env={'APPDATA':'/user/roaming','LOCALAPPDATA':'/user/local','JAVA_HOME':'/env/jdk','ProgramFiles':'/programs'},home='/user')
        paths={str(path) for path,source in roots}
        for expected in ('/user/roaming/.hmcl/java','/user/.jdks','/programs/Microsoft','/env/jdk'):
            self.assertIn(str(Path(expected)),paths)
        self.assertNotIn(str(Path('/user')),paths)
        self.assertNotIn(str(Path('/')),paths)

    def test_probe_does_not_mistake_aetherloom_directory_for_loom_vm(self):
        output=' java.version = 17.0.15\n os.arch = amd64\n sun.arch.data.model = 64\n user.dir = C:/Aetherloom\n java.vendor = Microsoft\n'
        result=type('Result',(),{'returncode':0,'stdout':'','stderr':output})()
        with patch('aetherloom.runtime.subprocess.run',return_value=result):
            info=_probe('java')
        self.assertFalse(info.experimental);self.assertEqual(info.major,17)

    def test_discovery_deduplicates_without_probing_mods_or_saves(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for folder in ('runtime/java17','saves/java17','mods/java17'):
                home=root/folder;(home/'bin').mkdir(parents=True)
                (home/'release').write_text('JAVA_VERSION="17.0.21"')
                (home/'bin'/('java.exe' if __import__('os').name=='nt' else 'java')).touch()
            with patch('aetherloom.runtime.inspect_java',side_effect=lambda p:java(p)) as probe:
                result=find_runtimes(root,locations=[(root,'game'),(root/'runtime','cache')])
            self.assertEqual(len(result),1);self.assertEqual(probe.call_count,1)


class JavaDownloadTests(unittest.TestCase):
    def archive(self,entries=None):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            for name,content in entries or [('jre/bin/java.exe',b'test-executable'),('jre/NOTICE',b'upstream license')]:archive.writestr(name,content)
        return data.getvalue()

    def package(self,data):
        return dict(url='https://github.com/adoptium/temurin17-binaries/releases/download/test/java.zip',size=len(data),sha256=hashlib.sha256(data).hexdigest(),major=17,version='17.0.21')

    def test_verified_install_preserves_license_and_is_reusable(self):
        data=self.archive()
        with tempfile.TemporaryDirectory() as d,patch('aetherloom.java_download.WINDOWS_RUNTIME_INSTALL',True):
            path=install_runtime(17,d,package=self.package(data),open_request=lambda url:io.BytesIO(data),probe=lambda p:java(p))
            self.assertTrue(Path(path).is_file())
            self.assertEqual((Path(path).parent.parent/'NOTICE').read_bytes(),b'upstream license')
            reused=install_runtime(17,d,package=self.package(data),open_request=lambda url:self.fail('Unexpected repeat download'),probe=lambda p:java(p))
            self.assertEqual(path,reused)

    def test_wrong_hash_cancel_and_incompatible_binary_never_publish_install(self):
        data=self.archive()
        for mode in ('hash','cancel','binary'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d,patch('aetherloom.java_download.WINDOWS_RUNTIME_INSTALL',True):
                root=Path(d);old=root/'old-user-java';old.mkdir();(old/'keep').write_text('original')
                package=self.package(data);cancel=threading.Event()
                if mode=='hash':package['sha256']='0'*64
                class Response(io.BytesIO):
                    def read(self,size=-1):
                        if mode=='cancel':cancel.set()
                        return super().read(size)
                probe=lambda p:java(p,major=21 if mode=='binary' else 17)
                with self.assertRaises(ValueError):
                    install_runtime(17,root,package=package,open_request=lambda url:Response(data),probe=probe,cancel=cancel)
                self.assertEqual([p.name for p in root.iterdir()],['old-user-java'])
                self.assertEqual((old/'keep').read_text(),'original')

    def test_archive_escape_duplicate_and_symlink_rejected_before_writes(self):
        cases=[self.archive([('../escape',b'x')]),self.archive([('jre/a',b'x'),('JRE/A',b'y')]),self.archive([('jre/NUL',b'x')])]
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            link=zipfile.ZipInfo('jre/link');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(link,'outside')
        cases.append(buffer.getvalue())
        for data in cases:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);archive=root/'input.zip';archive.write_bytes(data);output=root/'out';output.mkdir()
                with self.assertRaises(ValueError):extract_zip(archive,output,threading.Event())
                self.assertEqual(list(output.iterdir()),[])

    def test_official_metadata_and_unknown_redirect_rejected(self):
        data=self.archive();package=self.package(data)
        record={'version':{'major':17,'semver':'17.0.21+9'},'binary':{'architecture':'x64','image_type':'jre','os':'windows','package':{'size':len(data),'checksum':package['sha256'],'link':package['url']}}}
        result=release_package(17,open_request=lambda url:io.BytesIO(json.dumps([record]).encode()))
        self.assertEqual(result['sha256'],package['sha256'])
        for url in ('http://github.com/adoptium/a','https://example.com/java.zip','https://github.com/unrelated/project/releases/download/java.zip','https://github.com:8080/adoptium/temurin17-binaries/releases/download/v/java.zip'):
            with self.assertRaises(ValueError):trusted_url(url)

    def test_missing_jre_falls_back_to_same_major_jdk(self):
        package=self.package(self.archive())
        record={'version':{'major':17},'binary':{'architecture':'x64','image_type':'jdk','os':'windows','package':dict(checksum=package['sha256'],link=package['url'],size=package['size'])}}
        queries=[]
        def request(url):
            queries.append(url)
            return io.BytesIO(json.dumps([] if 'image_type=jre' in url else [record]).encode())
        result=release_package(17,request)
        self.assertEqual(result['major'],17);self.assertEqual(len(queries),2)


class ManagedJavaTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_shared_runtime_is_resolved_before_cloud_operations(self):
        with tempfile.TemporaryDirectory() as d:
            binding={'root':d,'version':'forge','java':'obsolete','java_mode':'auto'}
            session=SharedSession('https://unused.invalid','not-logged',Path(d)/'cache','room',binding,lambda *args:None)
            with patch('aetherloom.launcher.manifest',return_value={'javaVersion':{'majorVersion':17}}),patch('aetherloom.runtime.find_runtimes',return_value=[java('java17')]),patch('aetherloom.cloud.API.__call__',side_effect=AssertionError('Unexpected cloud request')):
                await session.prepare_java()
            self.assertEqual(binding['java'],'java17')
            with patch('aetherloom.launcher.manifest',return_value={'javaVersion':{'majorVersion':21}}),patch('aetherloom.runtime.find_runtimes',return_value=[java('java17')]):
                with self.assertRaisesRegex(ValueError,'Java 21'):await session.prepare_java()
