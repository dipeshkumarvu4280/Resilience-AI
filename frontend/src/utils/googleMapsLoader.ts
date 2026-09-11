import { importLibrary, setOptions } from '@googlemaps/js-api-loader';

let loadPromise: Promise<typeof google> | null = null;

export const getGoogleMapsApiKey = (): string => {
  return import.meta.env.VITE_GOOGLE_MAPS_API_KEY || 'AIzaSyBRjMb3WnJHWSmPS6aV3H9KqiL--AWrviY';
};

export const hasGoogleMapsApiKey = (): boolean => {
  const key = getGoogleMapsApiKey();
  return typeof key === 'string' && key.trim().length > 0;
};

export const loadGoogleMaps = async (): Promise<typeof google> => {
  if (typeof window !== 'undefined' && (window as any).google?.maps?.Map) {
    return (window as any).google;
  }

  if (loadPromise) {
    return loadPromise;
  }

  const apiKey = getGoogleMapsApiKey();
  if (!apiKey) {
    throw new Error('Google Maps API key is not configured.');
  }

  try {
    setOptions({
      key: apiKey,
      v: 'weekly',
    });
  } catch {
    // Options already initialized in loader instance
  }

    loadPromise = (async () => {
    try {
      await Promise.all([
        importLibrary('maps'),
        importLibrary('marker'),
        importLibrary('routes').catch(() => null),
        importLibrary('geometry').catch(() => null),
      ]);
      if (typeof window === 'undefined' || !(window as any).google?.maps?.Map) {
        throw new Error('Google Maps JavaScript API could not be initialized.');
      }
      return (window as any).google;
    } catch (err: any) {
      loadPromise = null;
      throw err;
    }
  })();

  return loadPromise;
};

