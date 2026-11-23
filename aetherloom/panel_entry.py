import ipaddress
import re

def validate_entry(value):
    if set(value)!={"address","domain","port","path","icp"}:
        raise ValueError("面板设置字段不完整")
    value=dict(value)
    value["address"]=str(ipaddress.IPv4Address(value["address"]))
    if not isinstance(value["domain"],str) or len(value["domain"])>253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",label) for label in value["domain"].split(".")):
        raise ValueError("域名无效")
    if type(value["port"])!=int or not 1024<=value["port"]<=65535 or abs(value["port"]-47192)<=1:
        raise ValueError("请选择独立高位端口")
    if not re.fullmatch(r"[A-Za-z0-9]{16}",value["path"]):
        raise ValueError("安全路径须为 16 位字母数字")
    if not isinstance(value["icp"],str) or len(value["icp"])>80:
        raise ValueError("备案号过长")
    return value


