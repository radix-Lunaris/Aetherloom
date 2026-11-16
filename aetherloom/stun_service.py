"""Independent, bounded STUN process for the two-port filtering probes."""
import asyncio,signal
from .vendor.craftlink import stun_server

async def main():
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    for value in (signal.SIGINT,signal.SIGTERM):
        try:loop.add_signal_handler(value,stop.set)
        except NotImplementedError:pass
    try:
        if not await stun_server.start_stun_server():raise RuntimeError('STUN startup failed')
        if len(stun_server._server['transports'])!=2:raise RuntimeError('Both STUN sockets must be available')
        await stop.wait()
    finally:await stun_server.stop_stun_server()

if __name__=='__main__':asyncio.run(main())
