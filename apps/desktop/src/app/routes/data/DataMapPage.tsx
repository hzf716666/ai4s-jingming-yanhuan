import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import "echarts-gl";
import { cn } from "@/lib/cn";

const API = "http://127.0.0.1:8787/api/map";

interface MapPoint {
  name: string;
  value: number;
  unit: string;
  lon: number;
  lat: number;
  city?: string;
}

const FLY = [
  { label: "地球", center: [0, 20, 0], distance: 220 },
  { label: "中国", center: [104, 35, 0], distance: 46 },
  { label: "湖北", center: [112.4, 31, 0], distance: 10 },
];

const OCEAN = "#0b1e3f";
const BAR_TOP = "#4fc3f7";
const BAR_BODY = "#1976d2";

function lerp(a: number, b: number, k: number) {
  return a + (b - a) * k;
}
function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

export function DataMapPage() {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [indicators, setIndicators] = useState<
    { id: string; name: string; unit: string }[]
  >([]);
  const [indicator, setIndicator] = useState("营业收入_千元");
  const [year, setYear] = useState(2024);
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const [flying, setFlying] = useState(false);
  const [autoPlayed, setAutoPlayed] = useState(false);

  const [provincePoints, setProvincePoints] = useState<MapPoint[]>([]);
  const [zonePoints, setZonePoints] = useState<MapPoint[]>([]);

  // ---- load indicators once ----
  useEffect(() => {
    fetch(`${API}/indicators?scope=province`)
      .then((r) => r.json())
      .then((d) => {
        setIndicators(d.indicators);
        if (d.indicators[0]) setIndicator(d.indicators[0].id);
      })
      .catch(() => {});
  }, []);

  // ---- load points on indicator/year change ----
  useEffect(() => {
    if (!indicator) return;
    fetch(`${API}/provinces?indicator=${encodeURIComponent(indicator)}&year=${year}`)
      .then((r) => r.json())
      .then((d) => setProvincePoints(d.points ?? []))
      .catch(() => {});
    fetch(`${API}/zones?indicator=${encodeURIComponent(indicator)}&year=${year}`)
      .then((r) => r.json())
      .then((d) => setZonePoints(d.points ?? []))
      .catch(() => {});
  }, [indicator, year]);

  // ---- init chart ----
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    chart.on("click", (params: any) => {
      if (params?.data?.name) {
        const p = params.data as MapPoint;
        setSelected({ ...p, value: p.value, unit: p.unit });
      }
    });
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  const currentPoints = useMemo(() => {
    const vc = (
      chartRef.current?.getOption()?.globe as { viewControl?: { distance?: number } } | undefined
    )?.viewControl;
    return (vc?.distance ?? 220) < 28 ? zonePoints : provincePoints;
  }, [provincePoints, zonePoints]);

  // ---- render series ----
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const pts = currentPoints;
    const max = Math.max(1, ...pts.map((p) => p.value));
    chart.setOption(
      {
        globe: {
          baseColor: OCEAN,
          shading: "lambert",
          atmosphere: { show: true, glowPower: 80 },
          light: {
            ambient: { intensity: 0.5 },
            main: { intensity: 1.1, color: "#fff", shadow: true, alpha: 35, beta: 20 },
          },
          viewControl: {
            distance: 220,
            autoRotate: true,
            autoRotateSpeed: 4,
            minDistance: 3,
            maxDistance: 400,
          },
          layers: [
            {
              type: "bloom",
              bloomIntensity: 0.15,
            },
          ],
        },
        series: [
          {
            name: indicator,
            type: "bar3D",
            coordinateSystem: "globe",
            shading: "lambert",
            barSize: pts.length > 20 ? 1.1 : 0.8,
            data: pts.map((p) => ({
              value: [p.lon, p.lat, Math.max(0.4, (p.value / max) * 8)],
              name: p.name,
              lon: p.lon,
              lat: p.lat,
              raw: p.value,
              unit: p.unit,
              city: p.city,
            })),
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 1, 0, 0, [
                { offset: 0, color: BAR_BODY },
                { offset: 1, color: BAR_TOP },
              ]),
            },
            emphasis: { itemStyle: { color: "#ffd54f" } },
            label: {
              show: false,
            },
          },
        ],
      },
      true,
    );
  }, [currentPoints, indicator]);

  // ---- flyTo ----
  const flyTo = (idx: number) => {
    const chart = chartRef.current;
    if (!chart) return;
    const target = FLY[idx];
    setFlying(true);
    const t0 = performance.now();
    const dur = 2000;
    const vc = (
      chart.getOption()?.globe as { viewControl?: { center?: number[]; distance?: number } } | undefined
    )?.viewControl ?? { center: [0, 20, 0], distance: 220 };
    const fromCenter = vc.center ?? [0, 20, 0];
    const fromDist = vc.distance ?? 220;
    const step = (t: number) => {
      const k = easeInOut(Math.min(1, (t - t0) / dur));
      chart.setOption(
        {
          globe: {
            viewControl: {
              center: [
                lerp(fromCenter[0], target.center[0], k),
                lerp(fromCenter[1], target.center[1], k),
                0,
              ],
              distance: lerp(fromDist, target.distance, k),
              autoRotate: false,
            },
          },
        },
        true,
      );
      if (k < 1) requestAnimationFrame(step);
      else setFlying(false);
    };
    requestAnimationFrame(step);
  };

  // ---- auto play: earth -> china -> hubei once ----
  useEffect(() => {
    if (autoPlayed || !provincePoints.length) return;
    setAutoPlayed(true);
    const timer = setTimeout(() => flyTo(1), 1200);
    const timer2 = setTimeout(() => flyTo(2), 3400);
    return () => {
      clearTimeout(timer);
      clearTimeout(timer2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provincePoints.length, autoPlayed]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#060d1f] text-text">
      {/* 3D globe */}
      <div ref={ref} className="h-full w-full" />

      {/* click card */}
      {selected && (
        <div className="absolute right-4 top-4 w-56 rounded-card border border-border bg-surface/95 p-4 shadow-xl backdrop-blur">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">{selected.name}</div>
              {selected.city && (
                <div className="mt-0.5 text-xs text-muted">{selected.city}</div>
              )}
            </div>
            <button
              className="text-muted hover:text-text"
              onClick={() => setSelected(null)}
            >
              ✕
            </button>
          </div>
          <div className="mt-2 text-lg font-semibold text-accent">
            {selected.value.toLocaleString()}
            <span className="ml-1 text-xs font-normal text-muted">
              {selected.unit}
            </span>
          </div>
          <div className="mt-1 text-xs text-muted">
            {indicator.split("_")[0]} · {year} 年
          </div>
        </div>
      )}

      {/* fly buttons */}
      <div className="absolute left-4 top-4 flex gap-1.5">
        {FLY.map((f, i) => (
          <button
            key={f.label}
            onClick={() => flyTo(i)}
            disabled={flying}
            className="rounded-input border border-border bg-surface/80 px-3 py-1.5 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* year selector */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col gap-1">
        {[2023, 2024].map((y) => (
          <button
            key={y}
            onClick={() => setYear(y)}
            className={cn(
              "rounded-input border px-2.5 py-1.5 text-xs transition-colors",
              year === y
                ? "border-accent bg-accent/15 text-accent"
                : "border-border bg-surface/70 text-muted hover:text-text",
            )}
          >
            {y}
          </button>
        ))}
      </div>

      {/* bottom indicator bar */}
      <div className="absolute inset-x-0 bottom-0 border-t border-border/60 bg-surface/85 backdrop-blur">
        <div className="flex items-center gap-1.5 overflow-x-auto px-3 py-2">
          <span className="shrink-0 text-xs text-muted">指标</span>
          {indicators.map((ind) => (
            <button
              key={ind.id}
              onClick={() => setIndicator(ind.id)}
              className={cn(
                "shrink-0 rounded-input border px-2.5 py-1 text-xs transition-colors",
                indicator === ind.id
                  ? "border-accent bg-accent/15 text-accent"
                  : "border-border text-muted hover:text-text",
              )}
            >
              {ind.name}
              <span className="ml-1 opacity-60">{ind.unit}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
