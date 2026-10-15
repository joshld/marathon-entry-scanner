/* Race Entry Radar – public subscription endpoint.
 * Deploy separately as a Cloudflare Worker; NEVER put a Brevo key in Pages JS.
 * Environment: BREVO_API_KEY, BREVO_LIST_ID, BREVO_DOI_TEMPLATE_ID,
 * DOI_REDIRECT_URL, ALLOWED_ORIGIN, TURNSTILE_SECRET, UNSUBSCRIBE_SECRET.
 */
const BREVO = "https://api.brevo.com/v3";
const options = "GET, POST, OPTIONS";
const validFrequencies = new Set(["daily", "weekly"]);
const validTypes = new Set(["open", "soon", "new"]);
const validDistances = new Set(["M", "H", "U"]);
const json = (value, status=200, headers={}) => new Response(JSON.stringify(value),{
  status, headers:{"Content-Type":"application/json; charset=utf-8", "Cache-Control":"no-store", ...headers}
});
function cors(env, request) {
  const origin=request.headers.get("Origin")||"";
  return origin===env.ALLOWED_ORIGIN?{"Access-Control-Allow-Origin":origin,"Vary":"Origin",
    "Access-Control-Allow-Methods":options,"Access-Control-Allow-Headers":"Content-Type"}:{};
}
function validPrefs(p) {
  if(!p||!validFrequencies.has(p.f))return false;
  if(!Array.isArray(p.d)||!p.d.length||p.d.some(v=>!validDistances.has(v)))return false;
  if(!Array.isArray(p.a)||!p.a.length||p.a.some(v=>!validTypes.has(v)))return false;
  if(p.c!=="*"&&(!Array.isArray(p.c)||!p.c.length||p.c.length>100||
    p.c.some(v=>typeof v!=="string"||!/^[A-Z]{2}$/.test(v))))return false;
  return JSON.stringify(p).length<=450;
}
function b64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
}
function unbase64(s) {
  if(!/^[A-Za-z0-9_-]+$/.test(s)||s.length>350)throw Error("Invalid token");
  const bytes=Uint8Array.from(atob(s.replace(/-/g,"+").replace(/_/g,"/")),c=>c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}
async function digest(email,secret){
  const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  const raw=await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(email));
  return [...new Uint8Array(raw)].map(v=>v.toString(16).padStart(2,"0")).join("");
}
function constantTimeHex(a,b){
  if(!/^[a-f0-9]{64}$/.test(a)||!/^[a-f0-9]{64}$/.test(b))return false;
  let diff=0;for(let i=0;i<64;i++)diff|=a.charCodeAt(i)^b.charCodeAt(i);
  return diff===0;
}
async function brevo(path,method,body,env){
  const response=await fetch(BREVO+path,{method,headers:{"api-key":env.BREVO_API_KEY,
    "accept":"application/json",...(body?{"Content-Type":"application/json"}:{})},
    ...(body?{body:JSON.stringify(body)}:{})});
  if(!response.ok)throw Error("Brevo service error "+response.status);
  return response;
}
async function verifyTurnstile(token,request,env){
  if(typeof token!=="string"||!token||token.length>2100)return false;
  const form=new FormData();form.set("secret",env.TURNSTILE_SECRET);
  form.set("response",token);
  const ip=request.headers.get("CF-Connecting-IP");if(ip)form.set("remoteip",ip);
  const result=await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {method:"POST",body:form});
  if(!result.ok)return false;
  return (await result.json()).success===true;
}
function health(env){
  const ready=["BREVO_API_KEY","BREVO_LIST_ID","BREVO_DOI_TEMPLATE_ID","DOI_REDIRECT_URL",
    "ALLOWED_ORIGIN","TURNSTILE_SECRET","UNSUBSCRIBE_SECRET"].every(key=>Boolean(env[key]));
  return json({ready},ready?200:503);
}
async function subscribe(request,env){
  if(request.headers.get("Origin")!==env.ALLOWED_ORIGIN)return json({error:"Origin not allowed"},403);
  if(!request.headers.get("Content-Type")?.startsWith("application/json"))return json({error:"JSON required"},415);
  const size=Number(request.headers.get("Content-Length")||0);
  if(size>4096)return json({error:"Request too large"},413);
  let body;
  try{body=await request.json()}catch{return json({error:"Invalid request"},400)}
  const email=typeof body.email==="string"?body.email.trim().toLowerCase():"";
  if(!/^[^\s@]{1,64}@[^\s@]{1,250}\.[^\s@]{2,}$/.test(email)||email.length>254||
     !validPrefs(body.preferences)||body.consent!==true)
    return json({error:"Valid email, preferences and consent are required"},400);
  if(!(await verifyTurnstile(body.turnstileToken,request,env)))
    return json({error:"Please complete the verification challenge"},400);
  try{
    await brevo("/contacts/doubleOptinConfirmation","POST",{
      email,includeListIds:[Number(env.BREVO_LIST_ID)],
      redirectionUrl:env.DOI_REDIRECT_URL,
      templateId:Number(env.BREVO_DOI_TEMPLATE_ID),
      attributes:{"RACE_PREFS":JSON.stringify(body.preferences)},
      contactPixelTrackingConsent:false
    },env);
  }catch(e){
    // Don't disclose whether an address is already subscribed.
    if(/Brevo service error 4\d\d/.test(e.message))
      return json({message:"If eligible, you will receive an email confirmation shortly."},202);
    return json({error:"Email service unavailable. Please try later."},502);
  }
  return json({message:"Check your inbox to confirm your subscription."},202);
}
async function unsubscribe(request,url,env){
  const e=url.searchParams.get("e")||"",s=url.searchParams.get("s")||"";
  let email;
  try{email=unbase64(e).toLowerCase()}catch{return new Response("Invalid unsubscribe link",{status:400})}
  if(email.length>254||!constantTimeHex(s,await digest(email,env.UNSUBSCRIBE_SECRET)))
    return new Response("Invalid unsubscribe link",{status:400});
  if(request.method==="GET"){
    // GET must not unsubscribe: email scanners prefetch links.
    return new Response('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'+
      '<title>Unsubscribe · Race Entry Radar</title><body style="font:16px system-ui;max-width:480px;margin:60px auto;padding:0 16px">'+
      '<h1>Stop race-entry alerts?</h1><p>Confirm to stop receiving Race Entry Radar emails.</p>'+
      '<form method="post"><button type="submit" style="padding:12px 20px">Unsubscribe</button></form></body></html>',
      {headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store","Referrer-Policy":"no-referrer"}});
  }
  if(request.method!=="POST")return new Response("Method not allowed",{status:405});
  try{
    await brevo("/contacts/"+encodeURIComponent(email),"PUT",
      {unlinkListIds:[Number(env.BREVO_LIST_ID)]},env);
  }catch(e){return new Response("Could not unsubscribe. Please try again later.",{status:502})}
  return new Response("You have been unsubscribed from Race Entry Radar alerts.",{
    headers:{"Content-Type":"text/plain; charset=utf-8","Cache-Control":"no-store"}});
}
export default {
  async fetch(request,env){
    const url=new URL(request.url);
    const ready=health(env);
    if(url.pathname==="/health")return ready;
    if(ready.status!==200)return json({error:"Subscriptions are not configured"},503,cors(env,request));
    if(url.pathname==="/unsubscribe"&&(request.method==="GET"||request.method==="POST"))
      return unsubscribe(request,url,env);
    if(url.pathname!=="/subscribe")return json({error:"Not found"},404,cors(env,request));
    if(request.method==="OPTIONS")return new Response(null,{status:204,headers:cors(env,request)});
    if(request.method!=="POST")return json({error:"Method not allowed"},405,cors(env,request));
    try{
      const result=await subscribe(request,env);
      const headers=new Headers(result.headers);for(const [k,v] of Object.entries(cors(env,request)))headers.set(k,v);
      return new Response(result.body,{status:result.status,headers});
    }catch{return json({error:"Subscription service unavailable"},503,cors(env,request))}
  }
};
