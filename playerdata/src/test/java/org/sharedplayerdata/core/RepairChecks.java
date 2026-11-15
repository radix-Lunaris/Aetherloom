package org.sharedplayerdata.core;
import java.nio.file.*;
import java.util.UUID;

public class RepairChecks {
    private static final UUID A=UUID.fromString("12345678-1234-4234-8234-123456789abc");
    private static final UUID B=UUID.fromString("22345678-1234-4234-8234-123456789abc");
    private static Tag player(UUID who,int xp) {
        Tag p=Tag.newCompound();p.put("UUID",Tag.ofUuid(who));p.put("XpLevel",Tag.ofInt(xp));return p;
    }
    private static void level(Path world,Tag player) throws Exception {
        Files.createDirectories(world);Tag root=Tag.newCompound(),data=Tag.newCompound();
        if (player!=null)data.put("Player",player);
        root.put("Data",data);NbtIo.writeCompressed(root,world.resolve("level.dat"));
    }
    private static void fail(RunnableWithException action) throws Exception {
        boolean failed=false;
        try {action.run();} catch(Exception e){failed=true;}
        if (!failed)throw new AssertionError("Expected fail-closed repair");
    }
    interface RunnableWithException {void run() throws Exception;}
    public static void main(String[] args) throws Exception {
        Path base=Path.of(args[0]);
        Path world=base.resolve("single-world");level(world,player(A,42));
        Path untouched=base.resolve("other-world");level(untouched,player(B,10));
        byte[] before=Files.readAllBytes(untouched.resolve("level.dat"));
        AetherloomRepair.repair(world,B,false);
        assert !NbtIo.readCompressed(world.resolve("level.dat")).getCompound("Data").contains("Player");
        assert NbtIo.readCompressed(world.resolve("playerdata/"+A+".dat")).getInt("XpLevel",0)==42;
        byte[] repaired=Files.readAllBytes(world.resolve("level.dat"));
        AetherloomRepair.repair(world,B,false);
        assert java.util.Arrays.equals(repaired,Files.readAllBytes(world.resolve("level.dat")));
        assert java.util.Arrays.equals(before,Files.readAllBytes(untouched.resolve("level.dat")));
        // Nonempty old external data must not silently win over embedded saved progress.
        level(world,player(A,77));
        fail(()->AetherloomRepair.repair(world,B,false));
        assert NbtIo.readCompressed(world.resolve("level.dat")).getCompound("Data").contains("Player");
        assert NbtIo.readCompressed(world.resolve("playerdata/"+A+".dat")).getInt("XpLevel",0)==42;
        AetherloomRepair.repair(world,A,true);
        assert NbtIo.readCompressed(world.resolve("playerdata/"+A+".dat")).getInt("XpLevel",0)==77;
        fail(()->AetherloomRepair.repair(world,new UUID(0,0),false));
        level(world,Tag.newCompound());fail(()->AetherloomRepair.repair(world,B,false));
        Files.write(world.resolve("level.dat"),new byte[]{1,2,3});fail(()->AetherloomRepair.repair(world,B,false));
        Path badBackup=base.resolve("backup-failure");level(badBackup,player(A,10));
        byte[] original=Files.readAllBytes(badBackup.resolve("level.dat"));
        Files.writeString(badBackup.resolve("aetherloom-playerdata-backups"),"blocked");
        fail(()->AetherloomRepair.repair(badBackup,B,false));
        assert java.util.Arrays.equals(original,Files.readAllBytes(badBackup.resolve("level.dat")));
        System.out.println("Repair checks passed: single-world, stale external conflict, verified save, unknown/zero UUID, corrupt NBT, idempotence, backup failure");
    }
}
