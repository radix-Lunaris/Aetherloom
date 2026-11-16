"""Measured stage progress; 100% is reserved for verified completion."""
import time

class TransferProgress:
    def __init__(self,operation,callback=None):
        self.operation=operation;self.callback=callback or (lambda state:None)
        self.percent=0.;self.last_time=0.;self.last_stage=None

    def emit(self,stage,done=0,total=0,start=0,end=0,unit='bytes',message=''):
        fraction=min(1.,max(0.,done/total)) if total else 1.
        percent=max(self.percent,min(99.,start+(end-start)*fraction))
        now=time.monotonic()
        if stage==self.last_stage and now-self.last_time<.15 and percent<end:return
        self.percent=percent;self.last_time=now;self.last_stage=stage
        self.callback(dict(operation=self.operation,stage=stage,done=done,total=total,
                           unit=unit,percent=percent,message=message))

    def finish(self,message='完成'):
        self.percent=100.
        self.callback(dict(operation=self.operation,stage='complete',percent=100.,message=message))
