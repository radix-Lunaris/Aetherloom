package org.sharedplayerdata.core;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Arrays;
import java.util.UUID;

/** Caller must hold session.lock. Only one explicitly selected world is accessed. */
public class AetherloomRepair {
    private static void replace(Path from, Path to) throws IOException {
        Files.move(from,to,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
    }
    public static void repair(Path world, UUID target, boolean completedSession) throws Exception {
        world=world.toRealPath();
        for (String name:new String[]{"level.dat","playerdata","players","players/data","aetherloom-playerdata-backups"})
            if (Files.isSymbolicLink(world.resolve(name))) throw new IOException("World symlinks are unsupported");
        if (Uuids.isNil(target)) throw new IOException("Invalid zero UUID");
        Path level=world.resolve("level.dat");
        Tag root=NbtIo.readCompressed(level), data=root.getCompound("Data");
        if (data==null) throw new IOException("Invalid level.dat Data");
        Path targetData=world.resolve("playerdata").resolve(target+".dat");
        if (Files.exists(targetData)) NbtIo.readCompressed(targetData);
        Tag player=data.getCompound("Player");
        if (data.contains("Player") && player==null) throw new IOException("Invalid Player compound");
        if (data.contains("singleplayer_uuid")) {
            if (player!=null) throw new IOException("Mixed embedded and referenced player data");
            repairReferencedPlayer(world,level,root,data,target,completedSession);
            return;
        }
        if (player==null) return;
        UUID owner=embeddedUuid(player);
        if (Uuids.isNil(owner)) throw new IOException("Embedded player ownership is unknown; manual review required");
        if (completedSession && !owner.equals(target)) throw new IOException("Saved player differs from verified Host identity");
        // Every operation has an immutable backup; failures never count as clean.
        Path backup=world.resolve("aetherloom-playerdata-backups").resolve(UUID.randomUUID().toString());
        Files.createDirectories(backup);
        Files.copy(level,backup.resolve("level.dat"));
        Path external=world.resolve("playerdata").resolve(owner+".dat");
        if (Files.isSymbolicLink(external)) throw new IOException("Player symlinks are unsupported");
        Files.createDirectories(external.getParent());
        Path candidate=backup.resolve("embedded-"+owner+".dat");
        NbtIo.writeCompressed(player,candidate);
        if (Files.exists(external)) {
            Tag previous=NbtIo.readCompressed(external);
            Path normalized=backup.resolve("existing-"+owner+".dat");
            NbtIo.writeCompressed(previous,normalized);
            Files.copy(external,backup.resolve("original-"+owner+".dat"));
            if (!completedSession && !Arrays.equals(Files.readAllBytes(candidate),Files.readAllBytes(normalized)))
                throw new IOException("CONFLICT: embedded and external player data differ; both preserved at "+backup);
        }
        Path playerTemp=external.resolveSibling(external.getFileName()+".aetherloom-"+UUID.randomUUID()+".tmp");
        Files.copy(candidate,playerTemp);
        replace(playerTemp,external);
        data.remove("Player");
        Path levelTemp=world.resolve("level.dat.aetherloom-"+UUID.randomUUID()+".tmp");
        NbtIo.writeCompressed(root,levelTemp);
        replace(levelTemp,level);
    }

    private static UUID embeddedUuid(Tag player) throws IOException {
        UUID uuid=Uuids.fromIntArray(player.getIntArray("UUID"));
        Tag most=player.asMap().get("UUIDMost"), least=player.asMap().get("UUIDLeast");
        if (most==null && least==null) return uuid;
        if (most==null || least==null || most.type()!=Tag.LONG || least.type()!=Tag.LONG)
            throw new IOException("Invalid legacy UUID fields");
        UUID legacy=new UUID((Long)most.rawValue(),(Long)least.rawValue());
        if (player.contains("UUID") && !legacy.equals(uuid))
            throw new IOException("Conflicting legacy and current UUID");
        return legacy;
    }

    private static void repairReferencedPlayer(Path world, Path level, Tag root, Tag data,
                                               UUID target, boolean completedSession) throws Exception {
        UUID owner=Uuids.fromIntArray(data.getIntArray("singleplayer_uuid"));
        if (Uuids.isNil(owner)) throw new IOException("Invalid singleplayer UUID reference");
        Path directory=world.resolve("players/data");
        Path ownerFile=directory.resolve(owner+".dat");
        Path targetFile=directory.resolve(target+".dat");
        if (Files.isSymbolicLink(ownerFile) || Files.isSymbolicLink(targetFile))
            throw new IOException("Player symlinks are unsupported");
        if (!Files.isRegularFile(ownerFile)) throw new IOException("Referenced player data is missing");
        NbtIo.readCompressed(ownerFile);
        if (completedSession) {
            if (!owner.equals(target)) throw new IOException("Saved player reference differs from verified Host identity");
            return;
        }
        if (owner.equals(target)) return;
        // Remove the previous host's singleplayer override. Minecraft loads
        // the new host by their own UUID in players/data, or creates a player.
        if (Files.exists(targetFile)) NbtIo.readCompressed(targetFile);
        Path backup=world.resolve("aetherloom-playerdata-backups").resolve(UUID.randomUUID().toString());
        Files.createDirectories(backup);
        Files.copy(level,backup.resolve("level.dat"));
        data.remove("singleplayer_uuid");
        Path temp=world.resolve("level.dat.aetherloom-"+UUID.randomUUID()+".tmp");
        try {
            NbtIo.writeCompressed(root,temp);
            replace(temp,level);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    static void repairNamed(Path world, UUID identity, String name, String operation) throws Exception {
        if (!name.matches("[a-z0-9_]{1,16}") ||
            !identity.equals(UUID.nameUUIDFromBytes(("OfflinePlayer:"+name).getBytes(StandardCharsets.UTF_8))))
            throw new IOException("Invalid legacy player name binding");
        world=world.toRealPath();
        Path level=world.resolve("level.dat");
        Path players=world.resolve("players");
        Path target=players.resolve(name+".dat");
        Path backups=world.resolve("aetherloom-playerdata-backups");
        for (Path path : new Path[]{level,players,target,backups})
            if (Files.isSymbolicLink(path)) throw new IOException("World symlinks are unsupported");
        if (Files.isDirectory(players)) {
            try (DirectoryStream<Path> files=Files.newDirectoryStream(players)) {
                for (Path path : files) {
                    String candidate=path.getFileName().toString();
                    if (candidate.equalsIgnoreCase(name+".dat") && !candidate.equals(name+".dat"))
                        throw new IOException("Player file has incompatible letter case; manual review required");
                }
            }
        }
        Tag root=NbtIo.readCompressed(level), data=root.getCompound("Data");
        if (data==null || data.contains("singleplayer_uuid")) throw new IOException("Unexpected legacy player layout");
        Tag external=Files.exists(target)?NbtIo.readCompressed(target):null;
        if (!data.contains("Player")) return;
        Tag player=data.getCompound("Player");
        if (player==null) throw new IOException("Invalid legacy Player compound");
        if (operation.equals("prepare-name")) throw new IOException("Legacy world still contains an unassigned singleplayer record");
        // This format keys player storage by name. An entity UUID in old NBT
        // can be random. The publisher or the verified Host supplies ownership.
        Path backup=backups.resolve(UUID.randomUUID().toString());
        Files.createDirectories(backup);
        Files.copy(level,backup.resolve("level.dat"));
        Path candidate=backup.resolve("embedded.dat");
        NbtIo.writeCompressed(player,candidate);
        if (external!=null) {
            Files.copy(target,backup.resolve("original-player.dat"));
            if (operation.equals("publish-name")) {
                Path normalized=backup.resolve("normalized.dat");
                NbtIo.writeCompressed(external,normalized);
                if (!Arrays.equals(Files.readAllBytes(candidate),Files.readAllBytes(normalized)))
                    throw new IOException("Legacy player file conflicts with embedded data; both preserved");
            }
        }
        Files.createDirectories(players);
        Path playerTemp=players.resolve(name+"."+UUID.randomUUID()+".tmp");
        Path levelTemp=world.resolve("level.dat."+UUID.randomUUID()+".tmp");
        try {
            Files.copy(candidate,playerTemp);
            replace(playerTemp,target);
            data.remove("Player");
            NbtIo.writeCompressed(root,levelTemp);
            replace(levelTemp,level);
        } finally {
            Files.deleteIfExists(playerTemp);
            Files.deleteIfExists(levelTemp);
        }
    }
    public static void main(String[] args) {
        try {
            if (args.length==4 && (args[0].equals("prepare-name") || args[0].equals("saved-name") || args[0].equals("publish-name"))) {
                repairNamed(Paths.get(args[1]),UUID.fromString(args[2]),args[3],args[0]);
            } else if (args.length==3 && (args[0].equals("prepare") || args[0].equals("saved"))) {
                repair(Paths.get(args[1]),UUID.fromString(args[2]),args[0].equals("saved"));
            } else throw new IllegalArgumentException("Invalid repair operation");
            System.out.println("OK");
        } catch (Throwable e) {
            System.err.println(e.getMessage());
            System.exit(2);
        }
    }
}
