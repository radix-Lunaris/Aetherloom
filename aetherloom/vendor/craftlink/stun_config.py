"""Aetherloom environment adapter for the unchanged CraftLink responder."""
import os
STUN_ENABLED=os.environ.get('AETHERLOOM_STUN_ENABLED','1')=='1'
STUN_HOST=os.environ.get('AETHERLOOM_STUN_HOST','0.0.0.0')
STUN_PORTS=(int(os.environ.get('AETHERLOOM_STUN_PORT','52718')),int(os.environ.get('AETHERLOOM_STUN_PORT2','52719')))
if len(set(STUN_PORTS))!=2 or any(not 1<=port<=65535 for port in STUN_PORTS):raise ValueError('Two distinct valid STUN ports required')
