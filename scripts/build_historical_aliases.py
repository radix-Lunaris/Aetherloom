"""Build exact vanilla controls from local copies of upstream Tiny mappings."""
from collections import defaultdict
import csv
import hashlib
import json
import re
import zipfile

from build_legacy_mappings import CLASSES, MEMBERS, ROOT

INPUT = ROOT / '.local/loader-inputs'
RESOURCE = ROOT / 'agent/resources'
MAVEN = 'https://maven.ornithemc.net/releases/net/ornithemc/calamus'
FABRIC = 'https://maven.fabricmc.net/net/fabricmc/intermediary'
SEEDS = ('1.8.5', '1.12.2', '1.13.2')
OPTIONAL = {'getLocalGameProfile', 'getOnlinePlayers', 'setUUID', 'legacyUuid', 'submitLegacyTick'}


def tiny(data):
    classes, members = {}, {}
    for line in data.decode('utf-8').splitlines()[1:]:
        parts = line.split('\t')
        if parts[0] == 'c':
            owner=parts[1]
            classes[owner]=parts[2]
        elif len(parts)==5 and not parts[0] and parts[1] in ('m','f'):
            members[owner, parts[1], parts[2], parts[3]]=parts[4]
    return classes, members


def read_jar(path):
    with zipfile.ZipFile(path) as archive:
        return tiny(archive.read('mappings/mappings.tiny'))


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seeds():
    classes, members = defaultdict(set), defaultdict(set)
    legacy = {owner: dict(table) for owner,table in MEMBERS.items()}
    legacy['class_1600']['legacyClientTick']='method_2954'
    legacy['server/MinecraftServer']['legacyServerDirectory']='method_3040'
    for version in SEEDS:
        source=INPUT/(version+'-legacy-obf.tiny')
        calamus_classes,calamus_members=read_jar(INPUT/'calamus'/(version+'.jar'))
        official_classes,official_members=tiny(source.read_bytes())
        inverse={stable:raw for raw,stable in official_classes.items()}
        for semantic,owner in CLASSES.items():
            classes[semantic].add(calamus_classes[inverse['net/minecraft/'+owner]])
        for owner,table in legacy.items():
            raw=inverse['net/minecraft/'+owner]
            aliases=defaultdict(set)
            for key,stable in official_members.items():
                if key[0]==raw and key in calamus_members:
                    aliases[stable].add((calamus_classes[raw],calamus_members[key]))
            for semantic,member in table.items():
                members[semantic].update(aliases[member])
                if semantic=='publishServer':
                    members[semantic].update(aliases['method_20311'])
    return classes,members


def translate(target, class_keys, member_keys, *, intermediary=False, name_only=False):
    classes,members=target
    inverse={name:raw for raw,name in classes.items()}
    indexed=defaultdict(set)
    for key,name in members.items():
        stable=classes[key[0]]
        indexed[stable,name].add(name if intermediary else key[3])
    output={}
    name_fields={'legacyServerDirectory'}
    excluded={'getGameProfile','getUUID','setUUID','legacyUuid','getLocalGameProfile'} if name_only else name_fields
    for semantic, names in class_keys.items():
        candidates=[name for name in names if name in inverse]
        if len(candidates)!=1:
            raise ValueError('Missing or ambiguous class '+semantic)
        name=candidates[0]
        output['class.'+semantic]=(name if intermediary else inverse[name]).replace('/','.')
    for semantic,names in member_keys.items():
        if semantic in excluded:
            continue
        by_owner=defaultdict(set)
        for owner,name in names:
            if owner in inverse:
                by_owner[owner].update(indexed[owner,name])
        if not any(by_owner.values()) and semantic not in OPTIONAL and not (name_only and semantic=='legacyRunDirectory'):
            raise ValueError('Missing member '+semantic)
        for owner,values in by_owner.items():
            if values:
                raw=owner if intermediary else inverse[owner]
                output[raw.replace('/','.')+'.'+semantic]=','.join(sorted(values))
    if not name_only and not any(key.endswith(('.setUUID','.legacyUuid')) for key in output):
        raise ValueError('No mutable entity UUID')
    return output


def fabric_114_keys():
    classes,members=read_jar(INPUT/'1.14.4-intermediary.jar')
    client='net.minecraft.client.Minecraft'
    server='net.minecraft.server.MinecraftServer'
    connection='net.minecraft.client.multiplayer.ClientPacketListener'
    owners={
        client:{
            'getInstance':'getInstance()', 'getSingleplayerServer':'getSingleplayerServer()',
            'player':'player','level':'level','screen':'screen','legacyRunDirectory':'gameDirectory',
            'legacyClientTick':'tick()', 'legacyOpenWorld':'selectLevel(java.lang.String,java.lang.String,net.minecraft.world.level.LevelSettings)',
            'legacySetScreen':'setScreen(net.minecraft.client.gui.screens.Screen)',
            'legacyDetach':'clearLevel()', 'stop':'stop()', 'getConnection':'getConnection()',
        },
        server:{
            'legacyLevelName':'getLevelIdName()', 'getPlayerCount':'getPlayerCount()',
            'halt':'halt(boolean)', 'stopServer':'stopServer()',
            'setUsesAuthentication':'setUsesAuthentication(boolean)', 'getDefaultGameType':'getDefaultGameType()',
            'publishServer':'publishServer(net.minecraft.world.level.GameType,boolean,int)',
        },
        connection: {'getOnlinePlayers':'getOnlinePlayers()', 'getLocalGameProfile':'getLocalGameProfile()'},
        'net.minecraft.world.entity.Entity':{'getUUID':'getUUID()','setUUID':'setUUID(java.util.UUID)'},
        'net.minecraft.world.entity.player.Player':{'getGameProfile':'getGameProfile()'},
    }
    raw_classes={}
    raw_members={}
    source=(INPUT/'1.14.4-mojang.txt').read_text(encoding='utf-8').splitlines()
    for line in source:
        if line and not line.startswith((' ','#')) and line.endswith(':'):
            owner,raw=line[:-1].split(' -> ')
            raw_classes[owner]=raw.replace('.','/')
        elif line.startswith('    ') and owner in owners and ' -> ' in line:
            definition,raw=line.strip().split(' -> ')
            definition=re.sub(r'^\d+:\d+:','',definition)
            value_type,signature=definition.split(' ',1)
            raw_members[owner,signature]=(value_type,raw)

    def desc(name):
        if name.endswith('[]'):
            return '['+desc(name[:-2])
        primitive={'void':'V','int':'I','boolean':'Z'}
        return primitive.get(name,'L'+raw_classes.get(name,name.replace('.','/'))+';')

    class_keys={semantic:{classes[raw_classes[semantic]]} for semantic in CLASSES}
    member_keys=defaultdict(set)
    for owner, aliases in owners.items():
        for semantic,signature in aliases.items():
            value_type,raw=raw_members[owner,signature]
            kind='m' if '(' in signature else 'f'
            descriptor=desc(value_type)
            if kind=='m':
                arguments=signature.split('(',1)[1][:-1]
                descriptor='('+''.join(desc(name) for name in arguments.split(',') if name)+')'+descriptor
            obf=raw_classes[owner]
            stable=members[obf,kind,descriptor,raw]
            member_keys[semantic].add((classes[obf],stable))
    return class_keys,member_keys


def emit(version, kinds, source, url):
    record={'version':version,'mapping_url':url,'mapping_sha256':file_sha(source)}
    for namespace,values in kinds.items():
        data=''.join(f'{key}={value}\n' for key,value in sorted(values.items())).encode('ascii')
        (RESOURCE/f'legacy-{namespace}-{version}.properties').write_bytes(data)
        record[namespace+'_sha256']=hashlib.sha256(data).hexdigest()
    return record


def main():
    with (ROOT/'COMPATIBILITY.csv').open(encoding='utf-8',newline='') as stream:
        releases={row['minecraft_release'] for row in csv.DictReader(stream)}
    declared=json.loads((RESOURCE/'LEGACY-MAPPINGS-SOURCE.json').read_text(encoding='utf-8'))
    legacy_fabric={row['version'] for row in declared['versions']}
    calamus_keys=seeds()
    records=[]
    for version in sorted(releases-legacy_fabric,key=lambda v:tuple(map(int,v.split('.')))):
        number=tuple(map(int,version.split('.')))
        if not (1,3)<=number<(1,14):
            continue
        source=INPUT/'calamus'/(version+'.jar')
        aliases=translate(read_jar(source),*calamus_keys,name_only=number<(1,7,6))
        records.append(emit(version,{'vanilla':aliases},source,f'{MAVEN}/{version}/calamus-{version}-v2.jar'))
    keys=fabric_114_keys()
    for version in ('1.14','1.14.1','1.14.2','1.14.3','1.14.4'):
        source=INPUT/(version+'-intermediary.jar')
        target=read_jar(source)
        classes,members=keys
        members={name:values for name,values in members.items() if name!='runServer'}
        kinds={'vanilla':translate(target,classes,members),'fabric':translate(target,classes,members,intermediary=True)}
        for aliases in kinds.values():
            server=aliases['class.net.minecraft.server.MinecraftServer']
            # java.lang.Runnable fixes this spelling through obfuscation.
            aliases[server+'.runServer']='run'
        records.append(emit(version,kinds,source,f'{FABRIC}/{version}/intermediary-{version}-v2.jar'))
    (RESOURCE/'HISTORICAL-MAPPINGS-SOURCE.json').write_text(json.dumps({
        'calamus':'https://github.com/OrnitheMC/calamus',
        'fabric':'https://github.com/FabricMC/intermediary',
        'calamus_seed_sha256':{
            version:{
                'calamus':file_sha(INPUT/'calamus'/(version+'.jar')),
                'legacy_fabric_tiny':file_sha(INPUT/(version+'-legacy-obf.tiny')),
            } for version in SEEDS
        },
        'mojang_1.14.4_sha256':file_sha(INPUT/'1.14.4-mojang.txt'),
        'versions':records,
    },indent=2)+'\n',encoding='utf-8')
    print('Generated',len(records),'historical mappings')


if __name__=='__main__':
    main()
