import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";
import { cn } from "@/lib/utils";

export interface MapMarker {
  latitude: number;
  longitude: number;
  label?: string;
  status?: string;
}

interface LocationMapProps {
  latitude: number | null;
  longitude: number | null;
  /** Extra read-only points, e.g. every staff check-in for the day. */
  markers?: MapMarker[];
  /** Draw the school's attendance radius around the primary point. */
  radiusMeters?: number;
  /** Click (and drag) to move the primary point, firing `onChange`. */
  interactive?: boolean;
  height?: number;
  zoom?: number;
  className?: string;
  onChange?: (latitude: number, longitude: number) => void;
}

const NIGERIA_CENTER: [number, number] = [9.082, 8.6753];
const STATUS_COLOURS: Record<string, string> = {
  at_school: "#16a34a",
  outside: "#dc2626",
  pending_review: "#d97706",
  unverified: "#6b7280",
};

function pinIcon(color: string) {
  return {
    className: "fn-map-pin",
    html: `<span style="display:block;width:18px;height:18px;border-radius:9999px;border:3px solid white;box-shadow:0 1px 4px rgba(0,0,0,.4);background:${color}"></span>`,
    iconSize: [18, 18] as [number, number],
    iconAnchor: [9, 9] as [number, number],
  };
}

/**
 * A small Leaflet map over OpenStreetMap tiles.
 *
 * Leaflet touches `window` at import time, so it is loaded inside the effect
 * (client-only) rather than at module scope — that keeps the component safe to
 * render on the server. The tile layer is the public OSM standard layer; there
 * are no API keys, matching the backend-proxied geocoding choice.
 */
export function LocationMap({
  latitude,
  longitude,
  markers = [],
  radiusMeters,
  interactive = false,
  height = 220,
  zoom = 15,
  className,
  onChange,
}: LocationMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const primaryRef = useRef<import("leaflet").Marker | null>(null);
  const circleRef = useRef<import("leaflet").Circle | null>(null);
  const pointsLayerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const interactiveRef = useRef(interactive);
  interactiveRef.current = interactive;

  // Initialise once.
  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    void (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !containerRef.current) return;
      leafletRef.current = L;

      const hasPoint = latitude != null && longitude != null;
      const map = L.map(container, {
        center: hasPoint ? [latitude, longitude] : NIGERIA_CENTER,
        zoom: hasPoint ? zoom : 6,
        scrollWheelZoom: false,
        attributionControl: true,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      mapRef.current = map;
      pointsLayerRef.current = L.layerGroup().addTo(map);

      map.on("click", (event: import("leaflet").LeafletMouseEvent) => {
        if (!interactiveRef.current) return;
        onChangeRef.current?.(event.latlng.lat, event.latlng.lng);
      });

      if (hasPoint) {
        placePrimary(L, latitude, longitude);
      }
      renderPoints(L, markers);
    })();

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      primaryRef.current = null;
      circleRef.current = null;
      pointsLayerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function placePrimary(
    L: typeof import("leaflet"),
    lat: number,
    lng: number,
  ) {
    const map = mapRef.current;
    if (!map) return;
    const icon = L.divIcon(pinIcon(interactiveRef.current ? "#2563eb" : "#16a34a"));
    if (primaryRef.current) {
      primaryRef.current.setLatLng([lat, lng]);
    } else {
      const marker = L.marker([lat, lng], {
        icon,
        draggable: interactiveRef.current,
      }).addTo(map);
      marker.on("dragend", () => {
        const pos = marker.getLatLng();
        onChangeRef.current?.(pos.lat, pos.lng);
      });
      primaryRef.current = marker;
    }
  }

  function renderPoints(L: typeof import("leaflet"), points: MapMarker[]) {
    const layer = pointsLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    for (const point of points) {
      const color = STATUS_COLOURS[point.status ?? ""] ?? "#2563eb";
      const dot = L.circleMarker([point.latitude, point.longitude], {
        radius: 7,
        color: "white",
        weight: 2,
        fillColor: color,
        fillOpacity: 1,
      });
      if (point.label) dot.bindTooltip(point.label, { direction: "top" });
      dot.addTo(layer);
    }
  }

  // Keep the primary marker, circle and view in step with the props.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map) return;
    const hasPoint = latitude != null && longitude != null;

    if (hasPoint) {
      placePrimary(L, latitude, longitude);
      if (circleRef.current) {
        circleRef.current.setLatLng([latitude, longitude]);
        circleRef.current.setRadius(radiusMeters ?? 150);
      } else if (radiusMeters != null) {
        circleRef.current = L.circle([latitude, longitude], {
          radius: radiusMeters,
          color: "#2563eb",
          weight: 1,
          fillColor: "#2563eb",
          fillOpacity: 0.08,
        }).addTo(map);
      }
      map.setView([latitude, longitude], Math.max(map.getZoom(), zoom), { animate: true });
    } else if (primaryRef.current) {
      primaryRef.current.remove();
      primaryRef.current = null;
      circleRef.current?.remove();
      circleRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latitude, longitude, radiusMeters]);

  // Keep the read-only points in step with the props.
  useEffect(() => {
    const L = leafletRef.current;
    if (!L) return;
    renderPoints(L, markers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markers]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label="Map showing the school location"
      className={cn(
        "w-full overflow-hidden rounded-xl border border-border [&_.leaflet-container]:h-full",
        className,
      )}
      style={{ height }}
    />
  );
}
