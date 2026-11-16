"""CraftLink status vocabulary backed by measured values, never guessed NAT."""
import asyncio,socket
from .vendor.craftlink import stun

def nat_values(profile):
    sub=getattr(profile.nat_type,'value','unknown')
    filtering=getattr(profile.filtering,'value','unknown')
    grade='adf' if filtering=='adf_or_eif' else filtering
    symmetric={'sym_easy_inc':'递增·可预测','sym_easy_dec':'递减·可预测','sym_hard':'随机·难'}
    if sub in symmetric:text='NAT4 对称型（'+symmetric[sub]+'）'
    elif sub=='cone':
        text='NAT1/2（完全锥形或地址受限锥形·P2P 轻松）' if grade in ('eif','adf') else 'NAT3 端口受限锥形' if grade=='apdf' else '锥形（过滤未测，NAT1/2/3 待定）'
    else:text='未知（映射未测出）'
    detail=f'独立诊断套接字 · 已响应 {profile.responded_servers}/{profile.asked} 个已探测端点（候选 {profile.pool_size}）'
    samples=getattr(profile,'mapped_ports',[])
    if samples:detail+=' · 映射端口 '+','.join(map(str,samples[:8]))+' · 步长 '+str(getattr(profile,'step',0))
    return {'nat':text,'inbound':stun.NAT_FILTER_LABEL.get(grade,'入站未测'),
            'public':':'.join(map(str,profile.public)) if profile.public else '未测出',
            'detail':detail,
            'subtype':sub,'filtering':filtering}

def probe_nat(servers=None):
    # Dedicated daemon diagnostic thread, isolated from the networking loop.
    # Run upstream's blocking probes inline here to avoid non-daemon executor
    # workers holding the application open during an unresponsive DNS lookup.
    loop=asyncio.new_event_loop()
    def inline(executor,function,*args):
        future=loop.create_future()
        try:future.set_result(function(*args))
        except Exception as error:future.set_exception(error)
        return future
    loop.run_in_executor=inline
    # Match CraftLink's diagnostic entrypoint: 3s responses, four answers,
    # original third-probe and filtering budgets. Do not use connect shortcuts.
    try:
        from .diagnostics import event
        profile=loop.run_until_complete(stun.detect_nat_type(servers=servers,log=lambda line:event('nat.probe',message=line)))
        return nat_values(profile)
    finally:loop.close()

def human_bytes(value):
    value=float(value or 0)
    for suffix in ('B','KiB','MiB','GiB'):
        if value<1024 or suffix=='GiB':return f'{value:.1f} {suffix}'
        value/=1024
