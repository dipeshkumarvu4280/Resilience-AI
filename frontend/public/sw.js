/* eslint-disable no-restricted-globals */
// RESILIENCE Emergency Response Platform — Service Worker (RFC 8291 / 8292 Push Notification Receiver)

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {
    title: '🚨 RESILIENCE Emergency Alert',
    body: 'An urgent safety update is available for your location.',
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    url: '/',
    data: {},
  };

  if (event.data) {
    try {
      const rawData = event.data.json();
      payload = {
        ...payload,
        ...rawData,
      };
    } catch (err) {
      const textVal = event.data.text();
      if (textVal) {
        payload.body = textVal;
      }
    }
  }

  const targetUrl = payload.url || (payload.data && payload.data.url) || '/';
  const notifTitle = payload.title || '🚨 RESILIENCE Emergency Alert';

  const options = {
    body: payload.body || 'Emergency update received.',
    icon: payload.icon || '/favicon.svg',
    badge: payload.badge || '/favicon.svg',
    vibrate: [200, 100, 200, 100, 300],
    tag: payload.tag || `alert-${Date.now()}`,
    renotify: true,
    requireInteraction: true,
    data: {
      url: targetUrl,
      ...(payload.data || {}),
    },
  };

  event.waitUntil(
    self.registration.showNotification(notifTitle, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url && (client.url.includes(targetUrl) || (targetUrl === '/' && client.url.endsWith('/'))) && 'focus' in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
