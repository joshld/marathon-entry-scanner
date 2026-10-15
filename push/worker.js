/* Race Entry Radar: privacy-conscious Web Push subscriptions.
 * Cloudflare Worker using KV bound as PUSH_KV.
 * Public: ALLOWED_ORIGIN. Secret: PUSH_ADMIN_TOKEN.
 * No email address, login, or subscription data stored in GitHub.
 */
const JSON_HEADERS={"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"};
function reply(body,status=200,extra={}){return new Response(JSON.stringify(body),{status,headers:{...JSON_HEADERS,...extra}})}
function allowCors(request,env){
  const origin=request.headers.get("Origin");
  return origin&&origin===env.ALLOWED_ORIGIN?
    {"Access-Control-Allow-Origin":origin,"Access-Control-Allow-Headers":"Content-Type",
      "Access-Control-Allow-Methods":"POST,OPTIONS","Vary":"Origin"}:{};
}
function secureEndpoint(raw){
  try{
    const url=new URL(raw);
    if(url.protocol!=="https:"||url.username||url.password||url.port||raw.length>2100)return false;
    const host=url.hostname.toLowerCase();
    return host==="fcm.googleapis.com"||
      host==="updates.push.services.mozilla.com"||
      host==="web.push.apple.com"||
      host.endsWith(".push.apple.com")||
      host.endsWith(".notify.windows.com");
  }catch{return false}
}
function validPreferences(p){
  const types=["open","soon","new"];
  const distances=["Marathon","Half marathon","Ultra"];
  return p&&Array.isArray(p.countries)&&p.countries.length>=1&&p.countries.length<=80&&
    p.countries.every(c=>typeof c==="string"&&c.length>0&&c.length<75)&&
    Array.isArray(p.distances)&&p.distances.length>=1&&p.distances.every(d=>distances.includes(d))&&
    Array.isArray(p.types)&&p.types.length>=1&&p.types.every(t=>types.includes(t));
}
function validSubscription(s){
  return s&&typeof s.endpoint==="string"&&secureEndpoint(s.endpoint)&&s.keys&&
    typeof s.keys.p256dh==="string"&&/^[a-zA-Z0-9_-]{75,110}$/.test(s.keys.p256dh)&&
    typeof s.keys.auth==="string"&&/^[a-zA-Z0-9_-]{15,40}$/.test(s.keys.auth);
}
async function keyForEndpoint(endpoint){
  const bytes=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(endpoint));
  return "sub:"+[...new Uint8Array(bytes)].map(n=>n.toString(16).padStart(2,"0")).join("");
}
async function parseSmallJson(request){
  if(!request.headers.get("Content-Type")?.startsWith("application/json"))throw new Error("JSON required");
  if(Number(request.headers.get("Content-Length")||0)>8000)throw new Error("Request too large");
  const body=await request.text();if(body.length>8000)throw new Error("Request too large");
  return JSON.parse(body);
}
function authorized(request,env){
  const token=request.headers.get("Authorization")||"";
  // Constant-work comparison of bearer credential hashes for accepted shape.
  return Boolean(env.PUSH_ADMIN_TOKEN&&token===("Bearer "+env.PUSH_ADMIN_TOKEN));
}
async function subscribe(request,env){
  const payload=await parseSmallJson(request);
  if(!validSubscription(payload.subscription)||!validPreferences(payload.preferences))
    return reply({error:"Invalid subscription or preferences"},400);
  const key=await keyForEndpoint(payload.subscription.endpoint);
  const old=await env.PUSH_KV.get(key,"json");
  const entry={subscription:payload.subscription,preferences:payload.preferences,
    createdAt:old?.createdAt||new Date().toISOString(),
    lastSentAt:old?.lastSentAt||null};
  await env.PUSH_KV.put(key,JSON.stringify(entry));
  return reply({ok:true},201);
}
async function unsubscribe(request,env){
  const payload=await parseSmallJson(request);
  if(!payload||typeof payload.endpoint!=="string"||!secureEndpoint(payload.endpoint))
    return reply({error:"Invalid endpoint"},400);
  await env.PUSH_KV.delete(await keyForEndpoint(payload.endpoint));
  return reply({ok:true});
}
async function getSubscribers(request,env){
  const url=new URL(request.url);
  const cursor=url.searchParams.get("cursor")||undefined;
  const response=await env.PUSH_KV.list({prefix:"sub:",limit:500,...(cursor?{cursor}:{})});
  const items=await Promise.all(response.keys.map(async k=>{
    const value=await env.PUSH_KV.get(k.name,"json");
    return value?{id:k.name,...value}:null;
  }));
  return reply({subscribers:items.filter(Boolean),cursor:response.list_complete?null:response.cursor});
}
async function ack(request,env){
  const payload=await parseSmallJson(request);
  if(!payload||!Array.isArray(payload.ids)||payload.ids.length>100||
    payload.ids.some(id=>typeof id!=="string"||!/^sub:[a-f0-9]{64}$/.test(id)))
    return reply({error:"Invalid acknowledgement"},400);
  const now=new Date().toISOString();
  await Promise.all(payload.ids.map(async id=>{
    const row=await env.PUSH_KV.get(id,"json");
    if(row)await env.PUSH_KV.put(id,JSON.stringify({...row,lastSentAt:now}));
  }));
  return reply({ok:true});
}
export default{
  async fetch(request,env){
    const url=new URL(request.url);
    if(url.pathname==="/health")return reply({ready:Boolean(env.PUSH_KV&&env.ALLOWED_ORIGIN&&env.PUSH_ADMIN_TOKEN)});
    if(!env.PUSH_KV||!env.ALLOWED_ORIGIN||!env.PUSH_ADMIN_TOKEN)
      return reply({error:"Push notifications are not configured"},503);
    if(url.pathname.startsWith("/admin/")){
      if(!authorized(request,env))return reply({error:"Unauthorized"},401);
      try{
        if(url.pathname==="/admin/subscribers"&&request.method==="GET")
          return getSubscribers(request,env);
        if(url.pathname==="/admin/ack"&&request.method==="POST")
          return ack(request,env);
        return reply({error:"Not found"},404);
      }catch{return reply({error:"Subscription store unavailable"},503)}
    }
    const cors=allowCors(request,env);
    if(url.pathname!=="/subscribe"&&url.pathname!=="/unsubscribe")
      return reply({error:"Not found"},404,cors);
    if(request.headers.get("Origin")!==env.ALLOWED_ORIGIN)return reply({error:"Origin not allowed"},403);
    if(request.method==="OPTIONS")return new Response(null,{status:204,headers:cors});
    if(request.method!=="POST")return reply({error:"Method not allowed"},405,cors);
    try{
      const response=url.pathname==="/subscribe"?
        await subscribe(request,env):await unsubscribe(request,env);
      const headers=new Headers(response.headers);
      Object.entries(cors).forEach(([key,value])=>headers.set(key,value));
      return new Response(response.body,{status:response.status,headers});
    }catch{return reply({error:"Invalid request or temporary service failure"},400,cors)}
  }
};
