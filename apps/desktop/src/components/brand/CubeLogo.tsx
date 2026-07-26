import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

interface CubeLogoProps {
  className?: string;
  /** 立方体尺寸（px），默认 28 */
  size?: number;
  /** AI 运行态：弹跳翻面 */
  running?: boolean;
}

/**
 * 景明研环品牌 logo — 3D 毛玻璃立方体（无球）。
 */
export function CubeLogo({ className, size = 28, running = false }: CubeLogoProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const cubeRef = useRef<HTMLDivElement>(null);
  const animRef = useRef(0);
  const startRef = useRef(performance.now());

  const H = size / 2;
  const S = size / 72;

  useEffect(() => {
    const wrapper = wrapperRef.current;
    const cube = cubeRef.current;
    if (!wrapper || !cube) return;

    const tick = (now: number) => {
      const e = (now - startRef.current) / 1000;
      const bx = -8 + 15 * Math.sin(e * 0.3);
      const by = 8 + 20 * Math.sin(e * 0.4);

      if (running) {
        const d = 0.45;
        const t = (e / d) % 1;
        const bounce = Math.sin(t * Math.PI) * 22 * S;
        const fp = Math.min(t * 2, 1);
        const fe = 1 - (1 - fp) ** 1.5;
        const fi = Math.floor(e / d);
        const tf = Math.floor(e / d);
        const tx = Math.ceil(tf / 2) * 90 * (tf % 4 < 2 ? 1 : -1) + (fi % 2 === 0 ? fe * 90 : 0);
        const tz = Math.floor(tf / 2) * 90 * (tf % 4 < 3 ? 1 : -1) + (fi % 2 === 1 ? fe * 90 : 0);

        wrapper.style.transform = `translateY(${-bounce}px)`;
        cube.style.transform = `rotateX(${bx + tx}deg) rotateY(${by + 10 * Math.sin(e * 1.3)}deg) rotateZ(${tz}deg)`;
      } else {
        wrapper.style.transform = "translateY(0px)";
        cube.style.transform = `rotateX(${bx}deg) rotateY(${by}deg)`;
      }
      animRef.current = requestAnimationFrame(tick);
    };

    startRef.current = performance.now();
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [size, running]);

  // ── 六个面的 3D 变换 ──
  const tfs = [
    `translateZ(${H}px)`,
    `rotateY(90deg) translateZ(${H}px)`,
    `rotateY(-90deg) translateZ(${H}px)`,
    `rotateX(90deg) translateZ(${H}px)`,
    `rotateX(-90deg) translateZ(${H}px)`,
    `rotateY(180deg) translateZ(${H}px)`,
  ];

  return (
    <div
      ref={wrapperRef}
      className={cn("relative shrink-0", className)}
      style={{ width: size, height: size, perspective: size * 11, zIndex: 5, transformStyle: "flat" }}
    >
      <div
        ref={cubeRef}
        className="absolute inset-0"
        style={{
          transformStyle: "preserve-3d",
          willChange: "transform",
        }}
      >
        {/* ── 六个毛玻璃面 ── */}
        {tfs.map((tf, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              inset: 0,
              transform: tf,
              backfaceVisibility: "hidden",
            }}
          >
            {/* 玻璃底色 */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: "var(--accent)",
                opacity: 0.08,
                borderRadius: "0.5px",
                pointerEvents: "none",
              }}
            />
            {/* 边框 */}
            <div
              style={{
                position: "absolute",
                inset: -0.5,
                border: "0.6px solid color-mix(in srgb, var(--accent) 28%, transparent)",
                borderRadius: "0.5px",
                pointerEvents: "none",
              }}
            />
            {/* 网格纹理 */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                backgroundImage: [
                  `linear-gradient(color-mix(in srgb, var(--accent) 5%, transparent) 1px, transparent 1px)`,
                  `linear-gradient(90deg, color-mix(in srgb, var(--accent) 4%, transparent) 1px, transparent 1px)`,
                ].join(","),
                backgroundSize: `${Math.max(4, size / 12)}px ${Math.max(4, size / 12)}px`,
                pointerEvents: "none",
              }}
            />
            {/* 渐变高光 */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: `linear-gradient(138deg, color-mix(in srgb, var(--accent) 18%, transparent) 0%, color-mix(in srgb, var(--accent) 5%, transparent) 28%, transparent 52%)`,
                pointerEvents: "none",
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
