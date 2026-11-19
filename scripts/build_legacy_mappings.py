"""Generate small, exact legacy control aliases from Legacy Fabric Tiny v2."""
import csv
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAVEN = 'https://repo.legacyfabric.net/legacyfabric/net/legacyfabric/intermediary/'
RESOURCE = ROOT / 'agent/resources'
CLASSES = {
    'net.minecraft.client.Minecraft': 'class_1600',
    'net.minecraft.client.gui.screens.TitleScreen': 'class_624',
    'net.minecraft.client.gui.screens.ConnectScreen': 'class_472',
    'net.minecraft.client.gui.screens.DisconnectedScreen': 'class_475',
    'net.minecraft.client.multiplayer.ClientPacketListener': 'class_1845',
    'net.minecraft.server.level.ServerPlayer': 'class_798',
    'net.minecraft.server.MinecraftServer': 'server/MinecraftServer',
}
MEMBERS = {
    'class_1600': {
        'getInstance': 'method_2965', 'getSingleplayerServer': 'method_2909',
        'level': 'field_3803', 'player': 'field_10310', 'screen': 'field_3816',
        'legacyRunDirectory': 'field_3762', 'submitLegacyTick': 'method_6637',
        'legacyOpenWorld': 'method_6636', 'legacySetScreen': 'method_2928',
        'legacyDetach': 'method_2929', 'stop': 'method_2949',
        'getConnection': 'method_2960',
    },
    'server/MinecraftServer': {
        'legacyLevelName': 'method_2028', 'getPlayerCount': 'method_2043',
        'halt': 'method_3038', 'stopServer': 'method_3034', 'runServer': 'run',
        'setUsesAuthentication': 'method_3022', 'getDefaultGameType': 'method_3026',
        'publishServer': 'method_3000',
    },
    'class_1845': {'getOnlinePlayers': 'method_9656', 'getLocalGameProfile': 'method_9657'},
    'class_864': {'getUUID': 'method_6099', 'setUUID': 'method_12973', 'legacyUuid': 'field_6116'},
    'class_988': {'getGameProfile': 'method_8429'},
}


def parse(raw):
    classes, members = {}, {}
    lines = raw.decode('utf-8').splitlines()
    if lines[0] != 'tiny\t2\t0\tofficial\tintermediary':
        raise ValueError('Unexpected legacy mapping namespaces')
    owner = None
    for line in lines[1:]:
        items = line.split('\t')
        if items[0] == 'c':
            owner = items[2].removeprefix('net/minecraft/')
            classes[owner] = items[1].replace('/', '.')
        elif len(items) == 5 and items[0] == '' and items[1] in ('f', 'm'):
            if owner:
                members[owner, items[4]] = items[3]
    return classes, members


def compile_aliases(data):
    classes, members = parse(data)
    raw, mapped = {}, {}
    for semantic, owner in CLASSES.items():
        raw['class.' + semantic] = classes[owner]
        mapped['class.' + semantic] = 'net.minecraft.' + owner.replace('/', '.')
    for owner, methods in MEMBERS.items():
        for semantic, member in methods.items():
            if semantic == 'publishServer' and (owner, member) not in members:
                member='method_20311'
            if (owner, member) not in members:
                if semantic in ('setUUID', 'legacyUuid'):
                    continue
                raise KeyError((owner, member))
            raw[classes[owner] + '.' + semantic] = members[owner, member]
            mapped['net.minecraft.' + owner.replace('/', '.') + '.' + semantic] = member
    entity = 'net.minecraft.class_864'
    if not any(entity + '.' + name in mapped for name in ('setUUID', 'legacyUuid')):
        raise KeyError('No UUID write path')
    return raw, mapped


def download(version):
    url = f'{MAVEN}{version}/intermediary-{version}-v2.jar'
    with urllib.request.urlopen(url, timeout=20) as response:
        data = response.read(4 * 1024 * 1024)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        tiny = archive.read('mappings/mappings.tiny')
    return url, data, tiny


def main():
    with (ROOT / 'COMPATIBILITY.csv').open(encoding='utf-8', newline='') as catalog:
        versions = [row['minecraft_release'] for row in csv.DictReader(catalog)
                    if (1, 8) <= tuple(map(int, row['minecraft_release'].split('.'))) < (1, 14)]
    records = []
    with ThreadPoolExecutor(max_workers=8) as workers:
        for version, job in [(version, workers.submit(download,version)) for version in versions]:
            try:
                url, archive, mapping = job.result()
                aliases = compile_aliases(mapping)
            except (KeyError, ValueError, OSError) as error:
                print(version, 'not emitted:', error)
                continue
            record = {'version':version,'intermediary_url':url,'intermediary_sha256':hashlib.sha256(archive).hexdigest()}
            for flavor, properties in zip(('vanilla','fabric'), aliases):
                data = ''.join(f'{key}={value}\n' for key,value in sorted(properties.items())).encode('ascii')
                (RESOURCE / f'legacy-{flavor}-{version}.properties').write_bytes(data)
                record[flavor+'_sha256'] = hashlib.sha256(data).hexdigest()
            records.append(record)
            print(version, 'both namespaces generated', flush=True)
    (RESOURCE/'LEGACY-MAPPINGS-SOURCE.json').write_text(json.dumps({
        'license':'CC0-1.0', 'named_reference':'https://github.com/Legacy-Fabric/yarn',
        'intermediary_reference':'https://github.com/Legacy-Fabric/Legacy-Intermediaries',
        'versions':records
    },indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
