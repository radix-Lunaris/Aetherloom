"""Bounded runtime discovery inside the explicitly selected game root."""
import os
from pathlib import Path
import re
import subprocess


def hidden_process():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def java_major(java):
    result = subprocess.run([str(java), '-version'], capture_output=True, text=True,
                            errors='replace', timeout=10, **hidden_process())
    match = re.search(r'version "(\d+)(?:\.(\d+))?', result.stderr + result.stdout)
    if result.returncode or not match:
        raise ValueError('无法读取 Java 版本')
    return int(match[2] if match[1] == '1' else match[1])


def discover_java(root, required=17):
    """Known layouts only, depth <= 5, <= 2048 directories, no links or PATH scan.

    Never runs arbitrary executables found while browsing: candidates must have a
    Java release descriptor alongside bin/java. Manual paths remain available.
    """
    root = Path(root).resolve()
    if not root.is_dir(): return []
    found = []
    pending = [(root, 0)]
    visited = 0
    while pending and visited < 2048:
        folder, depth = pending.pop(0)
        visited += 1
        binary = folder / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        release = folder / 'release'
        if binary.is_file() and release.is_file() and not binary.is_symlink():
            try:
                metadata = release.read_text(encoding='utf-8', errors='replace')
                version = re.search(r'JAVA_VERSION="(\d+)(?:\.(\d+))?', metadata)
                major = int(version[2] if version[1] == '1' else version[1]) if version else 0
                if major >= required:
                    found.append((major, str(binary)))
            except (OSError, ValueError): pass
        if depth >= 5: continue
        try:
            for child in sorted(folder.iterdir()):
                if visited+len(pending)>=2048:break
                if child.is_symlink() or (hasattr(child, 'is_junction') and child.is_junction()): continue
                if not child.is_dir(): continue
                if depth == 0 and not any(word in child.name.lower() for word in ('java','jdk','jre','runtime')): continue
                if child.name.lower() in ('saves','assets','libraries','mods','versions','.git'): continue
                if root not in child.resolve().parents: continue
                pending.append((child, depth + 1))
        except OSError: continue
    return [path for _, path in sorted(found, key=lambda item: (item[0] != required, item[0], item[1]))]
