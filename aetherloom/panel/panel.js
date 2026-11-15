"use strict";
let token="", role="", messageTimer;
const el=id=>document.getElementById(id);
function message(text,error=false){
 const node=el("message");node.textContent=text;node.classList.toggle("error",error);node.hidden=false;
 clearTimeout(messageTimer);messageTimer=setTimeout(()=>{node.hidden=true;},error?12000:4000);
}
async function api(path,body){
 const headers={"Content-Type":"application/json"};if(token)headers.Authorization="Bearer "+token;
 const response=await fetch(new URL("api/"+path,location.href),{method:body?"POST":"GET",headers,body:body?JSON.stringify(body):undefined,cache:"no-store",credentials:"omit"});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"请求失败，请稍后重试");return data;
}
function rows(id,data,keys){
 const target=el(id);target.replaceChildren();
 if(!data.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=keys.length;td.className="empty-cell";
 const title=document.createElement("strong"),hint=document.createElement("span");title.textContent=id==="rooms"?"还没有实例记录":"暂无账号";
 hint.textContent=id==="rooms"?"从客户端创建实例后，可以在这里查看。":"创建第一个软件账号后，它会出现在这里。";td.append(title,hint);tr.append(td);target.append(tr);return;}
 for(const item of data){const tr=document.createElement("tr");for(const key of keys){const td=document.createElement("td");let value=item[key];
 if(key==="role"){const badge=document.createElement("span");badge.className="role-badge"+(value==="player"?" player":"");badge.textContent=value;td.append(badge);}
 else{if(key==="state")value=({idle:"空闲",preparing:"准备中",ready:"已就绪",uploading:"同步中"})[value]||value;if(key==="host"&&!value)value="暂无 Host";td.textContent=String(value??"—");if(key==="id")td.className="cell-id";}
 tr.append(td);}target.append(tr);}
}
function gib(n){return n==null?"—":(n/1024**3).toFixed(2);}
function metric(label,value,unit,note,icon){
 const card=document.createElement("div");card.className="metric";
 const caption=document.createElement("div");caption.className="metric-label";caption.textContent=label;
 const symbol=document.createElement("span");symbol.className="metric-icon";symbol.textContent=icon;caption.append(symbol);
 const number=document.createElement("strong");number.textContent=String(value);const units=document.createElement("span");units.textContent=unit;number.append(units);
 const foot=document.createElement("small");foot.textContent=note;card.append(caption,number,foot);return card;
}
async function refresh(){
 const [status,rooms,users]=await Promise.all([api("status"),api("rooms"),api("users")]);
 el("metrics").replaceChildren(metric("可用磁盘",gib(status.disk_free),"GiB","容量 "+gib(status.disk_total)+" GiB","▱"),
 metric("可用内存",gib(status.memory_available),"GiB","物理内存 "+gib(status.memory_total)+" GiB","▤"),
 metric("共享实例",status.rooms,"个","服务器中的实例记录","▦"),metric("软件账号",status.accounts,"个","独立的软件登录身份","◎"));
 const diskUsed=status.disk_total?100*(1-status.disk_free/status.disk_total):0;
 el("disk-progress").value=diskUsed;el("disk-label").textContent=diskUsed.toFixed(1)+"% · "+gib(status.disk_total-status.disk_free)+" / "+gib(status.disk_total)+" GiB";
 const memUsed=status.memory_total?100*(1-status.memory_available/status.memory_total):0;el("memory-progress").value=memUsed;
 el("memory-label").textContent=status.memory_total?memUsed.toFixed(1)+"% · "+gib(status.memory_total-status.memory_available)+" / "+gib(status.memory_total)+" GiB":"暂无数据";
 el("cpu-count").textContent=status.cpu_count??"—";el("load-average").textContent=status.load_average?status.load_average[0].toFixed(2):"—";
 el("service-version").textContent=status.version||"—";el("updated").textContent=new Date().toLocaleTimeString();
 el("room-count").textContent=rooms.length+" 个实例";el("account-count").textContent=users.length+" 个账号";
 rows("rooms",rooms,["id","owner","host","state","epoch"]);rows("users",users,["name","role"]);
}
function showView(name){
 document.querySelectorAll(".view").forEach(v=>{v.hidden=v.id!=="view-"+name;});
 document.querySelectorAll("[data-view]").forEach(b=>{const active=b.dataset.view===name;b.classList.toggle("active",active);if(active)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
 el("breadcrumb").textContent=({overview:"服务器概况",instances:"实例与会话",accounts:"账号管理"})[name];
}
document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
el("toggle-password").addEventListener("click",()=>{const visible=el("password").type==="password";el("password").type=visible?"text":"password";el("toggle-password").textContent=visible?"隐藏":"显示";el("toggle-password").setAttribute("aria-label",visible?"隐藏密码":"显示密码");});
el("login").addEventListener("submit",async e=>{
 e.preventDefault();const button=e.target.querySelector('button[type="submit"]');button.disabled=true;button.textContent="正在连接…";
 try{const result=await api("login",{username:el("username").value,password:el("password").value});token=result.token;role=result.role;el("password").value="";
 if(!["root","admin"].includes(role)){await api("logout",{});token="";throw new Error("该账号没有服务器面板权限");}
 el("admin-option").disabled=role!=="root";await refresh();el("actor").textContent=result.username;el("actor-role").textContent=role==="root"?"Root · 服务器所有者":"Admin · 服务器管理员";
 showView("overview");el("workspace").hidden=false;el("login-section").hidden=true;message("登录成功");}
 catch(error){if(token){try{await api("logout",{});}catch{}token="";}message(error.message,true);}
 finally{button.disabled=false;button.textContent="登录控制中心 →";}
});
el("refresh").addEventListener("click",async()=>{const b=el("refresh");b.disabled=true;try{await refresh();message("数据已更新");}catch(e){message(e.message,true);}finally{b.disabled=false;}});
el("logout").addEventListener("click",async()=>{try{await api("logout",{});}catch{}finally{token="";location.reload();}});
el("create-user").addEventListener("submit",async e=>{
 e.preventDefault();const button=e.target.querySelector("button");button.disabled=true;
 try{await api("users",{username:el("new-name").value,password:el("new-password").value,role:el("new-role").value});el("new-password").value="";el("new-name").value="";await refresh();message("账号已创建，请通过安全渠道告知使用者。");}
 catch(error){message(error.message,true);}finally{button.disabled=false;}
});
