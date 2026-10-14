// Minimaler Service Worker – nur für Benachrichtigungen ("Sie sind dran!")
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const match = list.find((c) => c.url === url);
      return match ? match.focus() : self.clients.openWindow(url);
    })
  );
});
