/* Browser push notifications for Race Entry Radar. No tracking or caching. */
self.addEventListener("push",event=>{
  let payload={};
  try{payload=event.data?event.data.json():{}}catch{}
  const title=typeof payload.title==="string"?payload.title.slice(0,110):"Race Entry Radar";
  const body=typeof payload.body==="string"?payload.body.slice(0,220):"A race entry update is available.";
  const url=typeof payload.url==="string"&&/^https:\/\//.test(payload.url)?
    payload.url:new URL("./",self.registration.scope).href;
  event.waitUntil(self.registration.showNotification(title,{
    body,tag:String(payload.tag||"race-entry-alert").slice(0,100),
    renotify:false,data:{url}
  }));
});
self.addEventListener("notificationclick",event=>{
  event.notification.close();
  const destination=event.notification.data?.url||new URL("./",self.registration.scope).href;
  event.waitUntil(self.clients.openWindow(destination));
});
