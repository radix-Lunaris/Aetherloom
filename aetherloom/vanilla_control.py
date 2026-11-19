"""Vanilla releases with a version-specific control mapping or named classes."""
import re

LEGACY_LAN_RELEASES = frozenset({
    '1.8', '1.8.1', '1.8.2', '1.8.3', '1.8.4',
    '1.8.5', '1.8.6', '1.8.7', '1.8.8', '1.8.9',
    '1.9.4', '1.10.2', '1.11.2', '1.12.2', '1.13.2',
})
CALAMUS_VANILLA_RELEASES = frozenset({
    '1.3.1', '1.3.2', '1.4.2', '1.4.4', '1.4.5', '1.4.6', '1.4.7',
    '1.5.1', '1.5.2', '1.6.1', '1.6.2', '1.6.4', '1.7.2', '1.7.3', '1.7.4', '1.7.5',
    '1.7.6', '1.7.7', '1.7.8', '1.7.9', '1.7.10',
    '1.9', '1.9.1', '1.9.2', '1.9.3', '1.10', '1.10.1',
    '1.11', '1.11.1', '1.12', '1.12.1', '1.13', '1.13.1',
})
FABRIC_114_RELEASES = frozenset({'1.14', '1.14.1', '1.14.2', '1.14.3', '1.14.4'})
NAME_DATA_RELEASES = frozenset(version for version in CALAMUS_VANILLA_RELEASES
                               if tuple(map(int,version.split('.'))) < (1,7,6))


def name_data_identity(binding, version):
    if version not in NAME_DATA_RELEASES:
        return None
    from .launcher import game_uuid, offline_uuid
    name=binding['name']
    if not re.fullmatch(r'[a-z0-9_]{1,16}',name):
        raise ValueError('此旧版按名称保存玩家，请选用 1–16 位小写字母、数字或下划线的离线名称')
    if binding.get('game_account') or game_uuid(name,binding.get('uuid'))!=offline_uuid(name):
        raise ValueError('此旧版联机使用按名称保存的离线身份，不能改用外置登录或自定义 UUID')
    return name


def supports_vanilla_control(version):
    if version in LEGACY_LAN_RELEASES or version in CALAMUS_VANILLA_RELEASES or version in FABRIC_114_RELEASES:
        return True
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
        return False
    major, minor, *patch = map(int, version.split('.'))
    if major >= 26:
        return True
    maximum_patch = {14: 4, 15: 2, 16: 5, 17: 1, 18: 2, 19: 4, 20: 6, 21: 11}
    number = patch[0] if patch else 0
    return (
        major == 1
        and minor in maximum_patch
        and (4 if minor == 14 else 0) <= number <= maximum_patch[minor]
    )
