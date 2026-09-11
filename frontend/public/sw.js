/* eslint-disable no-restricted-globals */
// RESILIENCE Emergency Response Platform — Service Worker (RFC 8291 / 8292 Push Notification Receiver)

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  if (!event.data) {
    return;
  }

  let payload = {
    title: '🚨 RESILIENCE Emergency Alert',
    body: 'An urgent safety update is available for your location.',
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    url: '/',
    data: {},
  };

  try {
    const rawData = event.data.json();
    payload = {
      ...payload,
      ...rawData,
    };
  } catch (err) {
    payload.body = event.data.text() || payload.body;
  }

  const options = {
    body: payload.body,
    icon: payload.icon || '/favicon.svg',
    badge: payload.badge || '/favicon.svg',
    vibrate: [200, 100, 200, 100, 300],
    tag: payload.tag || 'emergency-alert',
    renotify: true,
    requireInteraction: true,
    data: {
      url: payload.url || (payload.data && payload.data.url) || '/',
      ...payload.data,
    },
  };

  event.waitUntil(
    self.registration.showNotification(payload.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // If a window is already open with the target URL, focus it
      for (const client of clientList) {
        if (client.url.includes(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open a new window
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
