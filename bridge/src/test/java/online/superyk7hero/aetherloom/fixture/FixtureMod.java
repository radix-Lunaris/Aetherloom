package online.superyk7hero.aetherloom.fixture;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.*;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.fml.common.Mod;

/** Separate test-only jar. Never included in the client distribution. */
@Mod("aetherloom_fixture")
public class FixtureMod {
    private boolean started=false;
    private boolean seenWorld=false;
    public FixtureMod() { MinecraftForge.EVENT_BUS.addListener(this::tick); }
    private void tick(TickEvent.ClientTickEvent event) {
        String name=System.getenv("AETHERLOOM_CREATE_FIXTURE");
        if (name==null || event.phase!=TickEvent.Phase.END) return;
        Minecraft mc=Minecraft.getInstance();
        if (mc.level!=null) seenWorld=true;
        if (seenWorld && mc.screen instanceof TitleScreen) { mc.stop();return; }
        if (started) return;
        if (!(mc.screen instanceof TitleScreen)) return;
        started=true;
        mc.createWorldOpenFlows().createFreshLevel(name,
            new LevelSettings("Aetherloom isolated test",GameType.CREATIVE,false,Difficulty.PEACEFUL,true,new GameRules(),WorldDataConfiguration.DEFAULT),
            new WorldOptions(123456789L,false,false),
            registry -> registry.registryOrThrow(Registries.WORLD_PRESET).getOrThrow(WorldPresets.FLAT).createWorldDimensions());
    }
}
