package online.superyk7hero.aetherloom.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.*;
import org.objectweb.asm.*;

/** Fabric/Quilt hooks use semantic, versioned aliases; no loader API Mod. */
public final class LoaderTransformer implements ClassFileTransformer {
    final Properties names;
    final boolean earlyProfile;
    final boolean legacy;
    final boolean nameData;
    static final String HOOK="online/superyk7hero/aetherloom/agent/BootstrapHooks";
    public LoaderTransformer(Properties names,boolean earlyProfile,boolean legacy,boolean nameData){
        this.names=names;
        this.earlyProfile=earlyProfile;
        this.legacy=legacy;
        this.nameData=nameData;
    }
    boolean named(String owner,String semantic,String actual) {
        return Arrays.asList((names.getProperty(owner.replace('/','.')+"."+semantic,semantic)+","+semantic).split(",")).contains(actual);
    }
    public byte[] transform(ClassLoader loader,String name,Class<?> previous,ProtectionDomain domain,byte[] bytes) {
        if(name==null)return null;
        String server=names.getProperty("class.net.minecraft.server.MinecraftServer","net.minecraft.server.MinecraftServer").replace('.','/');
        String player=names.getProperty("class.net.minecraft.server.level.ServerPlayer","net.minecraft.server.level.ServerPlayer").replace('.','/');
        boolean configuration=earlyProfile && name.equals("net/minecraft/server/network/ServerConfigurationPacketListenerImpl");
        String mappedClient=names.getProperty("class.net.minecraft.client.Minecraft","");
        boolean client=legacy && names.containsKey(mappedClient+".legacyClientTick") && name.equals(mappedClient.replace('.','/'));
        if(!name.equals(server) && !name.equals(player) && !configuration && !client)return null;
        try {
            ClassReader reader=new ClassReader(bytes);ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);final boolean[] installed=new boolean[6];
            reader.accept(new ClassVisitor(Opcodes.ASM9,writer) {
                public MethodVisitor visitMethod(int access,String method,String descriptor,String signature,String[] exceptions) {
                    MethodVisitor delegate=super.visitMethod(access,method,descriptor,signature,exceptions);
                    boolean halt=name.equals(server) && named(name,"halt",method) && (descriptor.equals("(Z)V") || legacy && descriptor.equals("()V"));
                    boolean save=name.equals(server) && named(name,"stopServer",method) && descriptor.equals("()V");
                    boolean run=name.equals(server) && named(name,"runServer",method) && descriptor.equals("()V");
                    boolean profile=name.equals(player) && method.equals("<init>");
                    boolean profileLookup=configuration && method.equals("<init>");
                    boolean clientTick=client && named(name,"legacyClientTick",method) && descriptor.equals("()V");
                    if(clientTick)installed[5]=true;
                    if(halt)installed[0]=true;if(save)installed[1]=true;if(run)installed[2]=true;
                    if(!halt && !save && !run && !profile && !profileLookup && !clientTick)return delegate;
                    return new MethodVisitor(Opcodes.ASM9,delegate) {
                        final Set<Label> fatal=new HashSet<Label>();
                        boolean hasThis=true;
                        void event(String phase) {super.visitVarInsn(Opcodes.ALOAD,0);super.visitLdcInsn(phase);super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"server","(Ljava/lang/Object;Ljava/lang/String;)V",false);}
                        public void visitCode() {
                            super.visitCode();
                            if(halt)event("halt");
                            if(save){super.visitVarInsn(Opcodes.ALOAD,0);super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"beginSave","(Ljava/lang/Object;)V",false);}
                            if(profile) {
                                int slot=1;
                                Type[] arguments=Type.getArgumentTypes(descriptor);
                                long stringCount=Arrays.stream(arguments).filter(arg->arg.getDescriptor().equals("Ljava/lang/String;")).count();
                                for(Type arg:arguments) {
                                    if(arg.getDescriptor().equals("Lcom/mojang/authlib/GameProfile;")
                                        || nameData && stringCount==1 && arg.getDescriptor().equals("Ljava/lang/String;")) {
                                        installed[3]=true;
                                        super.visitVarInsn(Opcodes.ALOAD,slot);
                                        super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"profile","(Ljava/lang/Object;)Ljava/lang/Object;",false);
                                        super.visitTypeInsn(Opcodes.CHECKCAST,arg.getInternalName());
                                        super.visitVarInsn(Opcodes.ASTORE,slot);
                                        break;
                                    }
                                    slot+=arg.getSize();
                                }
                            }
                        }
                        public void visitTryCatchBlock(Label start,Label end,Label handler,String type) {
                            if(run && "java/lang/Throwable".equals(type))fatal.add(handler);
                            super.visitTryCatchBlock(start,end,handler,type);
                        }
                        public void visitMethodInsn(int opcode,String owner,String method,String desc,boolean iface){
                            super.visitMethodInsn(opcode,owner,method,desc,iface);
                            if(profileLookup && owner.equals("net/minecraft/server/network/CommonListenerCookie")
                                && method.equals("gameProfile") && desc.equals("()Lcom/mojang/authlib/GameProfile;")) {
                                installed[4]=true;
                                super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"profile","(Ljava/lang/Object;)Ljava/lang/Object;",false);
                                super.visitTypeInsn(Opcodes.CHECKCAST,"com/mojang/authlib/GameProfile");
                            }
                        }
                        public void visitFrame(int type,int locals,Object[] local,int stack,Object[] values) {
                            super.visitFrame(type,locals,local,stack,values);
                            hasThis=locals>0 && local[0] instanceof String;
                            if(crashPending){if(hasThis)event("crash");crashPending=false;}
                        }
                        boolean crashPending;
                        public void visitLabel(Label label){super.visitLabel(label);if(fatal.contains(label))crashPending=true;}
                        public void visitInsn(int opcode){
                            if(opcode==Opcodes.RETURN && save)super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"saved","()V",false);
                            if(opcode==Opcodes.RETURN && clientTick)super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"tickClient","()V",false);
                            super.visitInsn(opcode);
                        }
                    };
                }
            },ClassReader.EXPAND_FRAMES);
            if(name.equals(server) && installed[0] && installed[1] && installed[2])BootstrapHooks.serverInstalled=true;
            if(name.equals(player) && installed[3])BootstrapHooks.profileInstalled=true;
            if(configuration && installed[4])BootstrapHooks.profileLookupInstalled=true;
            if(client && installed[5])BootstrapHooks.clientTickInstalled=true;
            System.out.println("AETHERLOOM_AGENT_HOOK_INSTALLED "+name);
            return writer.toByteArray();
        } catch(Throwable error) {throw new IllegalStateException("Game hook failed: "+name,error);}
    }
}
