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
    static volatile boolean fabric;
    static boolean configurationApi,postTickApi;
    static Object hostProfile,haltedServer;
    static Object handledBackup;
    static Class<?> hooks;
    static final AtomicBoolean tickPending=new AtomicBoolean();
    static long joinDeadline;
    static final Set<String> reports=Collections.synchronizedSet(new HashSet<String>());
    static final AtomicBoolean statsPending=new AtomicBoolean();
    static long nextStats;

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
        try(InputStream mappings=Agent.class.getResourceAsStream("/forge-1.20.1.properties")) {names.load(mappings);}
        String adapter=config.getProperty("adapter","");
        if(adapter.endsWith("-fabric") || adapter.endsWith("-quilt")) {
            Properties aliases=new Properties();
            String version=adapter.substring(0,adapter.lastIndexOf('-'));
            InputStream resource=Agent.class.getResourceAsStream("/fabric-"+version+".properties");
            if(resource==null) {
                String baseline=version.startsWith("1.20.1") || version.startsWith("1.19") || version.startsWith("1.18") || version.startsWith("1.17") || version.startsWith("1.16")?"1.20.1":"1.21.1";
                resource=Agent.class.getResourceAsStream("/fabric-"+baseline+".properties");
                System.out.println("AETHERLOOM_AGENT_MAPPING_BASELINE requested="+version+" baseline="+baseline+" runtime capabilities required");
            }
            try(InputStream source=resource) {
                if(source==null)throw new IllegalArgumentException("Missing bundled mapping baselines");
                aliases.load(source);
            }
            instrumentation.appendToBootstrapClassLoaderSearch(new JarFile(new File(Agent.class.getProtectionDomain().getCodeSource().getLocation().toURI())));
            hooks=Class.forName("online.superyk7hero.aetherloom.agent.BootstrapHooks",true,null);
            hooks.getField("lifecycle").set(null,(BiConsumer<Object,String>)Agent::serverLifecycle);
            hooks.getField("identity").set(null,(Consumer<Object>)Agent::profileIdentity);
            instrumentation.addTransformer(new LoaderTransformer(aliases));
            names.clear();names.putAll(aliases);fabric=true;
        }
        Thread worker=new Thread(()->{
            try {
                long deadline=System.nanoTime()+TimeUnit.MINUTES.toNanos(10);
                while(gameLoader==null && System.nanoTime()<deadline) {
                    for(Class<?> type:instrumentation.getAllLoadedClasses())
                        if(type.getName().equals("net.minecraft.client.Minecraft") || fabric && type.getName().equals(names.getProperty("class.net.minecraft.client.Minecraft"))) {gameLoader=type.getClassLoader();break;}
                    if(gameLoader==null) Thread.sleep(100);
                }
                if(gameLoader==null) throw new IllegalStateException("Game loader discovery timed out");
                Thread.currentThread().setContextClassLoader(gameLoader);
                if(fabric)exposeBootstrapBridge();
                try {Class.forName("net.neoforged.neoforge.common.NeoForge",false,gameLoader);neoForge=true;}
                catch(ClassNotFoundException forge) {neoForge=false;}
                // QuickPlay can construct Minecraft while Forge is still setting
                // up its event bus. Register only after mod loading completes.
                while((minecraft()==null || !fabric && Boolean.TRUE.equals(call(type("net.minecraftforge.client.loading.ClientModLoader"),"isLoading"))) && System.nanoTime()<deadline)Thread.sleep(100);
                try {type("net.minecraft.client.multiplayer.ServerData$Type");modernApi=true;}
                catch(ClassNotFoundException legacyApi) {modernApi=false;}
                if(!fabric) {
                    try {type("net.minecraftforge.event.network.GatherLoginConfigurationTasksEvent");configurationApi=!neoForge;}catch(ClassNotFoundException missing){configurationApi=false;}
                    try {type("net.minecraftforge.event.TickEvent$ClientTickEvent$Post");postTickApi=true;}catch(ClassNotFoundException missing){postTickApi=false;}
                }
                if(fabric)emit("capabilities",0);else install();
                while(!exitRequested && (fabric || !finished)) {
                    if(!finished)stop=request("",null).contains("\"stop\": true");
                    if(fabric && tickPending.compareAndSet(false,true)) {
                        ((Executor)minecraft()).execute(()->{try{tick();}catch(Throwable error){fail(error);}finally{tickPending.set(false);}});
                    }
                    Thread.sleep(fabric?100:500);
                }
            } catch(Throwable error) {fail(error);}
        },"Aetherloom agent bootstrap");worker.setDaemon(true);worker.start();
    }

    static Class<?> type(String name) throws Exception {
        if(neoForge) {
            if(name.equals("net.minecraftforge.common.MinecraftForge"))name="net.neoforged.neoforge.common.NeoForge";
            else if(name.equals("net.minecraftforge.event.TickEvent$ClientTickEvent$Post"))name="net.neoforged.neoforge.client.event.ClientTickEvent$Post";
            else if(name.startsWith("net.minecraftforge.eventbus."))name=name.replace("net.minecraftforge.eventbus.","net.neoforged.bus.");
            else if(name.startsWith("net.minecraftforge."))name=name.replace("net.minecraftforge.","net.neoforged.neoforge.");
        }
        if(fabric)name=names.getProperty("class."+name,name);
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
            for(Method m:c.getDeclaredMethods()) if(!m.isBridge() && m.getName().equals(alias) && compatible(m.getParameterTypes(),args)) matches.add(m);
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
    static void profileIdentity(Object profile) {
        if(config.containsKey("join") || Boolean.parseBoolean(config.getProperty("inspect")))return;
        try {
            if(profile==hostProfile)return;
            if(!loaded && UUID.fromString(config.getProperty("identity")).equals(call(profile,"getId"))) {hostProfile=profile;return;}
            verifyIdentity(profile);
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
    static void verifyIdentity(Object profile) throws Exception {
        String name=(String)call(profile,"getName");
        String lookup="littleskin".equals(config.getProperty("auth_mode"))?"by-uuid/"+call(profile,"getId"):URLEncoder.encode(name,"UTF-8");
        String response=request("/identity/"+lookup,null);
        java.util.regex.Matcher match=java.util.regex.Pattern.compile("\\\"uuid\\\"\\s*:\\s*\\\"([0-9a-fA-F-]{36})\\\"").matcher(response);
        if(!match.find())throw new IllegalStateException("Unregistered peer identity");
        UUID id=UUID.fromString(match.group(1));
        if("littleskin".equals(config.getProperty("auth_mode"))) {
            if(!id.equals(call(profile,"getId")))throw new IllegalStateException("Verified LittleSkin UUID mismatch");
            return;
        }
        Field identity=profile.getClass().getDeclaredField("id");identity.setAccessible(true);identity.set(profile,id);
        if(!id.equals(call(profile,"getId")))throw new IllegalStateException("UUID application failed");
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
        Object resource=field(type("net.minecraft.world.level.storage.LevelResource"),"ROOT");
        return Files.isSameFile((Path)call(server,"getWorldPath",resource),Paths.get(config.getProperty("world")));
    }
    static void leave(Object mc) throws Exception {
        Object level=field(mc,"level");if(level!=null)call(level,"disconnect");
        Object server=call(mc,"getSingleplayerServer");if(server!=null)call(server,"halt",false);
        Object title=make("net.minecraft.client.gui.screens.TitleScreen");
        try {call(mc,modern()?"disconnect":"clearLevel",title);}
        catch(NoSuchMethodException alternate){call(mc,modern()?"clearLevel":"disconnect",title);}
    }
    static void tick() throws Exception {
        Object mc=minecraft(),player=field(mc,"player"),level=field(mc,"level"),server=call(mc,"getSingleplayerServer");
        if(!config.containsKey("join") && !loaded && !stopping && player==null && server==null)confirmSelectedBackup(mc);
        // QuickPlay may have started the integrated server before registration.
        // Recover only the explicitly selected world, never an arbitrary world.
        if(!config.containsKey("join") && !loaded && pending==null && !stopping && server!=null && player!=null && level!=null && selected(server))pending=server;
        if(loaded && System.nanoTime()>=nextStats) {
            nextStats=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            Object connection=server==null?call(mc,"getConnection"):null;
            int count=server!=null?((Number)call(server,"getPlayerCount")).intValue():connection!=null?((Collection<?>)call(connection,"getOnlinePlayers")).size():0;
            emitStats(count);
        }
        if(config.containsKey("join")) {
            Object screen=field(mc,"screen");
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
            if(fabric && (!hooks.getField("serverInstalled").getBoolean(null) || !hooks.getField("profileInstalled").getBoolean(null)))throw new IllegalStateException("Required lifecycle/identity hooks were not installed");
            pending=null;int port=0;
            if(!Boolean.parseBoolean(config.getProperty("inspect"))) {
                try(ServerSocket socket=new ServerSocket(0)){port=socket.getLocalPort();}
                call(server,"setUsesAuthentication","littleskin".equals(config.getProperty("auth_mode")));
                if(!Boolean.TRUE.equals(call(server,"publishServer",call(server,"getDefaultGameType"),false,port)))throw new IllegalStateException("LAN publication failed");
            }
            checkIdentity(player);loaded=true;emit("ready",port);
        }
        if(stop && !stopping) {stopping=true;if(level!=null || server!=null)leave(mc);else call(mc,"stop");}
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
        Object screen=field(mc,"screen");if(screen==null || screen==handledBackup)return;
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
        if(pinger==null && type("net.minecraft.client.gui.screens.TitleScreen").isInstance(field(mc,"screen"))) {
            Object serverType=modern()?field(type("net.minecraft.client.multiplayer.ServerData$Type"),"LAN"):Boolean.FALSE;
            target=make("net.minecraft.client.multiplayer.ServerData","Aetherloom",config.getProperty("join"),serverType);
            pinger=make("net.minecraft.client.multiplayer.ServerStatusPinger");
            try {call(pinger,"pingServer",target,(Runnable)()->{},(Runnable)()->{});}
            catch(NoSuchMethodException older){call(pinger,"pingServer",target,(Runnable)()->{});}
            joinDeadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(60);
        }
        if(pinger!=null) {
            call(pinger,"tick");
            if(((Number)field(target,"ping")).longValue()>=0) {
                call(pinger,"removeAll");pinger=null;connecting=true;
                Object address=call(type("net.minecraft.client.multiplayer.resolver.ServerAddress"),"parseString",config.getProperty("join"));
                Object title=make("net.minecraft.client.gui.screens.TitleScreen");
                try {call(type("net.minecraft.client.gui.screens.ConnectScreen"),"startConnecting",title,mc,address,target,false,null);}
                catch(NoSuchMethodException older){call(type("net.minecraft.client.gui.screens.ConnectScreen"),"startConnecting",title,mc,address,target,false);}
            } else if(System.nanoTime()>joinDeadline)throw new IllegalStateException((neoForge?"NeoForge":fabric?"Fabric/Quilt":"Forge")+" discovery timeout");
        }
    }
    static String quote(String value) {
        StringBuilder out=new StringBuilder("\"");
        for(char c:value.toCharArray()) {if(c=='"' || c=='\\')out.append('\\').append(c);else if(c<32)out.append(String.format("\\u%04x",(int)c));else out.append(c);}
        return out.append('"').toString();
    }
    static void checkIdentity(Object player) throws Exception {
        UUID expected=UUID.fromString(config.getProperty("identity"));
        if((modern() || fabric) && config.containsKey("join") && !"littleskin".equals(config.getProperty("auth_mode")) && !expected.equals(call(player,"getUUID"))) {
            // Forge 52's configuration barrier runs after the login profile
            // packet. The Host validates and applies the member UUID before
            // loading player data; align the offline client's earlier profile.
            Object profile=call(player,"getGameProfile");
            UUID vanilla=UUID.nameUUIDFromBytes(("OfflinePlayer:"+call(profile,"getName")).getBytes(StandardCharsets.UTF_8));
            if(!vanilla.equals(call(player,"getUUID")))throw new IllegalStateException("Unexpected offline login identity");
            Field id=profile.getClass().getDeclaredField("id");id.setAccessible(true);id.set(profile,expected);
            Object connection=call(minecraft(),"getConnection");
            Object localProfile=call(connection,"getLocalGameProfile");id.set(localProfile,expected);
            call(player,"setUUID",expected);
            System.out.println("AETHERLOOM_AGENT_OFFLINE_CONFIGURATION_IDENTITY_ALIGNED");
        }
        if(!expected.equals(call(player,"getUUID")))throw new IllegalStateException("Actual player UUID differs from managed identity");
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
