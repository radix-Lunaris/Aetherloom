import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from aetherloom.launcher import inside, manifest, offline_uuid, LaunchError
from aetherloom.store import Authority, Conflict

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.s = Authority(self.root, clock=lambda:self.now)
        self.room = self.s.create("owner")

    def test_unique_host_under_concurrency(self):
        def claim(i):
            try:
                return self.s.claim(self.room, str(i))
            except Conflict:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as p:
            results = list(p.map(claim, range(16)))
        self.assertEqual(sum(x is not None for x in results), 1)

    def test_stale_lease_and_recovery_confirmation(self):
        old = self.s.claim(self.room, "A")
        self.now += 61
        with self.assertRaises(Conflict):
            self.s.claim(self.room,"B")
        new = self.s.claim(self.room,"B",True)
        with self.assertRaises(Conflict):
            self.s.commit(self.room,"A",old["token"],old["epoch"],None,{})
        self.assertGreater(new["epoch"],old["epoch"])

    def test_commit_requires_parent_and_preserves_candidates(self):
        lease = self.s.claim(self.room,"A")
        h = self.s.put_blob(b"hello")
        m = {"level.dat":{"size":5,"pieces":[[0,5,h]]}}
        with self.assertRaises(Conflict):
            self.s.commit(self.room,"A",lease["token"],lease["epoch"],"wrong",m)
        head = self.s.commit(self.room,"A",lease["token"],lease["epoch"],None,m)
        candidate = self.s.candidate(self.room,"old",None,m)
        with self.assertRaises(PermissionError):
            self.s.restore(self.room,"old",candidate,head)
        new = self.s.claim(self.room,"B")
        with self.assertRaises(Conflict):
            self.s.restore(self.room,"owner",candidate,head)
        self.s.commit(self.room,"B",new["token"],new["epoch"],head,m)
        with self.assertRaises(Conflict):
            self.s.restore(self.room,"owner",candidate,head)

    def test_bad_manifest_cannot_commit(self):
        a = self.s.claim(self.room,"A")
        for path in ["../escape", "C:/x", "a\\b"]:
            with self.assertRaises(ValueError):
                self.s.commit(self.room,"A",a["token"],a["epoch"],None,
                              {path:{"size":0,"pieces":[]}})
        h=self.s.put_blob(b"x")
        with self.assertRaises(ValueError):
            self.s.commit(self.room,"A",a["token"],a["epoch"],None,
                {"a":{"size":2,"pieces":[[1,1,h]]}})

    def test_version_inheritance_and_escape(self):
        def write(v, data):
            d=self.root/"versions"/v
            d.mkdir(parents=True)
            (d/(v+".json")).write_text(json.dumps(data))
        write("base",{"id":"base","mainClass":"Main","arguments":{"game":["base"]}})
        write("forge",{"id":"forge","inheritsFrom":"base","arguments":{"game":["forge"]}})
        m=manifest(self.root,"forge")
        self.assertEqual(m["_client"],"base")
        self.assertEqual(m["arguments"]["game"],["base","forge"])
        with self.assertRaises(LaunchError):
            inside(self.root,"../escape")
        write("cycle",{"id":"cycle","inheritsFrom":"cycle"})
        with self.assertRaises(LaunchError):
            manifest(self.root,"cycle")
        self.assertEqual(offline_uuid("Notch"),"b50ad385829d3141a2167e7d7539ba7f")

if __name__ == "__main__":
    unittest.main()

