import { getVapidPublicKey, subscribeWebPush, unsubscribeWebPush, triggerTestWebPush } from '../services/api';
import type { WebPushState } from '../types';

/**
 * Converts a URL-safe base64 string to a Uint8Array required for PushManager applicationServerKey.
 */
export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Checks if current execution environment is a secure context (HTTPS, localhost, 127.0.0.1).
 * Insecure HTTP origins on mobile browsers cannot register Service Workers or PushSubscriptions.
 */
export function isSecureContextEnvironment(): boolean {
  if (typeof window === 'undefined') return false;
  if (typeof window.isSecureContext === 'boolean') {
    return window.isSecureContext;
  }
  return (
    window.location.protocol === 'https:' ||
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
  );
}

/**
 * Checks if Service Workers and Push Notifications are supported by current browser.
 */
export function isWebPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/**
 * Evaluates the comprehensive 8-state Web Push machine for genuine emergency alert status.
 * Never claims ACTIVE unless permission is granted, PushSubscription exists, and backend persistence is confirmed.
 */
export async function getComprehensivePushState(): Promise<WebPushState> {
  if (typeof window === 'undefined') {
    return 'NOT_SUPPORTED';
  }

  if (!isSecureContextEnvironment()) {
    return 'INSECURE_CONTEXT';
  }

  if (!isWebPushSupported()) {
    return 'NOT_SUPPORTED';
  }

  const permission = Notification.permission;
  if (permission === 'denied') {
    return 'PERMISSION_DENIED';
  }
  if (permission === 'default') {
    return 'PERMISSION_NOT_REQUESTED';
  }

  // Permission is 'granted'
  try {
    let registration: ServiceWorkerRegistration;
    try {
      registration = await navigator.serviceWorker.ready;
    } catch {
      return 'SW_REGISTRATION_FAILED';
    }

    if (!registration || !registration.pushManager) {
      return 'SW_REGISTRATION_FAILED';
    }

    let subscription: PushSubscription | null = null;
    try {
      subscription = await registration.pushManager.getSubscription();
    } catch {
      return 'SUBSCRIPTION_FAILED';
    }

    if (!subscription) {
      return 'PERMISSION_GRANTED_NO_SUBSCRIPTION';
    }

    // Subscription exists in browser PushManager
    const lastSubId = localStorage.getItem('resilience_push_sub_id');
    if (lastSubId) {
      return 'ACTIVE';
    }
    return 'SUBSCRIPTION_NOT_PERSISTED';
  } catch {
    return 'SUBSCRIPTION_FAILED';
  }
}

/**
 * Registers the Service Worker, acquires PushSubscription with correct VAPID key,
 * and persists the subscription with the backend.
 */
export async function registerServiceWorkerAndSubscribe(
  reportId?: string,
  sessionId?: string
): Promise<{ success: boolean; subscriptionId?: string; error?: string }> {
  if (!isSecureContextEnvironment()) {
    return {
      success: false,
      error: 'Browser notifications require HTTPS on this device.',
    };
  }

  if (!isWebPushSupported()) {
    return {
      success: false,
      error: 'Web Push notifications are not supported by this mobile browser or device configuration.',
    };
  }

  try {
    // 1. Request notification permission upon explicit user interaction
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      return { success: false, error: `Notification permission ${permission}.` };
    }

    // 2. Register Service Worker
    let registration: ServiceWorkerRegistration;
    try {
      registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      await navigator.serviceWorker.ready;
    } catch (swErr: any) {
      return {
        success: false,
        error: `Service Worker registration failed: ${swErr.message || swErr}`,
      };
    }

    // 3. Fetch backend VAPID public key
    const vapidRes = await getVapidPublicKey();
    if (!vapidRes.success || !vapidRes.vapid_public_key) {
      return { success: false, error: 'Failed to retrieve server VAPID public key.' };
    }

    const applicationServerKey = urlBase64ToUint8Array(vapidRes.vapid_public_key);

    // 4. Subscribe with PushManager
    let subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      // Check if applicationServerKey matches
      const rawKey = subscription.options?.applicationServerKey;
      let isMatching = false;
      if (rawKey) {
        const rawBytes = new Uint8Array(rawKey);
        if (rawBytes.length === applicationServerKey.length) {
          isMatching = rawBytes.every((b, i) => b === applicationServerKey[i]);
        }
      }
      if (!isMatching) {
        console.info('[WebPush] Existing push subscription uses outdated key. Refreshing...');
        try {
          await subscription.unsubscribe();
        } catch (unsubErr) {
          console.warn('[WebPush] Error unsubscribing previous subscription:', unsubErr);
        }
        subscription = null;
      }
    }

    if (!subscription) {
      try {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey as BufferSource,
        });
      } catch (subErr: any) {
        return {
          success: false,
          error: `PushManager subscription failed: ${subErr.message || subErr}`,
        };
      }
    }

    const subJson = subscription.toJSON();
    if (!subJson.endpoint || !subJson.keys?.p256dh || !subJson.keys?.auth) {
      return { success: false, error: 'Invalid subscription object generated by browser.' };
    }

    // 5. Send subscription to backend
    try {
      const regRes = await subscribeWebPush({
        endpoint: subJson.endpoint,
        keys: {
          p256dh: subJson.keys.p256dh,
          auth: subJson.keys.auth,
        },
        user_agent: navigator.userAgent,
        report_id: reportId,
        session_id: sessionId,
      });

      if (regRes.success && regRes.subscription_id) {
        localStorage.setItem('resilience_push_sub_id', regRes.subscription_id);
        localStorage.setItem('resilience_push_endpoint', subJson.endpoint);
        return {
          success: true,
          subscriptionId: regRes.subscription_id,
        };
      } else {
        localStorage.removeItem('resilience_push_sub_id');
        return {
          success: false,
          error: regRes.message || 'Subscription was rejected by backend persistence.',
        };
      }
    } catch (backendErr: any) {
      localStorage.removeItem('resilience_push_sub_id');
      return {
        success: false,
        error: backendErr?.response?.data?.detail || backendErr.message || 'Failed to persist subscription on server.',
      };
    }
  } catch (err: any) {
    return {
      success: false,
      error: err.message || 'Failed to initialize Web Push subscription.',
    };
  }
}

/**
 * Unsubscribes current browser session from Web Push notifications.
 */
export async function unsubscribeCurrentWebPush(): Promise<boolean> {
  if (!isWebPushSupported()) return false;

  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      const endpoint = subscription.endpoint;
      await subscription.unsubscribe();
      await unsubscribeWebPush(endpoint);
      localStorage.removeItem('resilience_push_sub_id');
      localStorage.removeItem('resilience_push_endpoint');
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * Triggers a test push notification to verify push delivery without dummy records.
 */
export async function sendTestPushNotification(
  reportId?: string
): Promise<{ success: boolean; message: string; sent_count: number }> {
  try {
    const res = await triggerTestWebPush(reportId);
    return res;
  } catch (err: any) {
    return {
      success: false,
      message: err?.response?.data?.detail || err.message || 'Failed to send test push notification.',
      sent_count: 0,
    };
  }
}

/**
 * Checks if current browser already has an active PushSubscription registered with the push service.
 */
export async function checkExistingPushSubscription(): Promise<boolean> {
  if (!isWebPushSupported()) return false;
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return !!subscription;
  } catch {
    return false;
  }
}


