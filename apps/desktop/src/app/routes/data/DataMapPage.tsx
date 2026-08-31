import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import "echarts-gl";
import graphicGL from "echarts-gl/lib/util/graphicGL";
import Bars3DGeometry from "echarts-gl/lib/util/geometry/Bars3DGeometry";
import { useUiStore } from "@/lib/store";
import { cn } from "@/lib/cn";

// ---------------------------------------------------------------------------
// echarts-gl 的 lines3D 会把线画在球体表面（与球面同深度 → z-fighting 不可见）。
// 通过替换 ecgl.meshLines3D 顶点着色器，把线条沿径向抬升 0.2%（围绕球心缩放），
// 使矢量轮廓线在任何缩放下都清晰可见。全库仅地图页使用 lines3D，替换安全。
// ---------------------------------------------------------------------------
const LINES3D_SHADER = `@export ecgl.meshLines3D.vertex

attribute vec3 position: POSITION;
attribute vec3 positionPrev;
attribute vec3 positionNext;
attribute float offset;
attribute vec4 a_Color : COLOR;

#ifdef VERTEX_ANIMATION
attribute vec3 prevPosition;
attribute vec3 prevPositionPrev;
attribute vec3 prevPositionNext;
uniform float percent : 1.0;
#endif

uniform mat4 worldViewProjection : WORLDVIEWPROJECTION;
uniform vec4 viewport : VIEWPORT;
uniform float near : NEAR;

varying vec4 v_Color;

@import ecgl.common.wireframe.vertexHeader

@import ecgl.lines3D.clipNear

void main()
{
#ifdef VERTEX_ANIMATION
 vec4 prevProj = worldViewProjection * vec4(mix(prevPositionPrev, positionPrev, percent) * 1.002, 1.0);
 vec4 currProj = worldViewProjection * vec4(mix(prevPosition, position, percent) * 1.002, 1.0);
 vec4 nextProj = worldViewProjection * vec4(mix(prevPositionNext, positionNext, percent) * 1.002, 1.0);
#else
 vec4 prevProj = worldViewProjection * vec4(positionPrev * 1.002, 1.0);
 vec4 currProj = worldViewProjection * vec4(position * 1.002, 1.0);
 vec4 nextProj = worldViewProjection * vec4(positionNext * 1.002, 1.0);
#endif

 if (currProj.w < 0.0) {
 if (nextProj.w > 0.0) {
 currProj = clipNear(currProj, nextProj);
 }
 else if (prevProj.w > 0.0) {
 currProj = clipNear(currProj, prevProj);
 }
 }

 vec2 prevScreen = (prevProj.xy / abs(prevProj.w) + 1.0) * 0.5 * viewport.zw;
 vec2 currScreen = (currProj.xy / abs(currProj.w) + 1.0) * 0.5 * viewport.zw;
 vec2 nextScreen = (nextProj.xy / abs(nextProj.w) + 1.0) * 0.5 * viewport.zw;

 vec2 dir;
 float len = offset;
 if (position == positionPrev) {
 dir = normalize(nextScreen - currScreen);
 }
 else if (position == positionNext) {
 dir = normalize(currScreen - prevScreen);
 }
 else {
 vec2 dirA = normalize(currScreen - prevScreen);
 vec2 dirB = normalize(nextScreen - currScreen);

 vec2 tanget = normalize(dirA + dirB);

 float miter = 1.0 / max(dot(tanget, dirA), 0.5);
 len *= miter;
 dir = tanget;
 }

 dir = vec2(-dir.y, dir.x) * len;
 currScreen += dir;

 currProj.xy = (currScreen / viewport.zw - 0.5) * 2.0 * abs(currProj.w);

 gl_Position = currProj;

 v_Color = a_Color;

 @import ecgl.common.wireframe.vertexMain
}
 @end`;

// 注册补丁着色器：覆盖默认的 ecgl.meshLines3D.vertex（同名 @export 直接替换，
// 与 echarts-gl 自身注册默认着色器的方式一致），把线条沿径向抬升 0.2% 消除
// z-fighting。必须在任何 lines3D 使用之前执行。
graphicGL.Shader.import(LINES3D_SHADER);

// ---------------------------------------------------------------------------
// 圆柱柱体：echarts-gl 的 bar3D 几何是方块（Bars3DGeometry.addBar 生成 8 顶点
// 立方体）。替换 addBar 与顶点/三角形计数，把每根柱子建成 12 段侧壁 + 顶盖的
// 圆柱（globe 场景 bars 关闭了背面剔除，环向绕序不影响可见性）。
// ---------------------------------------------------------------------------
const CYL_SEG = 12;
const CYL_VERTEX_COUNT = CYL_SEG * 2 + 1;
const CYL_TRIANGLE_COUNT = CYL_SEG * 3;

interface BarGeomCtx {
  _vertexOffset: number;
  _triangleOffset: number;
  attributes: { position: { set(i: number, v: number[]): void }; color: { set(i: number, v: number[]): void } };
  indices: { [i: number]: number };
  _dataIndices: { [i: number]: number };
}

const barProto = Bars3DGeometry.prototype as unknown as {
  addBar: (...a: unknown[]) => void;
  getBarVertexCount: () => number;
  getBarTriangleCount: () => number;
  __jmCyl?: boolean;
};
if (!barProto.__jmCyl) {
  const norm3 = (v: number[]): number[] => {
    const l = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / l, v[1] / l, v[2] / l];
  };
  const cross3 = (a: number[], b: number[]): number[] => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  const addCylinder = function (
    this: BarGeomCtx,
    start: number[],
    dir: number[],
    leftDir: number[],
    size: number[],
    color: number[],
    dataIndex: number,
  ) {
    const py = norm3(dir);
    const pz = norm3(cross3(leftDir, py));
    const px = norm3(cross3(py, pz));
    const r = Math.max(0.01, Math.min(size[0], size[2]) / 2);
    const h = Math.max(0, size[1]);
    const startV = this._vertexOffset;
    const topCenter = startV + CYL_SEG * 2;
    for (let i = 0; i < CYL_SEG; i++) {
      const a = (i / CYL_SEG) * Math.PI * 2;
      const ca = Math.cos(a);
      const sa = Math.sin(a);
      const ox = (px[0] * ca + pz[0] * sa) * r;
      const oy = (px[1] * ca + pz[1] * sa) * r;
      const oz = (px[2] * ca + pz[2] * sa) * r;
      this.attributes.position.set(startV + i * 2, [start[0] + ox, start[1] + oy, start[2] + oz]);
      this.attributes.color.set(startV + i * 2, color);
      this.attributes.position.set(startV + i * 2 + 1, [
        start[0] + ox + py[0] * h,
        start[1] + oy + py[1] * h,
        start[2] + oz + py[2] * h,
      ]);
      this.attributes.color.set(startV + i * 2 + 1, color);
    }
    this.attributes.position.set(topCenter, [start[0] + py[0] * h, start[1] + py[1] * h, start[2] + py[2] * h]);
    this.attributes.color.set(topCenter, color);
    let idx3 = this._triangleOffset * 3;
    for (let i = 0; i < CYL_SEG; i++) {
      const b0 = startV + i * 2;
      const b1 = startV + ((i + 1) % CYL_SEG) * 2;
      const t0 = b0 + 1;
      const t1 = b1 + 1;
      this.indices[idx3++] = b0;
      this.indices[idx3++] = b1;
      this.indices[idx3++] = t0;
      this.indices[idx3++] = b1;
      this.indices[idx3++] = t1;
      this.indices[idx3++] = t0;
      this.indices[idx3++] = t0;
      this.indices[idx3++] = t1;
      this.indices[idx3++] = topCenter;
    }
    this._triangleOffset += CYL_TRIANGLE_COUNT;
    this._vertexOffset = topCenter + 1;
    for (let i = startV; i < this._vertexOffset; i++) this._dataIndices[i] = dataIndex;
  };
  barProto.addBar = addCylinder as unknown as typeof barProto.addBar;
  barProto.getBarVertexCount = () => CYL_VERTEX_COUNT;
  barProto.getBarTriangleCount = () => CYL_TRIANGLE_COUNT;
  barProto.__jmCyl = true;
}

// ---------------------------------------------------------------------------
// 半透明球体：claygl 渲染器按 material.transparent 决定是否开启混合。
// 地球表面材质由 graphicGL.createMaterial('ecgl.color'|'ecgl.lambert'|'ecgl.realistic')
// 创建（GlobeView 内调用），通过替换该方法给球体材质打开透明 + 关闭深度写入，
// 使 baseColor 的 alpha 真正生效（默认被忽略）。bars/scatter/lines 用的是
// ecgl.meshXxx 前缀，不受影响；lines3D 的材质本就自带 transparent。
// ---------------------------------------------------------------------------
if (!(window as unknown as { __jmGlobePatch?: boolean }).__jmGlobePatch) {
  const ggl = (echarts as unknown as {
    graphicGL?: { createMaterial?: (prefix: string, defines?: unknown) => { transparent?: boolean; depthMask?: boolean } }
  }).graphicGL;
  const orig = ggl?.createMaterial;
  if (orig && !(orig as { __jmPatched?: boolean }).__jmPatched) {
    const patched = (prefix: string, defines?: unknown) => {
      const m = orig(prefix, defines);
      if (prefix === "ecgl.color" || prefix === "ecgl.lambert" || prefix === "ecgl.realistic") {
        m.transparent = true;
        m.depthMask = false;
      }
      return m;
    };
    (patched as { __jmPatched?: boolean }).__jmPatched = true;
    ggl!.createMaterial = patched;
  }
  (window as unknown as { __jmGlobePatch?: boolean }).__jmGlobePatch = true;
}

const API = "http://127.0.0.1:8787/api/map";
const DEV = !!(import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV;

interface MapPoint {
  name: string;
  value: number;
  unit: string;
  lon: number;
  lat: number;
  city?: string;
}

interface GeoFeature {
  name: string;
  zh: boolean;
  lon: number;
  lat: number;
  rings: [number, number][][];
}

// 视域深度档位（按相机距离划分，驱动边界/名称层的显隐）：
// 全球(整球) → 洲际(≈70°) → 中国(≈全国) → 区域(湖北+邻省) → 湖北(≈全省)
// 柱状图的"吸引力度"不按档位跳变，而是按连续距离插值（见 BAR_HEIGHT_KEYFRAMES）。
const LEVELS = [
  { label: "全球", minDist: 160 },
  { label: "洲际", minDist: 90 },
  { label: "中国", minDist: 60 },
  { label: "区域", minDist: 25 },
  { label: "湖北", minDist: 0 },
];

function levelFromDistance(d: number): number {
  for (let i = 0; i < LEVELS.length; i++) {
    if (d >= LEVELS[i].minDist) return i;
  }
  return LEVELS.length - 1;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function withAlpha(color: string, alpha: number): string {
  const h = (color || "").trim();
  if (h.startsWith("#")) {
    const full = h.length === 4 ? "#" + h[1] + h[1] + h[2] + h[2] + h[3] + h[3] : h;
    const r = parseInt(full.slice(1, 3), 16);
    const g = parseInt(full.slice(3, 5), 16);
    const b = parseInt(full.slice(5, 7), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
  }
  return "rgba(120,120,120," + alpha + ")";
}

/** hex 颜色按 t∈[0,1] 向白色混合：同一指标内数值越大柱体越亮，便于区分 */
function lighten(hex: string, t: number): string {
  const h = (hex || "").trim();
  const full = h.length === 4 ? "#" + h[1] + h[1] + h[2] + h[2] + h[3] + h[3] : h;
  if (!/^#[0-9a-fA-F]{6}$/.test(full)) return hex;
  const m = Math.min(1, Math.max(0, t));
  const r = parseInt(full.slice(1, 3), 16);
  const g = parseInt(full.slice(3, 5), 16);
  const b = parseInt(full.slice(5, 7), 16);
  return (
    "rgb(" +
    Math.round(r + (255 - r) * m) +
    "," +
    Math.round(g + (255 - g) * m) +
    "," +
    Math.round(b + (255 - b) * m) +
    ")"
  );
}

// ---- 连续插值工具：滚轮缩放时所有柱子参数随距离平滑变化 ----

function lerpKeys(keys: [number, number][], d: number): number {
  if (d <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    if (d <= keys[i + 1][0]) {
      const t = (d - keys[i][0]) / (keys[i + 1][0] - keys[i][0]);
      return keys[i][1] + (keys[i + 1][1] - keys[i][1]) * t;
    }
  }
  return keys[keys.length - 1][1];
}

function smoothRamp(x: number, a: number, b: number): number {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

/** 柱子高度关键帧 [距离, 高度系数]，距离升序（近→远，lerpKeys 约定）：
 *  放大（距离变小）时柱高随视域收缩——相机靠近球面约 15 倍，柱高必须按更陡的
 *  曲线下降，否则放大后柱体在屏幕上看起来不变。 */
const BAR_HEIGHT_KEYFRAMES: [number, number][] = [
  [15, 0.09], [30, 0.12], [60, 0.16], [100, 0.21], [150, 0.26], [230, 0.3], [700, 0.34],
];
/** 柱子粗细关键帧 [距离, 尺寸]，距离升序：同样随放大收窄，避免深放大时柱子互相遮挡 */
const BAR_SIZE_KEYFRAMES: [number, number][] = [
  [15, 0.4], [30, 0.55], [60, 0.8], [100, 1.1], [150, 1.5], [230, 2.0], [700, 2.6],
];
/** 各粒度的最大柱高（相对球半径） */
const GRAN_MAX_H = { nation: 6, prov: 4.5, city: 3.5 } as const;

/** 粒度权重随距离连续过渡：全球单柱 → 省 → 市州（交叉淡入淡出） */
function granularityWeights(d: number): { wNation: number; wProv: number; wCity: number } {
  const wNation = 1 - smoothRamp(d, 160, 130);
  const wProv = smoothRamp(d, 160, 130) * (1 - smoothRamp(d, 62, 42));
  const wCity = smoothRamp(d, 62, 42);
  return { wNation, wProv, wCity };
}

/** 园区数据按 city 聚合成市州（放大到省市级后柱状图粒度跟随） */
function aggregateCities(zones: MapPoint[]): MapPoint[] {
  const byCity = new Map<string, { v: number; pt: MapPoint }>();
  for (const z of zones) {
    const city = z.city;
    if (!city) continue;
    const e = byCity.get(city);
    if (e) e.v += z.value;
    else byCity.set(city, { v: z.value, pt: z });
  }
  return Array.from(byCity.entries()).map(([city, e]) => ({
    name: city,
    value: e.v,
    unit: e.pt.unit,
    lon: e.pt.lon,
    lat: e.pt.lat,
    city,
  }));
}

// ---- 焦点区域粒度切换（参考 three.js 示例的 checkView 语义）----

/** 点在多环多边形内（首环外环，其余为内环挖洞） */
function pointInRings(lon: number, lat: number, rings: [number, number][][]): boolean {
  const inside = (ring: [number, number][]) => {
    let is = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) is = !is;
    }
    return is;
  };
  if (!inside(rings[0])) return false;
  for (let i = 1; i < rings.length; i++) {
    if (inside(rings[i])) return false;
  }
  return true;
}

/** 相机朝向（alpha/beta）→ 视线中心落在地球表面的经纬度。
 *  与 echarts-gl 的 directionFromAlphaBeta 同公式（alpha 仰角、beta 方位角）。 */
function viewCenterLatLon(alpha: number, beta: number): { lat: number; lon: number } {
  const theta = ((alpha + 90) * Math.PI) / 180;
  const phi = ((90 - beta) * Math.PI) / 180;
  const dir = [Math.sin(theta) * Math.cos(phi), -Math.cos(theta), Math.sin(theta) * Math.sin(phi)];
  const lat = 90 - (Math.acos(Math.max(-1, Math.min(1, dir[1]))) * 180) / Math.PI;
  const lon = (Math.atan2(-dir[2], dir[0]) * 180) / Math.PI;
  return { lat, lon };
}

/** geo 图层名（北京市/广西壮族自治区）→ 数据层名（北京/广西） */
function normalizeProvinceName(name: string): string {
  return name
    .replace(/特别行政区$/, "")
    .replace(/壮族自治区$/, "")
    .replace(/回族自治区$/, "")
    .replace(/维吾尔自治区$/, "")
    .replace(/自治区$/, "")
    .replace(/省$/, "")
    .replace(/市$/, "");
}

export function DataMapPage() {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const camRef = useRef({ distance: 230, alpha: 20, beta: 194 });
  const distRef = useRef(230);
  const zoomIdxRef = useRef(0);
  const lastBarsDistRef = useRef(-1);
  const focusKeyRef = useRef<string | null>(null);
  const geoRef = useRef<GeoFeature[] | null>(null);
  const firstOptRef = useRef(true);
  const borderRef = useRef<Record<string, unknown>[]>([]);
  const nameRef = useRef<Record<string, unknown>[]>([]);
  const buildBarsRef = useRef<(d: number) => Record<string, unknown>[]>(() => []);
  const theme = useUiStore((s) => s.theme);
  const [indicators, setIndicators] = useState<{ id: string; name: string; unit: string }[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set(["营业收入_千元"]));
  const [year, setYear] = useState(2024);
  const [years, setYears] = useState<number[]>([2023, 2024]);
  const [zoomIdx, setZoomIdx] = useState(0);
  const [focusName, setFocusName] = useState<string | null>(null);
  const [selectedPt, setSelectedPt] = useState<MapPoint | null>(null);
  const [barData, setBarData] = useState<Record<string, { prov: MapPoint[]; zones: MapPoint[] }>>({});
  const [geo, setGeo] = useState<Record<string, GeoFeature[]>>({});

  // 初始朝向亚洲；DEV 下支持 ?dist=N&alpha=N&beta=N 指定初始相机（测试焦点粒度切换）
  useEffect(() => {
    camRef.current = { distance: 230, alpha: 20, beta: 104 + 90 };
    if (DEV) {
      const q = new URLSearchParams(location.search);
      const d = parseFloat(q.get("dist") ?? "");
      const a = parseFloat(q.get("alpha") ?? "");
      const b = parseFloat(q.get("beta") ?? "");
      const next = { ...camRef.current };
      if (isFinite(d) && d > 0) next.distance = d;
      if (isFinite(a)) next.alpha = a;
      if (isFinite(b)) next.beta = b;
      if (next.distance !== camRef.current.distance || next.alpha !== camRef.current.alpha || next.beta !== camRef.current.beta) {
        camRef.current = next;
        distRef.current = next.distance;
        lastBarsDistRef.current = -1;
      }
    }
  }, []);

  useEffect(() => {
    fetch(API + "/indicators?scope=province")
      .then((r) => r.json())
      .then((d) => {
        setIndicators(d.indicators);
        const biz = (d.indicators as { id: string }[]).find(
          (i) => i.id === "营业收入_千元",
        );
        if (biz) setSelected(new Set([biz.id]));
      })
      .catch(() => {});
    fetch(API + "/zone-years")
      .then((r) => r.json())
      .then((d) => {
        const ys = (d.years as number[]) ?? [];
        if (ys.length) {
          setYears(ys);
          setYear(ys[ys.length - 1]);
        }
      })
      .catch(() => {});
    Promise.all(
      ["world", "china", "hubei", "districts"].map((n) =>
        fetch(API + "/geo/" + n)
          .then((r) => r.json())
          .catch(() => []),
      ),
    ).then(([world, china, hubei, districts]) =>
      setGeo({ world, china, hubei, districts }),
    );
  }, []);

  // 按需拉取选中指标的数据（缓存键 = 指标 + 年份）
  useEffect(() => {
    if (!year) return;
    for (const id of selected) {
      const key = id + "@" + year;
      if (barData[key]) continue;
      Promise.all([
        fetch(API + "/provinces?indicator=" + encodeURIComponent(id) + "&year=" + year).then((r) => r.json()),
        fetch(API + "/zones?indicator=" + encodeURIComponent(id) + "&year=" + year).then((r) => r.json()),
      ])
        .then(([p, z]) => {
          setBarData((prev) => ({
            ...prev,
            [key]: { prov: p.points ?? [], zones: z.points ?? [] },
          }));
        })
        .catch(() => {});
    }
  }, [selected, year, barData]);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    // StrictMode 开发双挂载：新 chart 必须重新下发完整 globe 配置
    firstOptRef.current = true;
    prevZoomIdxRef.current = null;
    lastBarsDistRef.current = -1;
    if (DEV) (window as unknown as Record<string, unknown>).__mapChart = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);

    // 相机变化（拖动旋转/滚轮缩放）→ 记录相机 + 换算视域档位 + 刷新柱状图
    // 注意：echarts-gl 注册的 action event 名是全小写 'globecamerachanged'
    chart.on("globecamerachanged", (params) => {
      const p = params as { distance?: number; alpha?: number; beta?: number };
      if (typeof p.distance !== "number") return;
      camRef.current = {
        distance: p.distance,
        alpha: typeof p.alpha === "number" ? p.alpha : camRef.current.alpha,
        beta: typeof p.beta === "number" ? p.beta : camRef.current.beta,
      };
      distRef.current = p.distance;
      const idx = levelFromDistance(p.distance);
      if (idx !== zoomIdxRef.current) {
        zoomIdxRef.current = idx;
        setZoomIdx(idx);
      }
      // 焦点区域粒度切换：视线中心落在哪个省，放大后就展开哪个省的下一级
      {
        const china = geoRef.current;
        if (china?.length && typeof p.alpha === "number" && typeof p.beta === "number") {
          const { lat, lon } = viewCenterLatLon(p.alpha, p.beta);
          let fk: string | null = null;
          let hitName = "";
          for (const f of china) {
            if (pointInRings(lon, lat, f.rings)) {
              hitName = f.name;
              fk = normalizeProvinceName(f.name);
              break;
            }
          }
          if (fk !== focusKeyRef.current) {
            focusKeyRef.current = fk;
            setFocusName(fk);
          }
          if (DEV) {
            const st = (window as unknown as Record<string, unknown>).__mapDebugState as {
              lastView?: Record<string, unknown>;
            };
            if (st) {
              st.lastView = {
                lat: Math.round(lat * 10) / 10,
                lon: Math.round(lon * 10) / 10,
                chinaN: china.length,
                hit: hitName || null,
                fk,
              };
            }
          }
        }
      }
      // 相机状态实时同步到调试对象（不依赖 React 渲染）
      if (DEV) {
        const st = (window as unknown as Record<string, unknown>).__mapDebugState as
          | { cam?: Record<string, number>; camEvents?: number }
          | undefined;
        if (st) {
          st.camEvents = (st.camEvents ?? 0) + 1;
          st.cam = {
            distance: Math.round(p.distance),
            alpha: Math.round(camRef.current.alpha),
            beta: Math.round(camRef.current.beta),
          };
        }
      }
    });

    chart.on("click", (params) => {
      const p = params as {
        data?: { name?: string; raw?: number; unit?: string; lon?: number; lat?: number; city?: string };
      };
      if (p?.data?.name && typeof p.data.raw === "number") {
        setSelectedPt({
          name: p.data.name as string,
          value: p.data.raw,
          unit: p.data.unit ?? "",
          lon: p.data.lon ?? 0,
          lat: p.data.lat ?? 0,
          city: p.data.city,
        });
      }
    });

    // 渲染后像素探针（验证半透明/边界，仅开发模式）
    if (DEV) {
      const probeRef: { at: number; px: [number, number, number, number][] } = { at: 0, px: [] };
      (window as unknown as Record<string, unknown>).__mapProbe = probeRef;
      chart.getZr().on("rendered", () => {
        // 柱状图随距离连续刷新：rendered 在动作处理栈外触发（下一帧 flush），
        // 避免相机动作处理期间 setOption 被 echarts 延迟吞掉
        const d = distRef.current;
        if (Math.abs(d - lastBarsDistRef.current) < 0.4) return;
        lastBarsDistRef.current = d;
        const chartNow = chartRef.current;
        if (chartNow) {
          try {
            chartNow.setOption(
              { series: [...borderRef.current, ...nameRef.current, ...buildBarsRef.current(d)] },
              { replaceMerge: ["series"] },
            );
            if (DEV) {
              const st = (window as unknown as Record<string, unknown>).__mapDebugState as {
                rAFRuns?: number;
                lastRAFDist?: number;
                log?: string[];
              };
              if (st) {
                st.rAFRuns = (st.rAFRuns ?? 0) + 1;
                st.lastRAFDist = Math.round(d);
                st.log = st.log ?? [];
                st.log.push("R" + st.rAFRuns + "@" + Math.round(d) + " " + Date.now().toString().slice(-5));
                if (st.log.length > 30) st.log = st.log.slice(-30);
              }
            }
          } catch (e) {
            const st = (window as unknown as Record<string, unknown>).__mapDebugState as {
              rAFErr?: string;
            };
            if (st) st.rAFErr = String((e as Error).message ?? e).slice(0, 200);
          }
        }
        const cv = ref.current?.querySelector("canvas");
        if (!cv) return;
        const gl = (cv.getContext("webgl2") || cv.getContext("webgl") || cv.getContext("experimental-webgl")) as WebGLRenderingContext | null;
        if (!gl) return;
        const w = cv.width, h = cv.height;
        const N = 7;
        const px = new Uint8Array(4);
        const out: [number, number, number, number][] = [];
        for (let gy = 0; gy < N; gy++) {
          for (let gx = 0; gx < N; gx++) {
            gl.readPixels(Math.floor((gx + 0.5) * w / N), Math.floor((gy + 0.5) * h / N), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
            out.push([px[0], px[1], px[2], px[3]]);
          }
        }
        // 水平扫描线（y=h/2，每 8px 采一点）+ 垂直扫描线（x=w/2）
        const scan = (yf: number, xf: number, step: number, horizontal: boolean): number[][] => {
          const res: number[][] = [];
          for (let i = 0; i < (horizontal ? w : h); i += step) {
            const x = horizontal ? i : Math.floor(xf * w);
            const y = horizontal ? Math.floor(yf * h) : i;
            gl.readPixels(x, y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
            if (px[3] > 0) res.push([x, y, px[0], px[1], px[2], px[3]]);
          }
          return res;
        };
        const hscan = scan(0.5, 0.5, 8, true);
        const vscan = scan(0.5, 0.5, 8, false);
        probeRef.at = Date.now();
        probeRef.px = out;
        (probeRef as unknown as { hscan: number[][]; vscan: number[][] }).hscan = hscan;
        (probeRef as unknown as { vscan: number[][] }).vscan = vscan;
      });
    }

    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  // ---- 柱状图系列：粒度 + 高度 + 粗细全部是"距离"的连续函数 ----
  const buildBars = (d: number): Record<string, unknown>[] => {
    const out: Record<string, unknown>[] = [];
    const hScale = lerpKeys(BAR_HEIGHT_KEYFRAMES, d);
    const barSize = lerpKeys(BAR_SIZE_KEYFRAMES, d);
    const { wNation, wProv, wCity } = granularityWeights(d);
    const palette = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5", "--series-6", "--series-7", "--series-8"];
    let ci = 0;
    for (const id of selected) {
      const data = barData[id + "@" + year];
      if (!data) continue;
      const color = cssVar(palette[ci % palette.length]);
      ci++;
      // opOf 返回每根柱子透明度：粒度交叉淡入淡出 + 焦点省保持
      const pushBars = (pts: MapPoint[], maxH: number, opOf: (p: MapPoint) => number) => {
        const list = pts.filter((p) => opOf(p) > 0.01);
        if (!list.length) return;
        const max = Math.max(1, ...list.map((p) => p.value));
        out.push({
          type: "bar3D",
          coordinateSystem: "globe",
          shading: "color",
          barSize,
          data: list.map((p) => {
            const op = Math.min(1, Math.max(0, opOf(p)));
            return {
              name: p.name,
              value: [p.lon, p.lat, Math.max(0.25, (Math.log10(1 + p.value) / Math.log10(1 + max)) * maxH * hScale)],
              raw: p.value,
              unit: p.unit,
              lon: p.lon,
              lat: p.lat,
              city: p.city,
              // 同指标内按数值向白色混合：值越大越亮，与其它指标的主色相区分
              itemStyle: { color: lighten(color, (p.value / max) * 0.55), opacity: op },
            };
          }),
          emphasis: { itemStyle: { color: withAlpha(cssVar("--text"), 0.95) } },
          label: { show: false },
        });
      };
      // 全球/洲际：全国汇总单柱
      if (wNation > 0.01 && data.prov.length) {
        const v = data.prov.reduce((s, p) => s + p.value, 0);
        pushBars([{ name: "中国", value: v, unit: data.prov[0]?.unit ?? "", lon: 104, lat: 35 }], GRAN_MAX_H.nation, () => wNation);
      }
      // 中国：省级粒度。深放大（wCity 淡入区）时非焦点省提前淡出；
      // 焦点省有市数据则让位给市柱，无市数据则保持显示（不突然变成别省的柱子）
      {
        const fk = focusKeyRef.current;
        const needProvBars = wProv > 0.01 || (fk !== null && wCity > 0.01);
        if (needProvBars && data.prov.length) {
          pushBars(data.prov, GRAN_MAX_H.prov, (p) => {
            if (!fk) return wProv;
            if (p.name === fk) return fk === "湖北" ? wProv * (1 - wCity) : Math.max(wProv, 0.9 * wCity);
            return wProv * (1 - wCity);
          });
        }
      }
      // 区域/湖北：市州粒度跟随焦点省（目前只有湖北有市州数据）
      if (wCity > 0.01) {
        const fk = focusKeyRef.current;
        const cityPts = fk === "湖北" ? aggregateCities(data.zones) : [];
        if (cityPts.length) pushBars(cityPts, GRAN_MAX_H.city, () => wCity);
      }
    }
    return out;
  };
  buildBarsRef.current = buildBars;

  // ---- 轮廓层：各档位显示哪些层、透明度、颜色（档位变化时切换） ----
  const borderSeries = useMemo(() => {
    const world = geo.world ?? [];
    const china = geo.china ?? [];
    const hubei = geo.hubei ?? [];
    const districts = geo.districts ?? [];
    const text = cssVar("--text");
    const accent = cssVar("--accent");

    const layers: { data: GeoFeature[]; hex: string; width: number; show: (idx: number) => number }[] = [
      { data: world, hex: text, width: 1.5, show: (i) => (i <= 1 ? 1 : i === 2 ? 0.18 : 0) },
      { data: china, hex: text, width: 1.8, show: (i) => (i === 2 ? 1 : i === 3 ? 0.38 : i === 4 ? 0.15 : 0) },
      { data: hubei, hex: accent, width: 2.2, show: (i) => (i >= 3 ? 1 : 0) },
      { data: districts, hex: text, width: 1.4, show: (i) => (i === 4 ? 1 : 0) },
    ];

    const out: Record<string, unknown>[] = [];
    for (const ly of layers) {
      const alpha = ly.show(zoomIdx);
      if (!alpha) continue;
      // polyline 模式下每条 coords 必须是一维点数组 [[lon,lat],...]；
      // 一个 feature 的多个环（含岛屿/飞地）要拆成多个 data item，
      // 否则 dataToPoint 收到嵌套数组产生 NaN，整层静默不渲染。
      const items = ly.data.flatMap((f) => f.rings.map((ring) => ({ coords: ring })));
      if (!items.length) continue;
      out.push({
        type: "lines3D",
        coordinateSystem: "globe",
        polyline: true,
        silent: true,
        lineStyle: { color: withAlpha(ly.hex, alpha), width: ly.width, opacity: 1 },
        data: items,
      });
    }
    return out;
  }, [geo, zoomIdx, theme]);

  // ---- 名称层 ----
  const nameSeries = useMemo(() => {
    const text = cssVar("--text");
    const accent = cssVar("--accent");
    const world = (geo.world ?? []).filter((f) => f.zh);
    const bySize = (a: GeoFeature, b: GeoFeature) => b.rings.length - a.rings.length;
    const layers: { names: GeoFeature[]; color: string; fontSize: number; show: (i: number) => boolean }[] = [
      { names: world.slice().sort(bySize).slice(0, 20), color: withAlpha(text, 0.85), fontSize: 10, show: (i) => i === 0 },
      { names: world.slice().sort(bySize).slice(0, 60), color: withAlpha(text, 0.9), fontSize: 10, show: (i) => i === 1 },
      { names: geo.china ?? [], color: withAlpha(text, 0.95), fontSize: 12, show: (i) => i === 2 },
      { names: geo.hubei ?? [], color: withAlpha(accent, 0.95), fontSize: 13, show: (i) => i === 3 || i === 4 },
      { names: geo.districts ?? [], color: withAlpha(text, 0.85), fontSize: 9, show: (i) => i === 4 },
    ];
    return layers
      .filter((ly) => ly.show(zoomIdx))
      .map((ly) => ({
        type: "scatter3D",
        coordinateSystem: "globe",
        silent: true,
        symbolSize: 0,
        label: {
          show: true,
          formatter: (p: any) => p.data?.name ?? "",
          color: ly.color,
          fontSize: ly.fontSize,
          distance: 3,
        },
        data: ly.names.map((f) => ({ name: f.name, value: [f.lon, f.lat, 0] })),
      }));
  }, [geo, zoomIdx, theme]);

  // 同步最新边界/名称系列到 ref（相机事件里重建柱子时需要带上）
  useEffect(() => {
    borderRef.current = borderSeries;
    nameRef.current = nameSeries;
  }, [borderSeries, nameSeries]);

  // geo.china 同步到 ref（相机事件里做焦点省判定）
  useEffect(() => {
    geoRef.current = geo.china ?? null;
  }, [geo]);

  // 主 setOption：只在首次挂载写入完整 globe（含相机）；之后仅在视域档位
  // 变化时用部分合并更新 autoRotate；年份/指标/主题变化只发 series——
  // globe 完全不出现在选项里，相机倍率必然保持。
  const prevZoomIdxRef = useRef<number | null>(null);
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const d = distRef.current;
    const series = [...borderSeries, ...nameSeries, ...buildBars(d)];
    let globe: Record<string, unknown> | undefined;
    if (firstOptRef.current) {
      // 浅色主题下 --surface 是白/米白，白球配白底看不见——浅色改用淡蓝灰
      const sphereColor =
        theme === "dark" ? withAlpha(cssVar("--surface"), 0.5) : "rgba(203, 216, 233, 0.65)";
      globe = {
        shading: "color",
        baseColor: sphereColor,
        atmosphere: { show: false },
        light: { ambient: { intensity: 0 }, main: { intensity: 0 } },
        viewControl: {
          distance: camRef.current.distance,
          alpha: camRef.current.alpha,
          beta: camRef.current.beta,
          autoRotate: zoomIdx === 0,
          autoRotateSpeed: 0.8,
          minDistance: 15,
          maxDistance: 700,
          panSensitivity: 0,
          zoomSensitivity: 1,
          rotateSensitivity: 1,
          animationDurationUpdate: 600,
          animationEasingUpdate: "cubicOut",
        },
      };
    } else if (prevZoomIdxRef.current !== zoomIdx) {
      globe = { viewControl: { autoRotate: zoomIdx === 0 } };
    }
    prevZoomIdxRef.current = zoomIdx;
    firstOptRef.current = false;
    chart.setOption(
      {
        backgroundColor: "transparent",
        ...(globe ? { globe } : {}),
        series,
      },
      { replaceMerge: ["series"] },
    );
    if (DEV) {
      (window as unknown as Record<string, unknown>).__lastGlobeOpt = globe;
      const w2 = window as unknown as Record<string, unknown>;
      // OrbitControl 内部状态（排查自动旋转/事件用）
      try {
        const ech = chart as unknown as {
          getModel: () => { getComponent: (t: string) => unknown };
          getViewOfComponentModel: (m: unknown) => { _control?: Record<string, unknown> } | null;
        };
        const gm = ech.getModel().getComponent("globe");
        const gv = gm ? ech.getViewOfComponentModel(gm) : null;
        const ctl = gv ? (gv as unknown as { _control?: Record<string, unknown> })._control : null;
        // 实验：清理僵尸 animator（animateTo 目标=当前值时 clip 被停但 done 不触发）
        if (ctl && typeof ctl.stopAllAnimation === "function") ctl.stopAllAnimation();
        w2.__mapControl = ctl
          ? {
              rotating: ctl._rotating,
              autoRotate: ctl._autoRotate,
              animating: typeof ctl._isAnimating === "function" ? ctl._isAnimating() : null,
              animators: Array.isArray(ctl._animators) ? ctl._animators.length : null,
            }
          : null;
        const anim = (chart.getZr() as unknown as {
          animation?: { _$handlers?: Record<string, unknown[] | undefined>; on?: (n: string, h: () => void) => void };
        })?.animation;
        w2.__mapFrameHooks = anim?._$handlers?.frame?.length ?? -1;
        // 每帧探针：确认 zr 动画循环是否真的在跑
        if (!w2.__frameProbeInstalled) {
          w2.__frameProbeInstalled = true;
          anim?.on?.("frame", () => {
            (w2.__frameTick as number[])?.push(Date.now());
          });
          w2.__frameTick = [];
        }
        w2.__ctlPhi = ctl ? (ctl._phi as number) : null;
      } catch {
        w2.__mapControl = null;
      }
      const mainLog = (w2.__mapMainLog as string[]) ?? [];
      mainLog.push("M@" + Math.round(d) + " " + Date.now().toString().slice(-5));
      if (mainLog.length > 20) mainLog.shift();
      w2.__mapMainLog = mainLog;
      const g = (chart.getOption() as unknown as { globe?: Record<string, unknown> })?.globe;
      w2.__mapChartGlobe = g
        ? {
            shading: g.shading ?? null,
            baseColor: g.baseColor ?? null,
            atmosphere: (g.atmosphere as Record<string, unknown>) ?? null,
            light: (g.light as Record<string, unknown>) ?? null,
            vc: (g.viewControl as Record<string, unknown>) ?? null,
          }
        : null;
      w2.__mapSeriesInfo = (chart.getOption().series as { type?: string; data?: unknown[] }[]).map((s) => ({
        t: s.type,
        n: s.data?.length ?? 0,
      }));
    }
  }, [zoomIdx, theme, geo, selected, year, barData, borderSeries, nameSeries]);

  // 开发调试钩子：纯属性对象（每次渲染刷新），浏览器侧可直接读取
  if (DEV) {
    const w = window as unknown as Record<string, unknown>;
    const state = (w.__mapDebugState as
      | {
          cam: Record<string, number> | null;
          bars: Record<string, unknown>[] | null;
          camEvents?: number;
          barDataKeys?: string[];
          lastBarsDist?: number;
          focus?: string | null;
        }
      | undefined) ?? { cam: null, bars: null, camEvents: 0, barDataKeys: [], lastBarsDist: -1, focus: null };
    state.cam = {
      distance: Math.round(camRef.current.distance),
      alpha: Math.round(camRef.current.alpha),
      beta: Math.round(camRef.current.beta),
      zoomIdx,
    };
    state.bars = ((chartRef.current?.getOption().series ?? []) as { type?: string }[])
      .filter((s) => s.type === "bar3D")
      .map((s) => {
        const ss = s as { data?: { value?: number[]; name?: string }[]; itemStyle?: { opacity?: number }; barSize?: number };
        return {
          n: ss.data?.length ?? 0,
          maxH: Math.round(Math.max(0, ...(ss.data ?? []).map((dd) => dd.value?.[2] ?? 0)) * 100) / 100,
          first: ss.data?.[0]?.name ?? "",
          names: (ss.data ?? []).map((dd) => dd.name ?? "").slice(0, 14),
          opacity: Math.round((ss.itemStyle?.opacity ?? 1) * 1000) / 1000,
          barSize: Math.round((ss.barSize ?? 0) * 100) / 100,
        };
      });
    state.barDataKeys = Object.keys(barData);
    state.lastBarsDist = Math.round(lastBarsDistRef.current * 10) / 10;
    state.focus = focusKeyRef.current;
    w.__mapDebugState = state;
    {
      const cs = getComputedStyle(document.documentElement);
      w.__mapDebugVars = {
        theme,
        surface: cs.getPropertyValue("--surface").trim(),
        text: cs.getPropertyValue("--text").trim(),
        accent: cs.getPropertyValue("--accent").trim(),
        series1: cs.getPropertyValue("--series-1").trim(),
      };
    }
    // 实际生效的 globe 配置（排查渲染用）
    const go = (chartRef.current?.getOption() as unknown as { globe?: Record<string, unknown> })?.globe;
    const g0 = (go?.["0"] ?? go?.[0]) as
      | { shading?: unknown; baseColor?: unknown; atmosphere?: unknown; light?: unknown; viewControl?: Record<string, unknown> }
      | undefined;
    const zr = chartRef.current?.getZr() as unknown as {
      animation?: { _running?: boolean; _stillFrameAccum?: number };
    } | null;
    w.__mapDebugGlobe = {
      globeKeys: go ? Object.keys(go) : null,
      shading: g0?.shading ?? null,
      baseColor: g0?.baseColor ?? null,
      atmosphere: g0?.atmosphere ?? null,
      light: g0?.light ?? null,
      vc: g0?.viewControl ?? null,
      zrAnimRunning: zr?.animation?._running ?? null,
      zrStillAccum: zr?.animation?._stillFrameAccum ?? null,
    };
  }

  const toggleIndicator = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="relative h-full w-full overflow-hidden text-text">
      <div ref={ref} className="h-full w-full" />

      {selectedPt && (
        <div className="absolute right-4 top-16 w-52 rounded-card border border-border bg-surface/95 p-4 shadow-xl">
          <div className="flex items-start justify-between">
            <div className="text-sm font-semibold">{selectedPt.name}</div>
            <button
              className="text-muted hover:text-text"
              onClick={() => setSelectedPt(null)}
            >
              ×
            </button>
          </div>
          <div className="mt-2 text-lg font-semibold text-accent">
            {selectedPt.value.toLocaleString()}
            <span className="ml-1 text-xs font-normal text-muted">{selectedPt.unit}</span>
          </div>
          <div className="mt-1 text-xs text-muted">
            {selectedPt.city ? selectedPt.city + " · " : ""}
            {year} 年
          </div>
        </div>
      )}

      {/* 当前视域档位（深放大时附带焦点省名） */}
      <div className="absolute left-4 top-4 rounded-input border border-border bg-surface/80 px-2.5 py-1 text-xs text-accent">
        {LEVELS[zoomIdx].label}
        {zoomIdx >= 3 && focusName ? " · " + focusName : ""}
      </div>

      {/* 时间轴 */}
      <div className="absolute right-4 top-4 flex items-center gap-2 rounded-input border border-border bg-surface/80 px-3 py-1.5">
        <span className="text-xs text-muted">年份</span>
        <input
          type="range"
          min={years[0] ?? 2023}
          max={years[years.length - 1] ?? 2024}
          step={1}
          value={Math.min(Math.max(year, years[0] ?? 2023), years[years.length - 1] ?? 2024)}
          onChange={(e) => setYear(Number(e.target.value))}
          className="w-28 cursor-pointer"
          style={{ accentColor: "var(--accent)" }}
        />
        <span className="w-9 text-right text-xs font-semibold text-accent">{year}</span>
      </div>

      {/* 底部指标多选栏：可全部取消，只展示纯地图 */}
      <div className="absolute inset-x-0 bottom-0 border-t border-border bg-surface/90 backdrop-blur">
        <div className="flex items-center gap-1.5 overflow-x-auto px-3 py-2">
          <span className="shrink-0 text-xs text-muted">指标</span>
          {indicators.map((ind, i) => {
            const on = selected.has(ind.id);
            return (
              <button
                key={ind.id}
                onClick={() => toggleIndicator(ind.id)}
                className={cn(
                  "shrink-0 rounded-input border px-2.5 py-1 text-xs transition-colors",
                  on
                    ? "border-transparent text-[var(--accent-fg)]"
                    : "border-border text-muted hover:text-text",
                )}
                style={on ? { backgroundColor: cssVar("--series-" + ((i % 8) + 1)) } : undefined}
              >
                {ind.name}
                <span className="ml-1 opacity-70">{ind.unit}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
