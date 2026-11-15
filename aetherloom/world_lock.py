"""Acquire Minecraft's session.lock byte-range lock before touching a world."""
import os
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def closed_world(world,require_level=True):
    world=Path(world).resolve()
    if require_level and not (world/'level.dat').is_file():raise ValueError('所选目录不是Minecraft世界：缺少level.dat')
    lock=(world/'session.lock').open('a+b')
    acquired=False
    try:
        lock.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except OSError:
            raise ValueError('世界仍被游戏占用，请保存并退出世界后再操作') from None
        yield world
    finally:
        if acquired:
            lock.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.lockf(lock,fcntl.LOCK_UN)
        lock.close()
