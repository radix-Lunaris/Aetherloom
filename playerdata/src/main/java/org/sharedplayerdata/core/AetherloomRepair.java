package org.sharedplayerdata.core;

import java.io.IOException;
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
        UUID owner=Uuids.fromIntArray(player.getIntArray("UUID"));
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
    public static void main(String[] args) {
        try {
            if (args.length!=3) throw new IllegalArgumentException("prepare|saved world UUID");
            if (!args[0].equals("prepare") && !args[0].equals("saved")) throw new IllegalArgumentException("Invalid mode");
            repair(Path.of(args[1]),UUID.fromString(args[2]),args[0].equals("saved"));
            System.out.println("OK");
        } catch (Throwable e) {
            System.err.println(e.getMessage());
            System.exit(2);
        }
    }
}
