"""Stream game output while redacting credentials across read boundaries."""
import threading

def collect(process,path,secrets):
    needles=[s.encode('utf-8') for s in secrets if s]
    keep=max((len(n) for n in needles),default=1)-1
    def run():
        pending=b''
        try:
            with path.open('wb') as output:
                while chunk:=process.stdout.read1(8192):
                    pending+=chunk
                    for needle in needles:pending=pending.replace(needle,b'[REDACTED]')
                    size=max(0,len(pending)-keep)
                    output.write(pending[:size]);output.flush();pending=pending[size:]
                for needle in needles:pending=pending.replace(needle,b'[REDACTED]')
                output.write(pending)
        finally:process.stdout.close()
    thread=threading.Thread(target=run,name='Aetherloom game log',daemon=True);thread.start()
    process.aetherloom_log_thread=thread
    return process
