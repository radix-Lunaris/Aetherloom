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

/** Java 8 compatible, no game or third-party linkage in the public agent. */
public final class Agent {
    static final Properties config=new Properties(), names=new Properties();
    static final ExecutorService io=Executors.newSingleThreadExecutor(r->{Thread t=new Thread(r,"Aetherloom agent control");t.setDaemon(true);return t;});
    static volatile ClassLoader gameLoader;
    static volatile boolean stop,finished,loaded,joined,stopping;
    static volatile Object pending,pinger,target;
    static volatile boolean connecting;
    static long joinDeadline;
    static final Set<String> reports=Collections.synchronizedSet(new HashSet<String>());

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
        if (!"1.20.1-forge".equals(config.getProperty("adapter"))) throw new IllegalArgumentException("Unverified adapter");
        try(InputStream mappings=Agent.class.getResourceAsStream("/forge-1.20.1.properties")) {names.load(mappings);}
        Thread worker=new Thread(()->{
            try {
                long deadline=System.nanoTime()+TimeUnit.MINUTES.toNanos(10);
                while(gameLoader==null && System.nanoTime()<deadline) {
                    for(Class<?> type:instrumentation.getAllLoadedClasses())
                        if(type.getName().equals("net.minecraft.client.Minecraft")) {gameLoader=type.getClassLoader();break;}
                    if(gameLoader==null) Thread.sleep(100);
                }
                if(gameLoader==null) throw new IllegalStateException("Game loader discovery timed out");
                Thread.currentThread().setContextClassLoader(gameLoader);
                install();
                while(!finished) {
                    stop=request("",null).contains("\"stop\": true");Thread.sleep(500);
                }
            } catch(Throwable error) {fail(error);}
        },"Aetherloom agent bootstrap");worker.setDaemon(true);worker.start();
    }

    static Class<?> type(String name) throws Exception {return Class.forName(name,true,gameLoader);}
    static String[] aliases(Class<?> owner,String name) {
        String value=names.getProperty(owner.getName()+"."+name,name);
        return value.split(",");
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
            for(Method m:c.getDeclaredMethods()) if(m.getName().equals(alias) && compatible(m.getParameterTypes(),args)) matches.add(m);
        // Overrides select the closest declaration, never an arbitrary overload.
        Method selected=null;
        for(Class<?> c=owner;c!=null && selected==null;c=c.getSuperclass()) {
            for(Method m:matches) if(m.getDeclaringClass()==c) {
                if(selected!=null) throw new IllegalStateException("Ambiguous mapped method: "+name);
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
            if(!config.containsKey("join")) {Object server=call(event,"getServer");if(selected(server))pending=server;}
        }));
        listen(bus,"net.minecraftforge.event.server.ServerStoppedEvent",checked(event->{
            Object server=call(event,"getServer");if(loaded && selected(server)) {loaded=false;emit("saved",0);}
        }));
        listen(bus,"net.minecraftforge.event.entity.player.PlayerNegotiationEvent",checked(event->{
            if(config.containsKey("join") || Boolean.parseBoolean(config.getProperty("inspect")))return;
            // The integrated Host joins via an in-memory connection, not a relay peer.
            if(Boolean.TRUE.equals(call(call(event,"getConnection"),"isMemoryConnection")))return;
            CompletableFuture<Void> result=CompletableFuture.runAsync(()->{
                try {
                    Object profile=call(event,"getProfile");String name=(String)call(profile,"getName");
                    String response=request("/identity/"+URLEncoder.encode(name,"UTF-8"),null);
                    java.util.regex.Matcher match=java.util.regex.Pattern.compile("\\\"uuid\\\"\\s*:\\s*\\\"([0-9a-fA-F-]{36})\\\"").matcher(response);
                    if(!match.find())throw new IllegalStateException("Unregistered peer identity");
                    UUID id=UUID.fromString(match.group(1));Field identity=profile.getClass().getDeclaredField("id");identity.setAccessible(true);identity.set(profile,id);
                    if(!id.equals(call(profile,"getId")))throw new IllegalStateException("UUID application failed");
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
        listen(bus,"net.minecraftforge.event.TickEvent$ClientTickEvent",checked(event->{if("END".equals(String.valueOf(field(event,"phase"))))tick();}));
        emit("capabilities",0);
        System.out.println("AETHERLOOM_AGENT_ADAPTER_INSTALLED 1.20.1-forge");
    }
    static Object minecraft() throws Exception {return call(type("net.minecraft.client.Minecraft"),"getInstance");}
    static boolean selected(Object server) throws Exception {
        Object resource=field(type("net.minecraft.world.level.storage.LevelResource"),"ROOT");
        return Files.isSameFile((Path)call(server,"getWorldPath",resource),Paths.get(config.getProperty("world")));
    }
    static void leave(Object mc) throws Exception {
        Object level=field(mc,"level");if(level!=null)call(level,"disconnect");
        Object server=call(mc,"getSingleplayerServer");if(server!=null)call(server,"halt",false);
        call(mc,"clearLevel",make("net.minecraft.client.gui.screens.TitleScreen"));
    }
    static void tick() throws Exception {
        Object mc=minecraft(),player=field(mc,"player"),level=field(mc,"level"),server=call(mc,"getSingleplayerServer");
        if(config.containsKey("join")) {
            if(joined && player==null && level==null)finished=true;
            else if(!joined && player!=null && level!=null && server==null) {checkIdentity(player);emit("joined",0);joined=true;loaded=true;}
            else if(!connecting && !joined)join(mc);
        }
        if(finished && level==null && server==null) {call(mc,"stop");return;}
        Object candidate=pending;
        if(candidate!=null && server==candidate && player!=null && level!=null) {
            pending=null;int port=0;
            if(!Boolean.parseBoolean(config.getProperty("inspect"))) {
                try(ServerSocket socket=new ServerSocket(0)){port=socket.getLocalPort();}
                call(server,"setUsesAuthentication",false);
                if(!Boolean.TRUE.equals(call(server,"publishServer",call(server,"getDefaultGameType"),false,port)))throw new IllegalStateException("LAN publication failed");
            }
            checkIdentity(player);loaded=true;emit("ready",port);
        }
        if(stop && !stopping) {stopping=true;if(level!=null || server!=null)leave(mc);else call(mc,"stop");}
    }
    static void join(Object mc) throws Exception {
        if(pinger==null && type("net.minecraft.client.gui.screens.TitleScreen").isInstance(field(mc,"screen"))) {
            target=make("net.minecraft.client.multiplayer.ServerData","Aetherloom",config.getProperty("join"),false);
            pinger=make("net.minecraft.client.multiplayer.ServerStatusPinger");
            call(pinger,"pingServer",target,(Runnable)()->{});joinDeadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(30);
        }
        if(pinger!=null) {
            call(pinger,"tick");
            if(((Number)field(target,"ping")).longValue()>=0 && field(target,"forgeData")!=null) {
                call(pinger,"removeAll");pinger=null;connecting=true;
                Object address=call(type("net.minecraft.client.multiplayer.resolver.ServerAddress"),"parseString",config.getProperty("join"));
                call(type("net.minecraft.client.gui.screens.ConnectScreen"),"startConnecting",make("net.minecraft.client.gui.screens.TitleScreen"),mc,address,target,false);
            } else if(System.nanoTime()>joinDeadline)throw new IllegalStateException("Forge discovery timeout");
        }
    }
    static String quote(String value) {
        StringBuilder out=new StringBuilder("\"");
        for(char c:value.toCharArray()) {if(c=='"' || c=='\\')out.append('\\').append(c);else if(c<32)out.append(String.format("\\u%04x",(int)c));else out.append(c);}
        return out.append('"').toString();
    }
    static void checkIdentity(Object player) throws Exception {
        UUID expected=UUID.fromString(config.getProperty("identity"));
        if(!expected.equals(call(player,"getUUID")))throw new IllegalStateException("Actual player UUID differs from managed identity");
    }
    static void emit(String event,int port) {
        // Never block a render/server thread on HTTP.
        io.submit(()->{try{request("","{\"event\":"+quote(event)+",\"port\":"+port+",\"world\":"+quote(config.getProperty("world"))+",\"uuid\":"+quote(config.getProperty("identity"))+",\"protocol\":1,\"component\":\"agent\",\"capabilities\":[\"world\",\"lan\",\"join\",\"identity\",\"saved\",\"exit\"]}");if("saved".equals(event))finished=true;}
            catch(Throwable error){fail(error);}});
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
        stop=true;String message=error.getClass().getName()+": "+String.valueOf(error.getMessage());
        if(reports.add(message)) {System.err.println("AETHERLOOM_AGENT_FAILED "+message);if(config.containsKey("endpoint"))io.submit(()->{try{request("","{\"event\":\"error\",\"port\":0,\"world\":"+quote(config.getProperty("world"))+",\"uuid\":"+quote(config.getProperty("identity"))+"}");}catch(Exception ignored){}});}
    }
}
