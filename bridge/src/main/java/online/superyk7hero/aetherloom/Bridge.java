package online.superyk7hero.aetherloom;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.server.IntegratedServer;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.server.ServerStartedEvent;
import net.minecraftforge.event.server.ServerStoppedEvent;
import net.minecraftforge.fml.common.Mod;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

/** Inert without a per-launch configuration supplied by Aetherloom. */
@Mod("aetherloom_bridge")
public class Bridge {
    private final Gson gson = new Gson();
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    private JsonObject config;
    private volatile boolean loaded = false;
    private volatile IntegratedServer pendingServer;
    private long nextPoll = 0;
    private volatile boolean stop = false;

    public Bridge() {
        String file = System.getenv("AETHERLOOM_BRIDGE_FILE");
        if (file == null || file.isBlank()) return;
        try {
            config = gson.fromJson(Files.readString(Path.of(file)), JsonObject.class);
            URI uri = URI.create(config.get("endpoint").getAsString());
            if (!"http".equals(uri.getScheme()) || !"127.0.0.1".equals(uri.getHost()))
                throw new IllegalArgumentException("Bridge requires loopback endpoint");
            MinecraftForge.EVENT_BUS.addListener(this::started);
            MinecraftForge.EVENT_BUS.addListener(this::stopped);
            MinecraftForge.EVENT_BUS.addListener(this::tick);
        } catch (Exception e) { throw new IllegalStateException("Invalid Aetherloom Bridge configuration", e); }
    }

    private HttpRequest.Builder request() {
        return HttpRequest.newBuilder(URI.create(config.get("endpoint").getAsString()))
            .header("Authorization", "Bearer " + config.get("token").getAsString())
            .header("Content-Type", "application/json").timeout(Duration.ofSeconds(3));
    }

    private void event(String type, int port, IntegratedServer server) throws Exception {
        JsonObject data = new JsonObject();
        data.addProperty("event", type);
        data.addProperty("port", port);
        data.addProperty("world", server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize().toString());
        data.addProperty("uuid", server.getSingleplayerProfile().getId().toString());
        HttpResponse<String> response = http.send(request().POST(HttpRequest.BodyPublishers.ofString(gson.toJson(data))).build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) throw new IllegalStateException("Bridge event rejected");
    }

    private boolean selected(IntegratedServer server) {
        try { return Files.isSameFile(server.getWorldPath(LevelResource.ROOT),
            Path.of(config.get("world").getAsString())); }
        catch (Exception e) { return false; }
    }

    private void started(ServerStartedEvent event) {
        if (!(event.getServer() instanceof IntegratedServer server) || !selected(server)) return;
        pendingServer = server;
    }

    private void open(IntegratedServer server) {
        try {
            int port = 0;
            if (!config.has("inspect") || !config.get("inspect").getAsBoolean()) {
                try (ServerSocket socket = new ServerSocket(0)) { port = socket.getLocalPort(); }
                server.setUsesAuthentication(false);
                if (!server.publishServer(server.getDefaultGameType(), false, port))
                    throw new IllegalStateException("Unable to publish selected world");
            }
            event("ready", port, server);
            loaded = true;
        } catch (Exception e) {
            System.err.println("Aetherloom could not prepare LAN: " + e);
            try { event("error", 0, server); } catch (Exception ignored) {}
            Minecraft.getInstance().clearLevel(new TitleScreen());
        }
    }

    private void stopped(ServerStoppedEvent event) {
        pendingServer = null;
        if (!loaded || !(event.getServer() instanceof IntegratedServer server) || !selected(server)) return;
        loaded = false;
        try { event("saved", 0, server); }
        catch (Exception e) { System.err.println("Aetherloom: saved event was not acknowledged; retain local recovery data."); }
    }

    private void tick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        Minecraft mc = Minecraft.getInstance();
        IntegratedServer pending = pendingServer;
        // publishServer reads Minecraft.player, which is still null during
        // ServerStartedEvent. Wait for the local client to finish joining.
        if (pending != null && mc.player != null && mc.level != null && mc.getSingleplayerServer() == pending) {
            pendingServer = null;
            open(pending);
        }
        if (!loaded) return;
        if (stop) {
            stop = false;
            System.out.println("Aetherloom: stopping managed world");
            Minecraft.getInstance().clearLevel(new TitleScreen());
            return;
        }
        long now = System.currentTimeMillis();
        if (now < nextPoll) return;
        nextPoll = now + 1000;
        http.sendAsync(request().GET().build(), HttpResponse.BodyHandlers.ofString())
            .thenAccept(response -> {
                if (response.statusCode() == 200) {
                    stop = gson.fromJson(response.body(), JsonObject.class).get("stop").getAsBoolean();
                    if (stop) System.out.println("Aetherloom: received stop command");
                }
            }).exceptionally(e -> { System.err.println("Aetherloom: loopback poll failed: " + e.getClass().getSimpleName()); return null; });
    }
}
