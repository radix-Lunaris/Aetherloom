package online.superyk7hero.aetherloom.agent;

import java.lang.instrument.Instrumentation;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;
import java.util.function.BiConsumer;
import java.util.function.UnaryOperator;
import java.util.jar.JarFile;
import java.util.concurrent.atomic.AtomicBoolean;

/** Java 8 compatible, no game or third-party linkage in the public agent. */
public final class Agent {
    static final Properties config=new Properties(), names=new Properties();
    static final ExecutorService io=Executors.newSingleThreadExecutor(r->{Thread t=new Thread(r,"Aetherloom agent control");t.setDaemon(true);return t;});
    static volatile ClassLoader gameLoader;
    static volatile boolean stop,finished,loaded,joined,stopping;
    static volatile boolean exitRequested;
    static volatile Object pending,pinger,target;
    static volatile boolean connecting;
    static volatile boolean modernApi;
    static volatile boolean neoForge;
    static volatile boolean directHooks;
    static boolean earlyProfile;
    static boolean legacy;
    static boolean legacyTickHook;
    static volatile boolean legacyTickReady;
    static volatile boolean legacyOwnerSeen;
    static long nextLegacyTick;
    static volatile Object selectedLegacyServer;
    static boolean configurationApi,postTickApi;
    static Object hostProfile,haltedServer;
    static Object handledBackup;
    static boolean worldOpenRequested;
    static Class<?> hooks;
    static final AtomicBoolean tickPending=new AtomicBoolean();
    static long joinDeadline;
    static final Set<String> reports=Collections.synchronizedSet(new HashSet<String>());
    static final AtomicBoolean statsPending=new AtomicBoolean();
    static long nextStats;
    static FutureTask<Void> hostSettings;
    static long hostSettingsDeadline;

    static String fabricBaseline(String version) throws IOException {
        int nearest=Integer.MAX_VALUE;
        String selected="1.21.1";
        java.util.regex.Matcher release=java.util.regex.Pattern.compile("^(1\\.\\d+)(?:\\.(\\d+))?(?:-|$)").matcher(version);
        if(!release.find())return selected;
        String family=release.group(1);
        int patch=release.group(2)==null?0:Integer.parseInt(release.group(2));
        Properties index=new Properties();
        try(InputStream source=Agent.class.getResourceAsStream("/fabric-mapping-index.properties")) {index.load(source);}
        for(String candidate:index.getProperty(family,"").split(",")) {
            if(candidate.isEmpty())continue;
            int distance=Math.abs(patch-Integer.parseInt(candidate));
            if(distance<nearest){
                nearest=distance;
                selected=candidate.equals("0")?family:family+"."+candidate;
            }
        }
        return selected;
    }

    public static void premain(String options,Instrumentation instrumentation) throws Exception {
        if ("selftest".equals(options)) {
            System.out.println("AETHERLOOM_AGENT_OK java="+System.getProperty("java.specification.version"));return;
        }
        if (options==null || options.isEmpty()) throw new IllegalArgumentException("Missing managed agent configuration");
        if (!"managed".equals(options))throw new IllegalArgumentException("Unknown agent mode");
        String configPath=System.getenv("AETHERLOOM_AGENT_CONFIG");
        if(configPath==null)throw new IllegalArgumentException("Missing managed environment");
        try(InputStream source=Files.newInputStream(Paths.get(configPath))) {config.load(source);}
        URI endpoint=URI.create(config.getProperty("endpoint"));
        if (!"http".equals(endpoint.getScheme()) || !"127.0.0.1".equals(endpoint.getHost()) || endpoint.getUserInfo()!=null)
            throw new IllegalArgumentException("Control must use loopback");
        String adapter=config.getProperty("adapter","");
        String version=adapter.substring(0,Math.max(0,adapter.lastIndexOf('-')));
        boolean named=version.matches("(?:2[6-9]|[3-9][0-9])\\..*");
        if(!named) {
            try(InputStream mappings=Agent.class.getResourceAsStream("/forge-1.20.1.properties")) {names.load(mappings);}
            try(InputStream exact=Agent.class.getResourceAsStream("/forge-"+version+".properties")) {
                if(exact!=null)names.load(exact);
            }
        }
        boolean knot=adapter.endsWith("-fabric") || adapter.endsWith("-quilt");
        boolean vanilla=adapter.endsWith("-vanilla");
        if(knot || vanilla) {
            Properties aliases=new Properties();
            String prefix=vanilla?"/vanilla-":"/fabric-";
            InputStream resource=named?null:Agent.class.getResourceAsStream((vanilla?"/legacy-vanilla-":"/legacy-fabric-")+version+".properties");
            legacy=resource!=null;
            if(!named && resource==null)resource=Agent.class.getResourceAsStream(prefix+version+".properties");
            if(knot && !named && resource==null) {
                String baseline=fabricBaseline(version);
                resource=Agent.class.getResourceAsStream("/fabric-"+baseline+".properties");
                System.out.println("AETHERLOOM_AGENT_MAPPING_BASELINE requested="+version+" baseline="+baseline+" runtime capabilities required");
            }
            if(vanilla && !named && resource==null)throw new IllegalArgumentException("Missing exact vanilla mapping for "+version);
            if(resource!=null)try(InputStream source=resource) {aliases.load(source);}
            instrumentation.appendToBootstrapClassLoaderSearch(new JarFile(new File(Agent.class.getProtectionDomain().getCodeSource().getLocation().toURI())));
            hooks=Class.forName("online.superyk7hero.aetherloom.agent.BootstrapHooks",true,null);
            hooks.getField("lifecycle").set(null,(BiConsumer<Object,String>)Agent::serverLifecycle);
            hooks.getField("identity").set(null,(UnaryOperator<Object>)Agent::profileIdentity);
            earlyProfile=named;
            legacyTickHook=legacy && aliases.containsKey(aliases.getProperty("class.net.minecraft.client.Minecraft")+".legacyClientTick");
            if(legacyTickHook)hooks.getField("clientTick").set(null,(Runnable)Agent::legacyTick);
            instrumentation.addTransformer(new LoaderTransformer(aliases,earlyProfile,legacy,config.containsKey("legacy_name")));
            names.clear();names.putAll(aliases);directHooks=true;
        }
        Thread worker=new Thread(()->{
            try {
                long deadline=System.nanoTime()+TimeUnit.MINUTES.toNanos(10);
                while(gameLoader==null && System.nanoTime()<deadline) {
                    for(Class<?> type:instrumentation.getAllLoadedClasses())
                        if(type.getName().equals("net.minecraft.client.Minecraft") || directHooks && type.getName().equals(names.getProperty("class.net.minecraft.client.Minecraft"))) {gameLoader=type.getClassLoader();break;}
                    if(gameLoader==null) Thread.sleep(100);
                }
                if(gameLoader==null) throw new IllegalStateException("Game loader discovery timed out");
                Thread.currentThread().setContextClassLoader(gameLoader);
                if(knot)exposeBootstrapBridge();
                try {Class.forName("net.neoforged.neoforge.common.NeoForge",false,gameLoader);neoForge=true;}
                catch(ClassNotFoundException forge) {neoForge=false;}
                // QuickPlay can construct Minecraft while Forge is still setting
                // up its event bus. Register only after mod loading completes.
                while((minecraft()==null || !directHooks && Boolean.TRUE.equals(call(type("net.minecraftforge.client.loading.ClientModLoader"),"isLoading"))) && System.nanoTime()<deadline)Thread.sleep(100);
                try {type("net.minecraft.client.multiplayer.ServerData$Type");modernApi=true;}
                catch(ClassNotFoundException legacyApi) {modernApi=false;}
                if(!directHooks) {
                    try {type("net.minecraftforge.event.network.GatherLoginConfigurationTasksEvent");configurationApi=!neoForge;}catch(ClassNotFoundException missing){configurationApi=false;}
                    try {type("net.minecraftforge.event.TickEvent$ClientTickEvent$Post");postTickApi=true;}catch(ClassNotFoundException missing){postTickApi=false;}
                }
                if(legacyTickHook && !hooks.getField("clientTickInstalled").getBoolean(null))
                    throw new IllegalStateException("Legacy client tick hook was not installed");
                if(directHooks)emit("capabilities",0);else install();
                legacyTickReady=legacyTickHook;
                while(!exitRequested && (directHooks || !finished)) {
                    if(!finished)stop=request("",null).contains("\"stop\": true");
                    if(directHooks && !legacyTickHook && tickPending.compareAndSet(false,true)) {
                        Runnable update=()->{try{tick();}catch(Throwable error){fail(error);}finally{tickPending.set(false);}};
                        Object client=minecraft();
                        if(legacy)call(client,"submitLegacyTick",(Callable<Void>)()->{update.run();return null;});
                        else ((Executor)client).execute(update);
                    }
                    Thread.sleep(directHooks?100:500);
                }
            } catch(Throwable error) {fail(error);}
        },"Aetherloom agent bootstrap");worker.setDaemon(true);worker.start();
    }
    static void legacyTick() {
        if(!legacyTickReady || exitRequested || System.nanoTime()<nextLegacyTick)return;
        nextLegacyTick=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(100);
        try {tick();}
        catch(Throwable error){legacyTickReady=false;fail(error);}
    }

    static Class<?> type(String name) throws Exception {
        if(neoForge) {
            if(name.equals("net.minecraftforge.common.MinecraftForge"))name="net.neoforged.neoforge.common.NeoForge";
            else if(name.equals("net.minecraftforge.event.TickEvent$ClientTickEvent$Post"))name="net.neoforged.neoforge.client.event.ClientTickEvent$Post";
            else if(name.startsWith("net.minecraftforge.eventbus."))name=name.replace("net.minecraftforge.eventbus.","net.neoforged.bus.");
            else if(name.startsWith("net.minecraftforge."))name=name.replace("net.minecraftforge.","net.neoforged.neoforge.");
        }
        if(directHooks)name=names.getProperty("class."+name,name);
        return Class.forName(name,true,gameLoader);
    }
    static String[] aliases(Class<?> owner,String name) {
        if(neoForge)return new String[]{name};
        Set<String> result=new LinkedHashSet<String>();
        result.addAll(Arrays.asList(names.getProperty(owner.getName()+"."+name,name).split(",")));
        for(Class<?> iface:owner.getInterfaces())result.addAll(Arrays.asList(aliases(iface,name)));
        result.add(name);return result.toArray(new String[0]);
    }
    static Object field(Object object,String name) throws Exception {
        Class<?> owner=object instanceof Class?(Class<?>)object:object.getClass();
        for(Class<?> c=owner;c!=null;c=c.getSuperclass()) for(String alias:aliases(c,name)) {
            try {Field f=c.getDeclaredField(alias);f.setAccessible(true);return f.get(object instanceof Class?null:object);}
            catch(NoSuchFieldException ignored) {}
        }
        throw new NoSuchFieldException(owner.getName()+"."+name);
    }
    static Object call(Object object,String name,Object...args) throws Exception {
        Class<?> owner=object instanceof Class?(Class<?>)object:object.getClass();
        Set<Method> matches=new HashSet<Method>();
        for(Class<?> c=owner;c!=null;c=c.getSuperclass()) for(String alias:aliases(c,name))
            for(Method m:c.getDeclaredMethods()) if(!m.isBridge() && Modifier.isStatic(m.getModifiers())==(object instanceof Class) && m.getName().equals(alias) && compatible(m.getParameterTypes(),args)) matches.add(m);
        if(name.equals("getConnection") && type("net.minecraft.client.Minecraft").isInstance(object)) {
            Class<?> expected=type("net.minecraft.client.multiplayer.ClientPacketListener");
            matches.removeIf(method->!expected.isAssignableFrom(method.getReturnType()));
        }
        // Overrides select the closest declaration, never an arbitrary overload.
        Method selected=null;
        for(Class<?> c=owner;c!=null && selected==null;c=c.getSuperclass()) {
            for(Method m:matches) if(m.getDeclaringClass()==c) {
                if(selected!=null) throw new IllegalStateException("Ambiguous mapped method: "+owner.getName()+"."+name+" candidates="+matches+" neo="+neoForge);
                selected=m;
            }
        }
        if(selected==null) throw new NoSuchMethodException(owner.getName()+"."+name);
        selected.setAccessible(true);return selected.invoke(object instanceof Class?null:object,args);
    }
    static boolean compatible(Class<?>[] types,Object[] args) {
        if(types.length!=args.length)return false;
        for(int i=0;i<types.length;i++) {
            Class<?> c=types[i];if(c==boolean.class)c=Boolean.class;if(c==int.class)c=Integer.class;
            if(args[i]!=null && !c.isInstance(args[i]))return false;
            if(args[i]==null && types[i].isPrimitive())return false;
        }
        return true;
    }
    static Object make(String name,Object...args) throws Exception {
        Constructor<?> selected=null;
        for(Constructor<?> c:type(name).getDeclaredConstructors()) if(compatible(c.getParameterTypes(),args)) {
            if(selected!=null)throw new IllegalStateException("Ambiguous constructor");selected=c;
        }
        if(selected==null)throw new NoSuchMethodException(name);selected.setAccessible(true);return selected.newInstance(args);
    }
    static void listen(Object bus,String event,Consumer<Object> handler) throws Exception {
        Object priority=Enum.valueOf((Class)type("net.minecraftforge.eventbus.api.EventPriority"),"NORMAL");
        // Invoke the public interface, avoiding inaccessible implementation classes.
        type("net.minecraftforge.eventbus.api.IEventBus").getMethod("addListener",priority.getClass(),boolean.class,Class.class,Consumer.class)
            .invoke(bus,priority,false,type(event),(Consumer<Object>)value->{try{handler.accept(value);}catch(Throwable error){fail(error);}});
    }
    interface Action {void run(Object event) throws Exception;}
    static Consumer<Object> checked(Action action) {return event->{try{action.run(event);}catch(Throwable error){fail(error);}};}
    static void install() throws Exception {
        Object bus=field(type("net.minecraftforge.common.MinecraftForge"),"EVENT_BUS");
        listen(bus,"net.minecraftforge.event.server.ServerStartedEvent",checked(event->{
            if(!config.containsKey("join")) {Object server=call(event,"getServer");boolean selected=selected(server);System.out.println("AETHERLOOM_AGENT_SERVER_STARTED selected="+selected);if(selected)pending=server;}
        }));
        listen(bus,"net.minecraftforge.event.server.ServerStoppedEvent",checked(event->{
            Object server=call(event,"getServer");if(loaded && selected(server)) {loaded=false;emit("saved",0);}
        }));
        if(configurationApi)listen(bus,"net.minecraftforge.event.network.GatherLoginConfigurationTasksEvent",checked(Agent::configurationIdentity));
        else listen(bus,"net.minecraftforge.event.entity.player.PlayerNegotiationEvent",checked(event->{
            if(config.containsKey("join") || Boolean.parseBoolean(config.getProperty("inspect")))return;
            // The integrated Host joins via an in-memory connection, not a relay peer.
            if(Boolean.TRUE.equals(call(call(event,"getConnection"),"isMemoryConnection")))return;
            CompletableFuture<Void> result=CompletableFuture.runAsync(()->{
                try {
                    verifyIdentity(call(event,"getProfile"));
                }catch(Throwable error){
                    fail(error);
                    try {call(call(event,"getConnection"),"disconnect",call(type("net.minecraft.network.chat.Component"),"literal","Aetherloom: identity rejected"));}
                    catch(Throwable disconnectError){System.err.println("AETHERLOOM_AGENT_IDENTITY_DISCONNECT_FAILED");}
                    throw new CompletionException(error);
                }
            },io);
            // Future completion is part of Forge's negotiation barrier.
            call(event,"enqueueWork",result);
        }));
        listen(bus,postTickApi?"net.minecraftforge.event.TickEvent$ClientTickEvent$Post":"net.minecraftforge.event.TickEvent$ClientTickEvent",checked(event->{if(postTickApi || "END".equals(String.valueOf(field(event,"phase"))))tick();}));
        emit("capabilities",0);
        System.out.println("AETHERLOOM_AGENT_ADAPTER_INSTALLED "+config.getProperty("adapter"));
    }
    static boolean modern() {return modernApi;}
    static void exposeBootstrapBridge() throws Exception {
        Object delegate=field(gameLoader,"delegate");
        try {
            Object current=field(delegate,"validParentCodeSources");
            if(current!=null) {
                Set<Path> paths=new HashSet<Path>((Collection<Path>)current);
                paths.add(Paths.get(Agent.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath());
                call(delegate,"setValidParentClassPath",paths);
            }
        }catch(NoSuchFieldException quiltIsolation) { /* Quilt uses a different parent routing policy. */ }
    }
    static Object profileIdentity(Object profile) {
        if(config.containsKey("join") || Boolean.parseBoolean(config.getProperty("inspect")))return profile;
        try {
            String legacyName=config.getProperty("legacy_name");
            if(legacyName!=null) {
                String player=profile instanceof String?(String)profile:profileName(profile);
                if(!player.matches("[a-z0-9_]{1,16}"))throw new IllegalStateException("Invalid legacy player name");
                if(!loaded && legacyName.equals(player)) {
                    legacyOwnerSeen=true;
                    return profile;
                }
                UUID expected=UUID.nameUUIDFromBytes(("OfflinePlayer:"+player).getBytes(StandardCharsets.UTF_8));
                if(!expected.equals(registeredUuidByName(player)))throw new IllegalStateException("Unregistered legacy player");
                return profile;
            }
            if(profile==hostProfile)return profile;
            if(!loaded && UUID.fromString(config.getProperty("identity")).equals(profileId(profile))) {hostProfile=profile;return profile;}
            return resolveProfile(profile,registeredUuid(profile));
        }catch(Throwable error){fail(error);throw new IllegalStateException("Managed peer identity rejected",error);}
    }
    static void serverLifecycle(Object server,String phase) {
        try {
            if(config.containsKey("join") || !selected(server))return;
            System.out.println("AETHERLOOM_AGENT_LIFECYCLE "+phase+" loaded="+loaded+" halt="+(server==haltedServer));
            if(phase.equals("crash")){fail(new IllegalStateException("Integrated server crashed; save is unconfirmed"));return;}
            if(phase.equals("halt")){haltedServer=server;return;}
            if(phase.equals("saved") && server==haltedServer && loaded && reports.isEmpty()) {loaded=false;emit("saved",0);}
        }catch(Throwable error){fail(error);}
    }
    static UUID profileId(Object profile) throws Exception {
        try {return (UUID)call(profile,"getId");}
        catch(NoSuchMethodException record){return (UUID)call(profile,"id");}
    }
    static String profileName(Object profile) throws Exception {
        try {return (String)call(profile,"getName");}
        catch(NoSuchMethodException record){return (String)call(profile,"name");}
    }
    static UUID registeredUuid(Object profile) throws Exception {
        boolean external="littleskin".equals(config.getProperty("auth_mode"));
        String lookup=external?"by-uuid/"+profileId(profile):URLEncoder.encode(profileName(profile),"UTF-8");
        UUID id=registeredUuidAt(lookup);
        if(external && !id.equals(profileId(profile)))throw new IllegalStateException("Verified LittleSkin UUID mismatch");
        return id;
    }
    static UUID registeredUuidByName(String name) throws Exception {
        return registeredUuidAt(URLEncoder.encode(name,"UTF-8"));
    }
    static UUID registeredUuidAt(String lookup) throws Exception {
        String response=request("/identity/"+lookup,null);
        java.util.regex.Matcher match=java.util.regex.Pattern.compile("\\\"uuid\\\"\\s*:\\s*\\\"([0-9a-fA-F-]{36})\\\"").matcher(response);
        if(!match.find())throw new IllegalStateException("Unregistered peer identity");
        return UUID.fromString(match.group(1));
    }
    static Object resolveProfile(Object profile,UUID id) throws Exception {
        if(id.equals(profileId(profile)))return profile;
        if(profile.getClass().getSuperclass().getName().equals("java.lang.Record")) {
            Object properties=call(profile,"properties");
            return profile.getClass().getConstructor(UUID.class,String.class,properties.getClass()).newInstance(id,profileName(profile),properties);
        }
        Field identity=profile.getClass().getDeclaredField("id");identity.setAccessible(true);identity.set(profile,id);
        if(!id.equals(profileId(profile)))throw new IllegalStateException("UUID application failed");
        return profile;
    }
    static void verifyIdentity(Object profile) throws Exception {
        UUID id=registeredUuid(profile);
        if(!id.equals(profileId(profile)) && profile.getClass().getSuperclass().getName().equals("java.lang.Record"))
            throw new IllegalStateException("Loader login cannot replace this immutable profile");
        resolveProfile(profile,id);
    }
    static void configurationIdentity(Object event) throws Exception {
        if(config.containsKey("join") || Boolean.parseBoolean(config.getProperty("inspect")))return;
        Object connection=call(event,"getConnection");
        if(Boolean.TRUE.equals(call(connection,"isMemoryConnection")))return;
        Object listener=call(connection,"getPacketListener");
        Object identity=call(listener,"getOwner");
        Object taskType=make("net.minecraft.server.network.ConfigurationTask$Type","aetherloom:identity");
        Object task=java.lang.reflect.Proxy.newProxyInstance(gameLoader,new Class<?>[]{type("net.minecraft.server.network.ConfigurationTask")},(proxy,method,args)->{
            if(method.getName().equals("type"))return taskType;
            if(method.getName().equals("toString"))return "Aetherloom identity barrier";
            if(method.getName().equals("hashCode"))return System.identityHashCode(proxy);
            if(method.getName().equals("equals"))return proxy==args[0];
            if(!method.getName().equals("start") || args==null || args.length!=1)throw new UnsupportedOperationException("Unknown configuration task method");
            Object context=args[0];
            io.submit(()->{
                try {
                    verifyIdentity(identity);
                    Object server=call(minecraft(),"getSingleplayerServer");
                    call(server,"execute",(Runnable)()->{
                        try {if(Boolean.TRUE.equals(call(connection,"isConnected")))call(context,"finish",taskType);}
                        catch(Throwable error){fail(error);}
                    });
                }catch(Throwable error){
                    fail(error);
                    try {call(connection,"disconnect",call(type("net.minecraft.network.chat.Component"),"literal","Aetherloom: identity rejected"));}
                    catch(Throwable ignored) {}
                }
            });return null;
        });
        call(event,"addTask",task);
    }
    static Object minecraft() throws Exception {return call(type("net.minecraft.client.Minecraft"),"getInstance");}
    static boolean selected(Object server) throws Exception {
        if(legacy) {
            if(server==selectedLegacyServer)return true;
            File directory;
            try {directory=(File)field(minecraft(),"legacyRunDirectory");}
            catch(NoSuchFieldException older){directory=(File)call(server,"legacyServerDirectory");}
            String folder=(String)call(server,"legacyLevelName");
            if(folder==null || folder.isEmpty())return false;
            Path saves=directory.toPath().resolve("saves").toRealPath();
            Path selected=saves.resolve(folder).normalize();
            if(!saves.equals(selected.getParent()) || !Files.isSameFile(selected,Paths.get(config.getProperty("world"))))return false;
            selectedLegacyServer=server;
            return true;
        }
        Object resource=field(type("net.minecraft.world.level.storage.LevelResource"),"ROOT");
        return Files.isSameFile((Path)call(server,"getWorldPath",resource),Paths.get(config.getProperty("world")));
    }
    static void leave(Object mc) throws Exception {
        if(legacy) {
            Object server=call(mc,"getSingleplayerServer");
            if(server!=null)try {call(server,"halt");}catch(NoSuchMethodException newer){call(server,"halt",false);}
            try {call(mc,"legacyDetach",new Object[]{null});}
            catch(NoSuchMethodException newer){call(mc,"legacyDetach");}
            return;
        }
        Object level=field(mc,"level");
        if(level!=null)try{call(level,"disconnect");}catch(NoSuchMethodException newer){/* Minecraft owns disconnect. */}
        Object server=call(mc,"getSingleplayerServer");if(server!=null)call(server,"halt",false);
        Object title=make("net.minecraft.client.gui.screens.TitleScreen");
        try {call(mc,modern()?"disconnect":"clearLevel",title);}
        catch(NoSuchMethodException alternate){
            try {call(mc,modern()?"clearLevel":"disconnect",title);}
            catch(NoSuchMethodException newer){call(mc,"disconnect",title,false);}
        }
    }
    static Object screen(Object mc) throws Exception {
        try {return field(mc,"screen");}
        catch(NoSuchFieldException newer){return call(field(mc,"gui"),"screen");}
    }
    static void tick() throws Exception {
        Object mc=minecraft(),player=field(mc,"player"),level=field(mc,"level"),server=call(mc,"getSingleplayerServer");
        if(!stop && !worldOpenRequested && server==null && Boolean.parseBoolean(config.getProperty("open_world"))) {
            Object screen=screen(mc);
            if(type("net.minecraft.client.gui.screens.TitleScreen").isInstance(screen)) {
                worldOpenRequested=true;
                String folder=Paths.get(config.getProperty("world")).getFileName().toString();
                if(legacy) {
                    call(mc,"legacyOpenWorld",folder,folder,null);
                    return;
                }
                Object flows;
                try {flows=call(mc,"createWorldOpenFlows");}
                catch(NoSuchMethodException older){call(mc,"loadLevel",folder);return;}
                try {call(flows,"loadLevel",screen,folder);}
                catch(NoSuchMethodException newer){call(flows,"openWorld",folder,(Runnable)()->{});}
                return;
            }
        }
        if(!legacy && !config.containsKey("join") && !loaded && !stopping && player==null && server==null)confirmSelectedBackup(mc);
        // QuickPlay may have started the integrated server before registration.
        // Recover only the explicitly selected world, never an arbitrary world.
        if(!config.containsKey("join") && !loaded && pending==null && !stopping && server!=null && player!=null && level!=null && selected(server))pending=server;
        if(loaded && System.nanoTime()>=nextStats) {
            nextStats=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            Object connection=server==null && !config.containsKey("legacy_name")?call(mc,"getConnection"):null;
            try {
                int count=server!=null?((Number)call(server,"getPlayerCount")).intValue():connection!=null?((Collection<?>)call(connection,"getOnlinePlayers")).size():0;
                emitStats(count);
            } catch(NoSuchMethodException missingStatistic) {
                if(!legacy)throw missingStatistic;
            }
        }
        if(config.containsKey("join")) {
            Object screen=screen(mc);
            if(connecting && !joined && screen!=null && type("net.minecraft.client.gui.screens.DisconnectedScreen").isInstance(screen)) {
                String reason="server rejected the connection";
                try {
                    Object message=field(screen,"reason");
                    for(Method method:message.getClass().getMethods())if(method.getName().equals("getString") && method.getParameterTypes().length==0 && method.getReturnType()==String.class) {reason=String.valueOf(method.invoke(message));break;}
                }catch(Exception ignored) {}
                throw new IllegalStateException("Game connection failed: "+reason);
            }
            if(joined && player==null && level==null)finished=true;
            else if(!joined && player!=null && level!=null && server==null) {checkIdentity(player);emit("joined",0);joined=true;loaded=true;}
            else if(!connecting && !joined)join(mc);
        }
        if(finished && level==null && server==null) {exitRequested=true;call(mc,"stop");return;}
        Object candidate=pending;
        if(candidate!=null && server==candidate && player!=null && level!=null) {
            if(directHooks && (
                !hooks.getField("serverInstalled").getBoolean(null)
                || !hooks.getField("profileInstalled").getBoolean(null)
                || (earlyProfile && !hooks.getField("profileLookupInstalled").getBoolean(null))
            ))throw new IllegalStateException("Required lifecycle/identity hooks were not installed");
            boolean inspection=Boolean.parseBoolean(config.getProperty("inspect"));
            if(!inspection && !hostSettingsReady(mc,server)) {
                if(stop && !stopping){stopping=true;leave(mc);}
                return;
            }
            pending=null;int port=0;
            if(!inspection) {
                boolean cheats=Boolean.parseBoolean(config.getProperty("host_cheats"));
                boolean official=Boolean.parseBoolean(config.getProperty("host_official_auth"));
                call(server,"setUsesAuthentication",official || "littleskin".equals(config.getProperty("auth_mode")));
                if(config.containsKey("host_pvp")) {
                    applyHostPvp(server,Boolean.parseBoolean(config.getProperty("host_pvp")));
                }
                Object mode=call(server,"getDefaultGameType");
                if(config.containsKey("host_mode"))mode=hostGameMode(mode,config.getProperty("host_mode"));
                if(legacy) {
                    port=publishLegacy(server,mode,cheats);
                } else {
                    try(ServerSocket socket=new ServerSocket(0)){port=socket.getLocalPort();}
                    Object scope=mode;
                    try {
                        scope=field(type("net.minecraft.server.MinecraftServer$MultiplayerScope"),"LAN");
                        if(config.containsKey("host_mode"))call(server,"setDefaultGameType",mode);
                    }
                    catch(ClassNotFoundException older){}
                    if(!Boolean.TRUE.equals(call(server,"publishServer",scope,cheats,port)))throw new IllegalStateException("LAN publication failed");
                }
                if(config.containsKey("host_cheats"))System.out.println(
                    "AETHERLOOM_AGENT_HOST_PRESETS pvp="+config.getProperty("host_pvp","world")
                    +" mode="+config.getProperty("host_mode","world")+" cheats="+cheats+" officialAuth="+official);
            }
            checkIdentity(player);loaded=true;emit("ready",port);
        }
        if(stop && !stopping) {stopping=true;if(level!=null || server!=null)leave(mc);else call(mc,"stop");}
    }
    static HostCommands hostCommand(Object server) throws Exception {
        Object root=call(server,"getCommands");
        return new HostCommands(root,call(root,"getDispatcher"),call(server,"createCommandSourceStack"));
    }

    static final class HostCommands {
        final Object commands,dispatcher,source;
        HostCommands(Object commands,Object dispatcher,Object source) {
            this.commands=commands;this.dispatcher=dispatcher;this.source=source;
        }
        Object validate(String command) throws Exception {
            Object parse=call(dispatcher,"parse",command,source);
            if(Boolean.TRUE.equals(call(call(parse,"getReader"),"canRead")) || call(call(parse,"getContext"),"getCommand")==null)
                throw new IllegalArgumentException("Unsupported Minecraft setting for this version: "+command);
            return parse;
        }
        void run(String command,Object parse) throws Exception {
            try {call(commands,"performPrefixedCommand",source,command);}
            catch(NoSuchMethodException old) {call(dispatcher,"execute",parse);}
        }
    }

    static boolean hostSettingsReady(Object mc,Object server) throws Exception {
        if(hostSettings!=null) {
            if(hostSettings.isDone()) {
                try {hostSettings.get();}
                catch(ExecutionException failure) {
                    throw new IllegalStateException("Host settings failed: "+failure.getCause().getMessage(),failure.getCause());
                }
                return true;
            }
            if(System.nanoTime()>hostSettingsDeadline) {
                hostSettings.cancel(false);
                throw new IllegalStateException("Integrated server did not finish applying Host settings");
            }
            return false;
        }
        String difficulty=config.getProperty("host_difficulty");
        String time=config.getProperty("host_time");
        String weather=config.getProperty("host_weather");
        String border=config.getProperty("host_world_border");
        String rules=config.getProperty("host_game_rules");
        String view=config.getProperty("host_view_distance");
        String simulation=config.getProperty("host_simulation_distance");
        List<String> commands=new ArrayList<String>();
        if(difficulty!=null)commands.add("difficulty "+difficulty);
        if(time!=null)commands.add("time set "+time);
        if(weather!=null)commands.add("weather "+weather);
        if(border!=null)commands.add("worldborder set "+border);
        if(rules!=null)for(String rule:rules.split(";"))commands.add("gamerule "+rule);
        if(view!=null || simulation!=null) {
            Object options=field(mc,"options");
            if(view!=null)call(call(options,"renderDistance"),"set",Integer.valueOf(view));
            if(simulation!=null)call(call(options,"simulationDistance"),"set",Integer.valueOf(simulation));
        }
        if(!commands.isEmpty()) {
            FutureTask<Void> settings=new FutureTask<Void>(()->{
                HostCommands source=hostCommand(server);
                Map<String,Object> parsed=new LinkedHashMap<String,Object>();
                for(String command:commands)parsed.put(command,source.validate(command));
                for(Map.Entry<String,Object> command:parsed.entrySet())source.run(command.getKey(),command.getValue());
                return null;
            });
            hostSettings=settings;
            hostSettingsDeadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(15);
            ((Executor)server).execute(settings);
            return false;
        }
        return true;
    }
    static void applyHostPvp(Object server,boolean enabled) throws Exception {
        try {call(server,"setPvpAllowed",enabled);return;}
        catch(NoSuchMethodException missing) {}
        try {call(server,"setPvp",enabled);return;}
        catch(NoSuchMethodException missing) {}
        try {
            Object level=((Iterable<?>)call(server,"getAllLevels")).iterator().next();
            Object rules=call(level,"getGameRules");
            Object key;
            try {key=field(rules.getClass(),"PVP");}
            catch(NoSuchFieldException previous) {
                key=field(rules.getClass(),"RULE_PVP");
                call(call(rules,"getRule",key),"set",enabled,server);
                return;
            }
            call(rules,"set",key,enabled,server);
        } catch(ReflectiveOperationException missing) {
            throw new IllegalStateException("This game adapter does not support the selected PvP override",missing);
        }
    }
    static Object hostGameMode(Object current,String mode) throws Exception {
        Class<?> type=((Enum<?>)current).getDeclaringClass();
        for(Object value:type.getEnumConstants()) {
            try {if(mode.equals(call(value,"getName")))return value;}
            catch(NoSuchMethodException missing) {
                if(mode.equalsIgnoreCase(((Enum<?>)value).name()))return value;
            }
        }
        throw new IllegalStateException("This game adapter does not support game mode: "+mode);
    }
    static int publishLegacy(Object server,Object mode,boolean cheats) throws Exception {
        String reported;
        try {reported=(String)call(server,"publishServer",mode,cheats);}
        catch(NoSuchMethodException explicitPort) {
            int port;
            try(ServerSocket socket=new ServerSocket(0)){port=socket.getLocalPort();}
            if(!Boolean.TRUE.equals(call(server,"publishServer",mode,cheats,port)))
                throw new IllegalStateException("Legacy LAN publication failed");
            return port;
        }
        if(reported==null || !reported.matches("[0-9]{1,5}"))throw new IllegalStateException("Legacy LAN failed to report a port");
        int port=Integer.parseInt(reported);
        if(port<1 || port>65535)throw new IllegalStateException("Legacy LAN returned an invalid port");
        return port;
    }
    static boolean capturedSelected(Object value,int depth,Set<Object> seen) throws Exception {
        if(value==null || depth>3 || !seen.add(value))return false;
        if(type("net.minecraft.world.level.storage.LevelStorageSource$LevelStorageAccess").isInstance(value)) {
            Path path=(Path)call(value,"getLevelPath",field(type("net.minecraft.world.level.storage.LevelResource"),"ROOT"));
            return Files.isSameFile(path,Paths.get(config.getProperty("world")));
        }
        if(!value.getClass().isSynthetic())return false;
        for(Field member:value.getClass().getDeclaredFields())if(!Modifier.isStatic(member.getModifiers()) && !member.getType().isPrimitive()) {
            member.setAccessible(true);if(capturedSelected(member.get(value),depth+1,seen))return true;
        }
        return false;
    }
    static void confirmSelectedBackup(Object mc) throws Exception {
        Object screen=screen(mc);if(screen==null || screen==handledBackup)return;
        if(!type("net.minecraft.client.gui.screens.BackupConfirmScreen").isInstance(screen))return;
        Object listener=field(screen,"onProceed");
        if(!capturedSelected(listener,0,Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>())))throw new IllegalStateException("Backup confirmation is not bound to the selected managed world");
        handledBackup=screen;
        for(Method method:type("net.minecraft.client.gui.screens.BackupConfirmScreen$Listener").getDeclaredMethods())if(Arrays.equals(method.getParameterTypes(),new Class<?>[]{boolean.class,boolean.class})) {
            System.out.println("AETHERLOOM_AGENT_SELECTED_WORLD_BACKUP_AND_CONTINUE");
            method.invoke(listener,true,false);return;
        }
        throw new NoSuchMethodException("Backup continuation capability");
    }
    static void join(Object mc) throws Exception {
        if(pinger==null && type("net.minecraft.client.gui.screens.TitleScreen").isInstance(screen(mc))) {
            if(legacy) {
                String address=config.getProperty("join");
                if(!address.matches("127\\.0\\.0\\.1:[0-9]{1,5}"))throw new IllegalArgumentException("Legacy join requires the managed loopback proxy");
                Object title=make("net.minecraft.client.gui.screens.TitleScreen");
                Object connect=make("net.minecraft.client.gui.screens.ConnectScreen",title,mc,"127.0.0.1",Integer.parseInt(address.substring(10)));
                connecting=true;
                call(mc,"legacySetScreen",connect);
                return;
            }
            Object serverType=modern()?field(type("net.minecraft.client.multiplayer.ServerData$Type"),"LAN"):Boolean.FALSE;
            target=make("net.minecraft.client.multiplayer.ServerData","Aetherloom",config.getProperty("join"),serverType);
            if(config.getProperty("adapter").endsWith("-vanilla")) {
                // The controller already obtained the ready Host and opened
                // the relay proxy. Vanilla does not need a loader status ping.
                connect(mc);
                return;
            }
            pinger=make("net.minecraft.client.multiplayer.ServerStatusPinger");
            try {call(pinger,"pingServer",target,(Runnable)()->{},(Runnable)()->{});}
            catch(NoSuchMethodException alternate){
                try {call(pinger,"pingServer",target,(Runnable)()->{});}
                catch(NoSuchMethodException newer){
                    Object nio=field(type("net.minecraft.server.network.EventLoopGroupHolder"),"NIO");
                    call(pinger,"pingServer",target,(Runnable)()->{},(Runnable)()->{},nio);
                }
            }
            joinDeadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(60);
        }
        if(pinger!=null) {
            call(pinger,"tick");
            if(((Number)field(target,"ping")).longValue()>=0) {
                call(pinger,"removeAll");pinger=null;connect(mc);
            } else if(System.nanoTime()>joinDeadline)throw new IllegalStateException(config.getProperty("adapter")+" discovery timeout");
        }
    }
    static void connect(Object mc) throws Exception {
        connecting=true;
        Object address=call(type("net.minecraft.client.multiplayer.resolver.ServerAddress"),"parseString",config.getProperty("join"));
        Object title=make("net.minecraft.client.gui.screens.TitleScreen");
        Class<?> targetScreen=type("net.minecraft.client.gui.screens.ConnectScreen");
        try {call(targetScreen,"startConnecting",title,mc,address,target,false,null);}
        catch(NoSuchMethodException older){
            try {call(targetScreen,"startConnecting",title,mc,address,target,false);}
            catch(NoSuchMethodException legacy){call(targetScreen,"startConnecting",title,mc,address,target);}
        }
    }
    static String quote(String value) {
        StringBuilder out=new StringBuilder("\"");
        for(char c:value.toCharArray()) {if(c=='"' || c=='\\')out.append('\\').append(c);else if(c<32)out.append(String.format("\\u%04x",(int)c));else out.append(c);}
        return out.append('"').toString();
    }
    static void checkIdentity(Object player) throws Exception {
        if(config.containsKey("legacy_name")) {
            // On these versions the server-side construction guard validates
            // the username before player files are read.
            if(!config.containsKey("join") && !Boolean.parseBoolean(config.getProperty("inspect")) && !legacyOwnerSeen)
                throw new IllegalStateException("Legacy server did not verify the local Host name");
            return;
        }
        UUID expected=UUID.fromString(config.getProperty("identity"));
        Object actual=call(player,"getUUID");
        if((modern() || directHooks) && config.containsKey("join") && !"littleskin".equals(config.getProperty("auth_mode")) && !expected.equals(actual)) {
            // Forge 52's configuration barrier runs after the login profile
            // packet. The Host validates and applies the member UUID before
            // loading player data; align the offline client's earlier profile.
            Object profile=call(player,"getGameProfile");
            UUID vanilla=UUID.nameUUIDFromBytes(("OfflinePlayer:"+profileName(profile)).getBytes(StandardCharsets.UTF_8));
            if(!vanilla.equals(call(player,"getUUID")))throw new IllegalStateException("Unexpected offline login identity");
            Object connection=call(minecraft(),"getConnection");
            Object corrected=resolveProfile(profile,expected);
            if(corrected!=profile)replaceProfileField(player,"gameProfile",profile,corrected);
            try {
                Object localProfile=call(connection,"getLocalGameProfile");
                Object correctedLocal=resolveProfile(localProfile,expected);
                if(correctedLocal!=localProfile)replaceProfileField(connection,"localGameProfile",localProfile,correctedLocal);
            } catch(NoSuchMethodException older) {
                if(!legacy)throw older;
            }
            if(legacy) {
                try {call(player,"setUUID",expected);}
                catch(NoSuchMethodException older){replaceProfileField(player,"legacyUuid",actual,expected);}
            } else call(player,"setUUID",expected);
            System.out.println("AETHERLOOM_AGENT_OFFLINE_CONFIGURATION_IDENTITY_ALIGNED");
        }
        if(!expected.equals(call(player,"getUUID")))throw new IllegalStateException("Actual player UUID differs from managed identity");
    }
    static void replaceProfileField(Object instance,String name,Object previous,Object replacement) throws Exception {
        for(Class<?> owner=instance.getClass();owner!=null;owner=owner.getSuperclass()) {
            for(String alias:aliases(owner,name)) {
                Field member;
                try {member=owner.getDeclaredField(alias);}
                catch(NoSuchFieldException ignored){continue;}
                if(member.getType()!=previous.getClass() || Modifier.isStatic(member.getModifiers()))continue;
                member.setAccessible(true);
                if(member.get(instance)!=previous)continue;
                member.set(instance,replacement);
                return;
            }
        }
        throw new NoSuchFieldException("Cannot replace immutable player profile "+name);
    }
    static void emit(String event,int port) {
        // Never block a render/server thread on HTTP.
        io.submit(()->{try{request("","{\"event\":"+quote(event)+",\"port\":"+port+",\"world\":"+quote(config.getProperty("world"))+",\"uuid\":"+quote(config.getProperty("identity"))+",\"protocol\":1,\"component\":\"agent\",\"capabilities\":[\"world\",\"lan\",\"join\",\"identity\",\"saved\",\"exit\"]}");if("saved".equals(event))finished=true;}
            catch(Throwable error){fail(error);}});
    }
    static void emitStats(int count) {
        if(!statsPending.compareAndSet(false,true))return;
        io.submit(()->{
            try {request("","{\"event\":\"stats\",\"players\":"+count+",\"world\":"+quote(config.getProperty("world"))+",\"uuid\":"+quote(config.getProperty("identity"))+"}");}
            catch(Exception ignored) {} finally {statsPending.set(false);}
        });
    }
    static String request(String suffix,String body) throws Exception {
        HttpURLConnection connection=(HttpURLConnection)new URL(config.getProperty("endpoint")+suffix).openConnection();
        connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(2000);connection.setReadTimeout(3000);
        connection.setRequestProperty("Authorization","Bearer "+config.getProperty("token"));
        try {
            if(body!=null) {connection.setRequestMethod("POST");connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");
                try(OutputStream output=connection.getOutputStream()){output.write(body.getBytes(StandardCharsets.UTF_8));}}
            if(connection.getResponseCode()!=200)throw new IOException("Control rejected "+connection.getResponseCode());
            try(InputStream input=connection.getInputStream();ByteArrayOutputStream data=new ByteArrayOutputStream()) {
                byte[] chunk=new byte[1024];int n;while((n=input.read(chunk))!=-1){if(data.size()+n>16384)throw new IOException("Oversize control response");data.write(chunk,0,n);}
                return new String(data.toByteArray(),StandardCharsets.UTF_8);
            }
        }finally{connection.disconnect();}
    }
    static void fail(Throwable error) {
        while((error instanceof InvocationTargetException || error instanceof CompletionException) && error.getCause()!=null)error=error.getCause();
        stop=true;String message=error.getClass().getName()+": "+String.valueOf(error.getMessage());
        if(reports.add(message)) {System.err.println("AETHERLOOM_AGENT_FAILED "+message);if(config.containsKey("endpoint"))io.submit(()->{try{request("","{\"event\":\"error\",\"message\":"+quote(message)+",\"port\":0,\"world\":"+quote(config.getProperty("world"))+",\"uuid\":"+quote(config.getProperty("identity"))+"}");}catch(Exception ignored){}});}
    }
}
