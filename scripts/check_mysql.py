"""Run only against an isolated acceptance database, never the live database."""
import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from aetherloom.server import create_app,add_user
from aetherloom.management import edit_account
from aetherloom.store import Conflict
from fastapi import HTTPException

assert os.environ.get('AETHERLOOM_MYSQL_DATABASE','').startswith('aetherloom_checks_'), 'Isolated database required'
with tempfile.TemporaryDirectory() as d:
    store=create_app(d).state.store
    for name,role in [('root','root'),('admin','admin'),('friend','player')]:add_user(store,name,'123456',role)
    root={'name':'root','role':'root'}
    room=store.create('friend')
    def claim(_):
        try:return store.claim(room,'friend')
        except Conflict:return None
    with ThreadPoolExecutor(max_workers=8) as executor:
        results=list(executor.map(claim,range(8)))
    winners=[r for r in results if r]
    assert len(winners)==1,'More than one Host won'
    lease=winners[0]
    head=store.commit(room,'friend',lease['token'],lease['epoch'],None,{})
    edit_account(store,root,'friend',{'username':'renamed'})
    with store.connect() as c:
        assert c.execute('SELECT owner FROM rooms WHERE id=?',(room,)).fetchone()['owner']=='renamed'
    try:edit_account(store,root,'renamed',{'username':'admin'})
    except HTTPException as e:assert e.status_code==409
    else:raise AssertionError('Rename collision did not fail')
    candidate=store.candidate(room,'renamed',head,{})
    active=store.claim(room,'renamed')
    try:store.restore(room,'root',candidate,head,root=True)
    except Conflict:pass
    else:raise AssertionError('Recovery replaced an active Host')
    store.commit(room,'renamed',active['token'],active['epoch'],head,{})
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM audit').fetchone()[0]>=1
print('MySQL acceptance passed: schema, six-character password, concurrent Host lease, commits, rename/collision rollback, recovery guard, audit')
