/**
 * Thin promise wrapper around the browser Geolocation API.
 *
 * Kept in one place so registration, Settings and the check-in screen all ask
 * for a fix the same way, and so the "not supported / denied / timed out"
 * cases read the same everywhere.
 */
export interface GeoFix {
  latitude: number;
  longitude: number;
  accuracy: number;
}

export function geolocationSupported(): boolean {
  return typeof navigator !== "undefined" && "geolocation" in navigator;
}

export function getCurrentPosition(
  options: PositionOptions = { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
): Promise<GeoFix> {
  return new Promise((resolve, reject) => {
    if (!geolocationSupported()) {
      reject(new Error("This device or browser does not support location."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      (error) => {
        const messages: Record<number, string> = {
          1: "Location permission was denied. Enable it for this site and try again.",
          2: "We could not get a location fix right now. Try again in a moment.",
          3: "Getting your location timed out. Move somewhere with a clearer view and try again.",
        };
        reject(new Error(messages[error.code] ?? "We could not get your location."));
      },
      options,
    );
  });
}
