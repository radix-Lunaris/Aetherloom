package online.superyk7hero.aetherloom.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.*;
import org.objectweb.asm.*;

/** Fabric/Quilt hooks use semantic, versioned aliases; no loader API Mod. */
public final class LoaderTransformer implements ClassFileTransformer {
    final Properties names;
    static final String HOOK="online/superyk7hero/aetherloom/agent/BootstrapHooks";
    public LoaderTransformer(Properties names){this.names=names;}
    boolean named(String owner,String semantic,String actual) {
        return Arrays.asList((names.getProperty(owner.replace('/','.')+"."+semantic,semantic)+","+semantic).split(",")).contains(actual);
    }
    public byte[] transform(ClassLoader loader,String name,Class<?> previous,ProtectionDomain domain,byte[] bytes) {
        String server=names.getProperty("class.net.minecraft.server.MinecraftServer","net.minecraft.server.MinecraftServer").replace('.','/');
        String player=names.getProperty("class.net.minecraft.server.level.ServerPlayer","net.minecraft.server.level.ServerPlayer").replace('.','/');
        if(!name.equals(server) && !name.equals(player))return null;
        try {
            ClassReader reader=new ClassReader(bytes);ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);final boolean[] installed=new boolean[4];
            reader.accept(new ClassVisitor(Opcodes.ASM9,writer) {
                public MethodVisitor visitMethod(int access,String method,String descriptor,String signature,String[] exceptions) {
                    MethodVisitor delegate=super.visitMethod(access,method,descriptor,signature,exceptions);
                    boolean halt=name.equals(server) && named(name,"halt",method) && descriptor.equals("(Z)V");
                    boolean save=name.equals(server) && named(name,"stopServer",method) && descriptor.equals("()V");
                    boolean run=name.equals(server) && named(name,"runServer",method) && descriptor.equals("()V");
                    boolean profile=name.equals(player) && method.equals("<init>");
                    if(halt)installed[0]=true;if(save)installed[1]=true;if(run)installed[2]=true;
                    if(!halt && !save && !run && !profile)return delegate;
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
                                for(Type arg:Type.getArgumentTypes(descriptor)) {
                                    if(arg.getDescriptor().equals("Lcom/mojang/authlib/GameProfile;")) {
                                        installed[3]=true;
                                        super.visitVarInsn(Opcodes.ALOAD,slot);super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"profile","(Ljava/lang/Object;)V",false);break;
                                    }
                                    slot+=arg.getSize();
                                }
                            }
                        }
                        public void visitTryCatchBlock(Label start,Label end,Label handler,String type) {
                            if(run && "java/lang/Throwable".equals(type))fatal.add(handler);
                            super.visitTryCatchBlock(start,end,handler,type);
                        }
                        public void visitFrame(int type,int locals,Object[] local,int stack,Object[] values) {
                            super.visitFrame(type,locals,local,stack,values);
                            hasThis=locals>0 && local[0] instanceof String;
                            if(crashPending){if(hasThis)event("crash");crashPending=false;}
                        }
                        boolean crashPending;
                        public void visitLabel(Label label){super.visitLabel(label);if(fatal.contains(label))crashPending=true;}
                        public void visitInsn(int opcode){if(save && opcode==Opcodes.RETURN)super.visitMethodInsn(Opcodes.INVOKESTATIC,HOOK,"saved","()V",false);super.visitInsn(opcode);}
                    };
                }
            },ClassReader.EXPAND_FRAMES);
            if(name.equals(server) && installed[0] && installed[1] && installed[2])BootstrapHooks.serverInstalled=true;
            if(name.equals(player) && installed[3])BootstrapHooks.profileInstalled=true;
            System.out.println("AETHERLOOM_AGENT_HOOK_INSTALLED "+name);
            return writer.toByteArray();
        } catch(Throwable error) {throw new IllegalStateException("Game hook failed: "+name,error);}
    }
}
