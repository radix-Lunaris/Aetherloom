"""Vanilla releases with a version-specific control mapping or named classes."""
import re

LEGACY_LAN_RELEASES = frozenset({
    '1.8', '1.8.1', '1.8.2', '1.8.3', '1.8.4',
    '1.8.5', '1.8.6', '1.8.7', '1.8.8', '1.8.9',
    '1.9.4', '1.10.2', '1.11.2', '1.12.2', '1.13.2',
})


def supports_vanilla_control(version):
    if version in LEGACY_LAN_RELEASES:
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
