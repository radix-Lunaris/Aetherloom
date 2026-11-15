"use strict";
let token="", role="";
const el=id=>document.getElementById(id);
function message(text){el("message").textContent=text;}
async function api(path,body){
 const headers={"Content-Type":"application/json"};if(token)headers.Authorization="Bearer "+token;
 const response=await fetch(new URL("api/"+path,location.href),{method:body?"POST":"GET",headers,body:body?JSON.stringify(body):undefined,cache:"no-store",credentials:"omit"});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"请求失败");return data;
}
function rows(id,data,keys){const target=el(id);target.replaceChildren();if(!data.length){const row=document.createElement("tr"),cell=document.createElement("td");cell.colSpan=keys.length;cell.textContent="暂无记录";row.append(cell);target.append(row);return;}for(const item of data){const row=document.createElement("tr");for(const key of keys){const cell=document.createElement("td");cell.textContent=String(item[key]??"—");row.append(cell);}target.append(row);}}
function size(n){return n==null?"—":(n/1024**3).toFixed(2)+" GiB";}
async function refresh(){const [status,rooms,users]=await Promise.all([api("status"),api("rooms"),api("users")]);const entries=[["磁盘剩余",size(status.disk_free)],["磁盘容量",size(status.disk_total)],["可用内存",size(status.memory_available)],["CPU 核心",status.cpu_count],["实例数量",status.rooms],["账号数量",status.accounts],["系统负载",status.load_average?status.load_average[0].toFixed(2):"—"]];el("metrics").replaceChildren();for(const [label,value]of entries){const card=document.createElement("div");card.className="metric";card.textContent=label;const strong=document.createElement("strong");strong.textContent=String(value);card.append(strong);el("metrics").append(card);}rows("rooms",rooms,["id","owner","host","state","epoch"]);rows("users",users,["name","role"]);message("更新于 "+new Date().toLocaleString());}
el("login").addEventListener("submit",async e=>{e.preventDefault();const button=e.target.querySelector("button");button.disabled=true;try{const result=await api("login",{username:el("username").value,password:el("password").value});token=result.token;role=result.role;el("password").value="";if(!["root","admin"].includes(role)){await api("logout",{});token="";throw new Error("该账号没有服务器面板权限");}el("admin-option").disabled=role!=="root";await refresh();el("workspace").hidden=false;el("login-section").hidden=true;}catch(error){token="";message(error.message);}finally{button.disabled=false;}});
el("refresh").addEventListener("click",()=>refresh().catch(e=>message(e.message)));
el("logout").addEventListener("click",async()=>{try{await api("logout",{});}finally{token="";location.reload();}});
el("create-user").addEventListener("submit",async e=>{e.preventDefault();const button=e.target.querySelector("button");button.disabled=true;try{await api("users",{username:el("new-name").value,password:el("new-password").value,role:el("new-role").value});el("new-password").value="";el("new-name").value="";await refresh();message("账号已创建，请通过安全渠道告知使用者。");}catch(error){message(error.message);}finally{button.disabled=false;}});

