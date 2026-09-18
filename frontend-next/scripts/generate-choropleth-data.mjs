import fs from "node:fs";
import path from "node:path";

const source = JSON.parse(fs.readFileSync(path.resolve("public/geo/india-states.json"), "utf8"));
const simplify = (points, tolerance) => {
  if (points.length <= 2) return points;
  const squared = tolerance * tolerance;
  const distance = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2;
  const segmentDistance = (point, start, end) => {
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    if (!dx && !dy) return distance(point, start);
    const t = Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)));
    return distance(point, [start[0] + t * dx, start[1] + t * dy]);
  };
  let farthest = squared;
  let index = 0;
  for (let i = 1; i < points.length - 1; i += 1) {
    const current = segmentDistance(points[i], points[0], points.at(-1));
    if (current > farthest) { index = i; farthest = current; }
  }
  if (!index) return [points[0], points.at(-1)];
  const left = simplify(points.slice(0, index + 1), tolerance);
  const right = simplify(points.slice(index), tolerance);
  return left.slice(0, -1).concat(right);
};
const coordinates = (geometry) => {
  if (geometry.type === "Polygon") return geometry.coordinates.flat();
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat(2);
  return [];
};
const extent = source.features.flatMap((feature) => coordinates(feature.geometry));
const minX = Math.min(...extent.map(([x]) => x));
const maxX = Math.max(...extent.map(([x]) => x));
const minY = Math.min(...extent.map(([, y]) => y));
const maxY = Math.max(...extent.map(([, y]) => y));
const width = maxX - minX;
const height = maxY - minY;
const project = ([x, y]) => [((x - minX) / width) * 1000, ((maxY - y) / height) * 760];
const ringPath = (ring) => simplify(ring, 0.015).map((point, index) => `${index ? "L" : "M"}${project(point).map((value) => value.toFixed(2)).join(",")}`).join(" ") + " Z";
const center = (geometry) => {
  const points = coordinates(geometry);
  return [points.reduce((sum, [x]) => sum + x, 0) / points.length, points.reduce((sum, [, y]) => sum + y, 0) / points.length];
};
const districts = source.features.map((feature, index) => ({
  id: String(feature.properties?.ID_1 ?? index),
  name: feature.properties?.NAME_1 ?? `Region ${index + 1}`,
  path: geometryPath(feature.geometry),
  labelX: Number(project(center(feature.geometry))[0].toFixed(2)),
  labelY: Number(project(center(feature.geometry))[1].toFixed(2)),
}));
function geometryPath(geometry) {
  if (geometry.type === "Polygon") return geometry.coordinates.map(ringPath).join(" ");
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flatMap((polygon) => polygon.map(ringPath)).join(" ");
  return "";
}
const output = { viewBox: `0 0 1000 760`, districts };
fs.mkdirSync(path.resolve("src/data"), { recursive: true });
fs.writeFileSync(path.resolve("src/data/india-regions.json"), JSON.stringify(output));
console.log(`Generated ${districts.length} simplified SVG regions`);
