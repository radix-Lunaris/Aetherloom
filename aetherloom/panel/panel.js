"use strict";
let token="", role="", messageTimer, refreshing=false, refreshFailures=0;
let panelAccess=null;
const rowCache=new Map();
const el=id=>document.getElementById(id);
function message(text,error=false){
 const node=el("message");node.textContent=text;node.classList.toggle("error",error);node.hidden=false;
 clearTimeout(messageTimer);messageTimer=setTimeout(()=>{node.hidden=true;},error?12000:4000);
}
async function api(path,body,method){
 const headers={"Content-Type":"application/json"};if(token)headers.Authorization="Bearer "+token;
 const response=await fetch(new URL("api/"+path,location.href),{method:method||(body?"POST":"GET"),headers,body:body?JSON.stringify(body):undefined,cache:"no-store",credentials:"omit"});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"请求失败，请稍后重试");return data;
}
function rows(id,data,keys){
 const target=el(id);
 const cache=rowCache.get(id)||new Map();rowCache.set(id,cache);
 const ids=new Set(data.map(item=>item.id||item.name));
 for(const [key,entry] of cache)if(!ids.has(key)){entry.node.remove();cache.delete(key);}
 target.querySelectorAll('.empty-cell').forEach(cell=>cell.parentElement.remove());
 if(!data.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=keys.length;td.className="empty-cell";
 const title=document.createElement("strong"),hint=document.createElement("span");title.textContent=id==="streams"?"暂无匹配的连接流":id==="rooms"?"还没有实例记录":"暂无账号";
 hint.textContent=id==="streams"?"":id==="rooms"?"从客户端创建实例后，可以在这里查看。":"创建第一个软件账号后，它会出现在这里。";td.append(title,hint);tr.append(td);target.append(tr);return;}
 for(const item of data){
 const identity=item.id||item.name, signature=JSON.stringify(item),old=cache.get(identity);
 if(old&&old.signature===signature)continue;
 const tr=document.createElement("tr");for(const key of keys){const td=document.createElement("td");let value=item[key];
 if(key==="role"){const badge=document.createElement("span");badge.className="role-badge"+(value==="player"?" player":"");badge.textContent=value;td.append(badge);}
 else{if(key==="disabled")value=value?"已停用":"正常";if(key==="state")value=({idle:"空闲",preparing:"准备中",recovery_required:"Host 已断开 · 待恢复",ready:"已就绪",uploading:"同步中"})[value]||value;if(key==="host"&&!value)value="暂无 Host";td.textContent=String(value??"—");if(key==="id")td.className="cell-id";}
 tr.append(td);}
 const actions=document.createElement('td');actions.className='row-actions';
 const button=(label,fn)=>{const b=document.createElement('button');b.type='button';b.className='secondary compact';b.textContent=label;b.addEventListener('click',fn);actions.append(b);};
 if(id==='users'&&item.role!=='root'){
 button('管理',()=>accountDialog(item));
 button(item.disabled?'启用':'停用',()=>confirmAction('确认'+(item.disabled?'启用':'停用')+' '+item.name+'？',()=>api('users/'+encodeURIComponent(item.name),{disabled:!item.disabled},'PATCH')));
 button('删除',()=>confirmAction('删除账号 '+item.name+'？已有登录将立即失效。拥有房间或正在托管的账号不能删除。',()=>api('users/'+encodeURIComponent(item.name),undefined,'DELETE')));
 }else if(id==='users'){actions.textContent='受保护';}
 if(id==="streams" && item.channel==="data" && !item.closed){
 button("断开此流",()=>confirmAction("断开 "+item.player+" 的这条连接？",()=>api("rooms/"+item.room+"/streams/"+item.epoch+"/"+item.id,undefined,"DELETE")));
 }
 if(id==='rooms'&&item.can_manage){
 if(item.required_mods)button('必需模组',()=>manageMods(item));
 button('管理',()=>roomDialog(item));button('成员',()=>membersDialog(item));
 button('恢复',()=>recoveryDialog(item));button('连接状态',()=>connectionsDialog(item));
 button('删除',()=>confirmAction('删除共享房间 '+item.name+'？客户端将无法再使用该房间。存档历史保留在服务端用于恢复。',()=>api('rooms/'+encodeURIComponent(item.id),undefined,'DELETE')));
 }
 tr.append(actions);
 if(old)old.node.replaceWith(tr);else target.append(tr);
 cache.set(identity,{signature,node:tr});}
}

function dialog(title,fields,submit){
 const d=document.createElement('dialog'),form=document.createElement('form'),h=document.createElement('h2');h.textContent=title;form.append(h);
 const inputs={};for(const field of fields){const label=document.createElement('label');label.textContent=field.label;
 const input=document.createElement(field.options?'select':'input');input.name=field.key;
 if(field.options)for(const value of field.options){const option=document.createElement('option');option.value=value;option.textContent=value;input.append(option);}
 else{input.type=field.password?'password':'text';input.maxLength=field.password?1024:200;if(field.password){input.minLength=6;input.autocomplete='new-password';}}
 input.value=field.value??'';input.required=!!field.required;inputs[field.key]=input;label.append(input);form.append(label);}
 const error=document.createElement('p');error.className='dialog-error';form.append(error);
 const actions=document.createElement('div');actions.className='dialog-actions';const cancel=document.createElement('button');cancel.type='button';cancel.className='secondary';cancel.textContent='取消';cancel.onclick=()=>d.close();
 const save=document.createElement('button');save.type='submit';save.className='primary';save.textContent='确认';actions.append(cancel,save);form.append(actions);
 form.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await submit(Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value])));d.close();await refresh();message('操作已完成');}catch(e){error.textContent=e.message;}finally{save.disabled=false;}};
 d.addEventListener('close',()=>d.remove());d.append(form);document.body.append(d);d.showModal();
}
function confirmAction(text,action){dialog(text,[],action);}
function accountDialog(item){
 const fields=[{key:'username',label:'账号名称',value:item.name,required:true},{key:'password',label:'新密码（留空不修改，至少6位）',password:true}];
 if(role==='root')fields.push({key:'role',label:'权限等级组',value:item.role,options:['player','admin']});
 dialog('管理账号 · '+item.name,fields,body=>{if(!body.password)delete body.password;return api('users/'+encodeURIComponent(item.name),body,'PATCH');});
}
async function roomDialog(item){try{
 const canTransfer=role==='root'||item.owner===el('actor').textContent;
 const options=canTransfer?await api('rooms/'+item.id+'/account-options'):[];
 const fields=[
 {key:'name',label:'房间名称',value:item.name,required:true},
 {key:'environment',label:'游戏环境（版本和加载器）',value:item.environment||'',required:true},
 {key:'mode',label:'连接策略',value:item.mode||'AUTO',options:['AUTO','RELAY','DIRECT']}];
 if(canTransfer)fields.push({key:'owner',label:'所有者账号',value:item.owner,options:options.map(account=>account.name),required:true});
 dialog('管理共享房间',fields,body=>api('rooms/'+item.id,body,'PATCH'));}catch(e){message(e.message,true);}}
async function membersDialog(item){
 try{const canEdit=role==='root'||item.owner===el('actor').textContent;
 const [members,options]=await Promise.all([api('rooms/'+item.id+'/members'),canEdit?api('rooms/'+item.id+'/account-options'):Promise.resolve([])]);
 dialog('成员 · '+members.map(m=>m.actor+' ('+m.role+')').join('、'),canEdit?[
 {key:'username',label:'成员账号',options:options.map(account=>account.name),required:true},{key:'role',label:'实例权限 / 移除',options:['member','admin','remove']}
 ]:[],body=>canEdit?api('rooms/'+item.id+'/members',body):Promise.resolve());}catch(e){message(e.message,true);}
}
async function recoveryDialog(item){
 try{const [candidates,head]=await Promise.all([api('rooms/'+item.id+'/recoveries'),api('rooms/'+item.id+'/head')]);
 if(!candidates.length){message('此房间暂无待审批恢复候选');return;}
 dialog('审批恢复 · 先确认所有Host已正常保存退出。恢复会新增权威版本，保留当前版本。',[
 {key:'candidate',label:'候选ID（提交人、原始基准）',options:candidates.map(c=>c.id)},
 {key:'confirm',label:'输入“确认恢复”以批准，当前版本 '+(head.version||'无'),required:true}
 ],body=>{if(body.confirm!=='确认恢复')throw new Error('请输入确认恢复');return api('rooms/'+item.id+'/recoveries/'+body.candidate+'/approve',{expected_head:head.version});});
 }catch(e){message(e.message,true);}
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
 if(refreshing||role==="player")return;
 refreshing=true;
 try{
 const [status,rooms,users]=await Promise.all([api("status"),api("rooms"),api("users")]);
 const metricCards=[metric("可用磁盘",gib(status.disk_free),"GiB","容量 "+gib(status.disk_total)+" GiB","▱"),
 metric("可用内存",gib(status.memory_available),"GiB","物理内存 "+gib(status.memory_total)+" GiB","▤"),
 metric("共享房间",status.rooms,"个","持久世界与当前 Host","▦"),metric("软件账号",status.accounts,"个","独立的软件登录身份","◎")];
 const metrics=el('metrics');
 metricCards.forEach((card,index)=>{const old=metrics.children[index];
 if(!old)metrics.append(card);else for(let i=0;i<card.children.length;i++){
 if(old.children[i].innerHTML!==card.children[i].innerHTML)old.children[i].replaceChildren(...card.children[i].childNodes);
 }});
 const diskUsed=status.disk_total?100*(1-status.disk_free/status.disk_total):0;
 el("disk-progress").value=diskUsed;el("disk-label").textContent=diskUsed.toFixed(1)+"% · "+gib(status.disk_total-status.disk_free)+" / "+gib(status.disk_total)+" GiB";
 const memUsed=status.memory_total?100*(1-status.memory_available/status.memory_total):0;el("memory-progress").value=memUsed;
 el("memory-label").textContent=status.memory_total?memUsed.toFixed(1)+"% · "+gib(status.memory_total-status.memory_available)+" / "+gib(status.memory_total)+" GiB":"暂无数据";
 el("cpu-count").textContent=status.cpu_count??"—";el("load-average").textContent=status.load_average?status.load_average[0].toFixed(2):"—";
 el("service-version").textContent=status.version||"—";el("updated").textContent=new Date().toLocaleTimeString();
 el("room-count").textContent=rooms.length+" 个实例";el("account-count").textContent=users.length+" 个账号";
 rows("rooms",rooms,["name","environment","owner","host","state","epoch"]);rows("users",users,["name","role","disabled"]);
 if(!el("view-streams").hidden){
 const sessions=await Promise.all(rooms.filter(r=>r.can_manage&&r.host).map(async r=>{
 const detail=await api("rooms/"+r.id+"/diagnostics");
 return detail.streams.map(s=>({...s,room:r.id,name:r.name,host:r.host,epoch:detail.epoch,
 route:Object.values(s.reports||{}).map(v=>[v.active_path,v.switch_phase].filter(Boolean).join(" · ")).join(" / ")||"等待端点上报"}));
 }));
 const query=el("stream-filter").value.trim().toLowerCase();
 rows("streams",sessions.flat().filter(s=>[s.name,s.host,s.player,s.route].join(" ").toLowerCase().includes(query)),["name","host","player","epoch","channel","route"]);
 }
 refreshFailures=0;
 }finally{refreshing=false;}
}
function showView(name){
 document.querySelectorAll(".view").forEach(v=>{v.hidden=v.id!=="view-"+name;});
 document.querySelectorAll("[data-view]").forEach(b=>{const active=b.dataset.view===name;b.classList.toggle("active",active);if(active)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
 if(name==="settings")loadSettings().catch(e=>message(e.message,true));
 el("breadcrumb").textContent=({overview:"服务器概况",instances:"共享房间",streams:"会话流",settings:"面板设置",accounts:"账号管理"})[name];
}
document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
el("toggle-password").addEventListener("click",()=>{const visible=el("password").type==="password";el("password").type=visible?"text":"password";el("toggle-password").textContent=visible?"隐藏":"显示";el("toggle-password").setAttribute("aria-label",visible?"隐藏密码":"显示密码");});
el("login").addEventListener("submit",async e=>{
 e.preventDefault();const button=e.target.querySelector('button[type="submit"]');button.disabled=true;button.textContent="正在连接…";
 try{const result=await api("login",{username:el("username").value,password:el("password").value});token=result.token;role=result.role;el("password").value="";
 panelAccess=(await api("panel/access")).access;
 document.querySelectorAll("[data-view]").forEach(b=>b.hidden=b.dataset.view==="settings"?!panelAccess:role==="player");
 if(!["root","admin"].includes(role)&&!panelAccess){await api("logout",{});token="";throw new Error("该账号没有服务器面板权限");}
 el("admin-option").disabled=role!=="root";await refresh();el("actor").textContent=result.username;el("actor-role").textContent=role==="root"?"Root · 服务器所有者":"Admin · 服务器管理员";
 showView(role==="player"?"settings":"overview");el("workspace").hidden=false;el("login-section").hidden=true;message("登录成功");}
 catch(error){if(token){try{await api("logout",{});}catch{}token="";}message(error.message,true);}
 finally{button.disabled=false;button.textContent="登录控制中心 →";}
});

el("logout").addEventListener("click",async()=>{try{await api("logout",{});}catch{}finally{token="";location.reload();}});
el("create-user").addEventListener("submit",async e=>{
 e.preventDefault();const button=e.target.querySelector("button");button.disabled=true;
 try{await api("users",{username:el("new-name").value,password:el("new-password").value,role:el("new-role").value});el("new-password").value="";el("new-name").value="";await refresh();message("账号已创建，请通过安全渠道告知使用者。");}
 catch(error){message(error.message,true);}finally{button.disabled=false;}
});

async function connectionsDialog(item){
 const d=document.createElement('dialog'),title=document.createElement('h2'),body=document.createElement('pre'),close=document.createElement('button');
 title.textContent='连接状态 · '+item.name;close.textContent='关闭';close.onclick=()=>d.close();
 body.style.whiteSpace='pre-wrap';d.append(title,body,close);document.body.append(d);d.showModal();
 let busy=false;
 async function update(){if(busy||!d.open)return;busy=true;
 try{const state=await api('rooms/'+item.id+'/diagnostics');
 body.textContent='状态 '+state.state+' · Host '+(state.host||'无')+' · 代次 '+state.epoch+'\n'+
 (state.streams.length?state.streams.map(stream=>stream.player+' · '+stream.channel+' · '+stream.mode+'\nHost 中继接入 '+stream.host_attached+' · Player 中继接入 '+stream.player_attached+'\n'+stream.path).join('\n\n'):'当前没有连接流');
 }catch(e){body.textContent=e.message;}finally{busy=false;}}
 const timer=setInterval(update,5000);d.addEventListener('close',()=>{clearInterval(timer);d.remove();});await update();
}
async function autoRefresh(){
 if(token&&!document.hidden){try{await refresh();}catch(e){refreshFailures=Math.min(refreshFailures+1,4);el('updated').textContent='连接中断，自动重试';}}
 setTimeout(autoRefresh,(document.hidden?30000:5000)*2**refreshFailures);
}
setTimeout(autoRefresh,5000);

;(() => {
  const control = document.getElementById("appearance");
  const system = matchMedia("(prefers-color-scheme: dark)");
  const modes = ["system","light","dark"];
  const labels = {system:"跟随系统",light:"亮色",dark:"暗色"};
  let mode = localStorage.getItem("appearance") || "system";
  function paint() {
    document.documentElement.dataset.theme = mode === "system" ? (system.matches ? "dark" : "light") : mode;
    control.textContent = labels[mode];
  }
  control.addEventListener("click", () => {
    mode = modes[(modes.indexOf(mode)+1)%3];
    localStorage.setItem("appearance",mode);
    paint();
  });
  system.addEventListener("change",paint);
  paint();
})();

const entryKeys=["address","domain","port","path","icp"];
let grants={};
async function loadSettings(){
 const info=await api("panel/settings");
 const form=el("panel-entry");
 for(const key of entryKeys)el("panel-"+key).value=(info.pending||info.current)[key];
 for(const input of form.elements)input.disabled=panelAccess!=="edit"||Boolean(info.pending);
 el("icp-footer").textContent=info.current.icp;
 const pending=el("panel-pending");
 pending.replaceChildren();
 if(info.pending){
  const target=info.pending;
  const a=document.createElement("a");a.href="https://"+target.domain+":"+target.port+"/"+target.path+"/";
  a.textContent="打开新入口并登录确认";a.target="_blank";a.rel="noopener";
  pending.append(a,document.createTextNode(" · "+new Date(info.expires*1000).toLocaleTimeString()+" 前有效"));
 }
 el("confirm-entry").hidden=!info.pending||panelAccess!=="edit";
 el("panel-grants").hidden=role!=="root";
 if(role==="root"){
  grants=Object.fromEntries(info.grants.map(g=>[g.actor,g.access_level]));
  const users=await api("users"),select=el("grant-account"),selected=select.value;
  select.replaceChildren(...users.filter(u=>u.role!=="root"&&!u.disabled).map(u=>new Option(u.name,u.name)));
  if(Array.from(select.options).some(o=>o.value===selected))select.value=selected;
  el("grant-level").value=grants[select.value]||"none";
 }
}
el("grant-account").onchange=e=>el("grant-level").value=grants[e.target.value]||"none";
el("panel-entry").onsubmit=async e=>{
 e.preventDefault();const body=Object.fromEntries(entryKeys.map(k=>[k,el("panel-"+k).value.trim()]));
 body.port=Number(body.port);
 try{await api("panel/settings",body);await loadSettings();}catch(error){message(error.message,true);}
};
el("confirm-entry").onclick=async()=>{
 try{await api("panel/confirm",{});await loadSettings();message("面板入口已确认");}catch(error){message(error.message,true);}
};
el("panel-grants").onsubmit=async e=>{
 e.preventDefault();try{await api("panel/grants/"+encodeURIComponent(el("grant-account").value),{access:el("grant-level").value},"PUT");await loadSettings();message("授权已保存");}catch(error){message(error.message,true);}
};

document.addEventListener("focusin",event=>{
 const select=event.target;
 if(!(select instanceof HTMLSelectElement)||select.options.length<6||select.dataset.searchable)return;
 select.dataset.searchable="1";
 const filter=document.createElement("input");
 filter.type="search";filter.placeholder="筛选选项";filter.autocomplete="off";
 filter.setAttribute("aria-label","筛选"+(select.labels[0]?.textContent||"选项"));
 filter.addEventListener("input",()=>{
  const query=filter.value.trim().toLowerCase();
  for(const option of select.options)option.hidden=!option.text.toLowerCase().includes(query);
 });
 select.before(filter);
});

function manageMods(item){
 const modal=document.createElement("dialog"),form=document.createElement("form"),list=document.createElement("div");
 const title=document.createElement("h2");title.textContent="房间必需模组";form.append(title,list);
 const choices=[...Object.keys(item.required_mods),...(item.optional_mods||[])].sort().map(key=>{
  const label=document.createElement("label"),input=document.createElement("input");
  input.type="checkbox";input.value=key;input.checked=Object.hasOwn(item.required_mods,key);
  label.append(input,document.createTextNode(key));list.append(label);return input;
 });
 const save=document.createElement("button");save.textContent="保存";save.className="primary";form.append(save);
 form.onsubmit=async e=>{e.preventDefault();try{
  await api("rooms/"+item.id+"/required-mods",{required:choices.filter(c=>c.checked).map(c=>c.value)},"PUT");
  modal.close();await refresh();
 }catch(error){message(error.message,true);}};
 modal.append(form);document.body.append(modal);modal.addEventListener("close",()=>modal.remove());modal.showModal();
}
