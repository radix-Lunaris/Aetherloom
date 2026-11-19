package online.superyk7hero.aetherloom.agent;

import java.util.function.BiConsumer;
import java.util.function.UnaryOperator;

/** JDK-only bootstrap bridge; game classes never link to the agent or ASM. */
public final class BootstrapHooks {
    public static volatile boolean serverInstalled,profileInstalled,profileLookupInstalled;
    public static volatile boolean clientTickInstalled;
    public static volatile BiConsumer<Object,String> lifecycle;
    public static volatile UnaryOperator<Object> identity;
    public static volatile Runnable clientTick;
    private static final ThreadLocal<Object> saving=new ThreadLocal<Object>();
    public static void beginSave(Object server){saving.set(server);}
    public static void saved(){Object server=saving.get();saving.remove();if(server!=null)server(server,"saved");}
    public static void server(Object value,String phase) {
        BiConsumer<Object,String> callback=lifecycle;if(callback!=null)callback.accept(value,phase);
    }
    public static Object profile(Object value) {
        UnaryOperator<Object> callback=identity;
        if(callback==null)throw new IllegalStateException("Identity controller unavailable");
        return callback.apply(value);
    }
    public static void tickClient() {
        Runnable callback=clientTick;
        if(callback!=null)callback.run();
    }
}
