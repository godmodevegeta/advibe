export function cartoTileUrl(apiKey: string | undefined): string | undefined {
  const key = apiKey?.trim();
  if (!key) return undefined;
  return `https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`;
}

export const cartoAttribution =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, &copy; <a href="https://carto.com/attributions">CARTO</a>';
