"""Bounded transfer workers; progress stays on the orchestration thread."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED

def transfer(items,worker,workers=4):
    iterator=iter(items)
    with ThreadPoolExecutor(max_workers=max(1,min(8,workers)),thread_name_prefix='Aetherloom transfer') as pool:
        pending=set()
        def submit():
            try:item=next(iterator)
            except StopIteration:return False
            pending.add(pool.submit(worker,item));return True
        for _ in range(max(1,min(8,workers))):
            if not submit():break
        try:
            while pending:
                done,pending=wait(pending,return_when=FIRST_COMPLETED)
                for future in done:
                    result=future.result()
                    yield result
                    submit()
        except BaseException:
            for future in pending:future.cancel()
            raise
