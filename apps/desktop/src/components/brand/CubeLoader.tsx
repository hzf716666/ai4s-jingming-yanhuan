import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

interface CubeLoaderProps {
  /** 容器尺寸（默认 280px） */
  size?: number;
  /** AI 运行态：立方体弹跳翻转 + 光晕脉冲 */
  running?: boolean;
  /** 进度值 0-100，传入则显示进度条 */
  progress?: number;
  /** 附加类名 */
  className?: string;
}

const CUBE_SIZE = 72;
const HALF_CUBE = 36;

/**
 * 景明研环 — 3D 立方体加载动画（无球）。
 *
 * - 静止态：立方体缓慢自转
 * - 运行态：原地弹跳 + 翻面旋转 + 光晕脉冲
 * - 可选的进度条显示
 */
export function CubeLoader({
  size = 280,
  running = false,
  progress,
  className,
}: CubeLoaderProps) {
  const cubeRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const glow1Ref = useRef<HTMLDivElement>(null);
  const glow2Ref = useRef<HTMLDivElement>(null);
  const fillRef = useRef<HTMLSpanElement>(null);
  const numRef = useRef<HTMLSpanElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const animRef = useRef<number>(0);
  const startTimeRef = useRef<number>(performance.now());

  // 进度渲染
  useEffect(() => {
    if (progress !== undefined && fillRef.current && numRef.current) {
      const clamped = Math.max(0, Math.min(100, progress));
      fillRef.current.style.width = clamped + "%";
      numRef.current.textContent = clamped + "%";
    }
  }, [progress]);

  // 动画循环
  useEffect(() => {
    const cube = cubeRef.current;
    const wrapper = wrapperRef.current;
    const g1 = glow1Ref.current;
    const g2 = glow2Ref.current;

    if (!cube || !wrapper || !g1 || !g2) return;

    const animate = (now: number) => {
      const elapsed = (now - startTimeRef.current) / 1000;

      const baseRotX = -8 + 15 * Math.sin(elapsed * 0.3);
      const baseRotY = 8 + 20 * Math.sin(elapsed * 0.4);

      if (running) {
        const cycleDuration = 0.45;
        const bounceHeight = 22;
        const flipDeg = 90;

        const t = (elapsed / cycleDuration) % 1;
        const bounce = Math.sin(t * Math.PI) * bounceHeight;

        const flipProgress = Math.min(t * 2, 1);
        const flipEased = 1 - Math.pow(1 - flipProgress, 1.5);

        const flipIndex = Math.floor(elapsed / cycleDuration);
        const flipAxis = flipIndex % 2;
        const currentFlip = flipEased * flipDeg;

        const totalFlips = Math.floor(elapsed / cycleDuration);
        const totalFlipX =
          Math.ceil(totalFlips / 2) * flipDeg * (totalFlips % 4 < 2 ? 1 : -1);
        const totalFlipZ =
          Math.floor(totalFlips / 2) * flipDeg * (totalFlips % 4 < 3 ? 1 : -1);

        const extraFlipX = flipAxis === 0 ? currentFlip : 0;
        const extraFlipZ = flipAxis === 1 ? currentFlip : 0;

        const totalX = totalFlipX + extraFlipX;
        const totalZ = totalFlipZ + extraFlipZ;

        wrapper.style.transform = `translateY(${-bounce}px)`;
        cube.style.transform = `
          rotateX(${baseRotX + totalX}deg)
          rotateY(${baseRotY + 10 * Math.sin(elapsed * 1.3)}deg)
          rotateZ(${totalZ}deg)
        `;

        const glowPulse = 0.4 + 0.5 * Math.sin(t * Math.PI);
        const s1 = 0.9 + 0.15 * Math.sin(elapsed * 2.0);
        const s2 = 0.9 + 0.15 * Math.sin((elapsed + 0.3) * 2.0);
        g1.style.opacity = String(glowPulse * 0.5);
        g1.style.transform = `scale(${s1})`;
        g2.style.opacity = String(glowPulse * 0.35);
        g2.style.transform = `scale(${s2})`;
      } else {
        wrapper.style.transform = "translateY(0px)";
        cube.style.transform = `
          rotateX(${baseRotX}deg)
          rotateY(${baseRotY}deg)
        `;

        g1.style.opacity = "0.08";
        g1.style.transform = `scale(${0.95 + 0.03 * Math.sin(elapsed * 0.7)})`;
        g2.style.opacity = "0.05";
        g2.style.transform = `scale(${0.95 + 0.03 * Math.sin(elapsed * 0.7 + 1)})`;
      }

      animRef.current = requestAnimationFrame(animate);
    };

    startTimeRef.current = performance.now();
    animRef.current = requestAnimationFrame(animate);

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [running]);

  const faceClass =
    "absolute inset-0 border border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-[8px] overflow-hidden";

  return (
    <div
      className={cn("relative flex flex-col items-center justify-center", className)}
      style={{
        width: size,
        height: size * 0.78,
        perspective: 800,
        isolation: "isolate",
      }}
    >
      <style>{`
        .cube-loader-glass {
          --glass-bg: color-mix(in srgb, var(--accent) 8%, transparent);
          --glass-border: color-mix(in srgb, var(--accent) 22%, transparent);
          --glass-highlight: color-mix(in srgb, var(--accent) 15%, transparent);
          --glow-color: color-mix(in srgb, var(--accent) 50%, transparent);
          --glow-color-2: color-mix(in srgb, var(--accent) 30%, transparent);
        }
      `}</style>

      {/* ── 立方体容器（Y 轴弹跳） ── */}
      <div
        ref={wrapperRef}
        className="cube-loader-glass absolute"
        style={{
          width: CUBE_SIZE,
          height: CUBE_SIZE,
          left: "50%",
          top: "50%",
          marginLeft: -HALF_CUBE,
          marginTop: -(HALF_CUBE + 10),
          transform: "translateY(0px)",
          willChange: "transform",
          zIndex: 5,
        }}
      >
        {/* ─ 立方体 ── */}
        <div
          ref={cubeRef}
          className="relative size-full"
          style={{
            transformStyle: "preserve-3d",
            willChange: "transform",
          }}
        >
          {/* 六个毛玻璃面 */}
          <span
            className={cn(faceClass, "cube-loader-glass")}
            style={{
              transform: `translateZ(${HALF_CUBE}px)`,
              boxShadow: "inset 0 0 20px color-mix(in srgb, var(--accent) 4%, transparent), 0 0 8px color-mix(in srgb, var(--accent) 6%, transparent)",
            }}
          />
          <span
            className={cn(faceClass, "cube-loader-glass")}
            style={{ transform: `rotateY(90deg) translateZ(${HALF_CUBE}px)` }}
          />
          <span
            className={cn(faceClass, "cube-loader-glass")}
            style={{ transform: `rotateY(-90deg) translateZ(${HALF_CUBE}px)` }}
          />
          <span
            className={cn(faceClass, "cube-loader-glass")}
            style={{
              transform: `rotateX(90deg) translateZ(${HALF_CUBE}px)`,
              background: "color-mix(in srgb, var(--accent) 10%, transparent)",
            }}
          />
          <span
            className={cn(faceClass, "cube-loader-glass")}
            style={{
              transform: `rotateX(-90deg) translateZ(${HALF_CUBE}px)`,
              background: "color-mix(in srgb, var(--accent) 4%, transparent)",
            }}
          />
          <span
            className={cn(faceClass, "cube-loader-glass")}
            style={{ transform: `rotateY(180deg) translateZ(${HALF_CUBE}px)` }}
          />
        </div>
      </div>

      {/* ── 光晕环 ── */}
      <div
        ref={glow1Ref}
        className="absolute pointer-events-none rounded-full cube-loader-glass"
        style={{
          width: 120,
          height: 120,
          left: "50%",
          top: "50%",
          marginLeft: -60,
          marginTop: -60,
          background:
            "radial-gradient(circle at center, " +
            "var(--glow-color) 0%, " +
            "var(--glow-color-2) 30%, " +
            "transparent 70%)",
          opacity: 0.08,
          transform: "scale(0.95)",
          willChange: "transform, opacity",
          zIndex: 1,
          transition: running ? "none" : "opacity 0.5s ease",
        }}
      />
      <div
        ref={glow2Ref}
        className="absolute pointer-events-none rounded-full cube-loader-glass"
        style={{
          width: 160,
          height: 160,
          left: "50%",
          top: "50%",
          marginLeft: -80,
          marginTop: -80,
          background:
            "radial-gradient(circle at center, " +
            "color-mix(in srgb, var(--accent) 20%, transparent) 0%, " +
            "transparent 60%)",
          opacity: 0.05,
          transform: "scale(0.95)",
          willChange: "transform, opacity",
          zIndex: 1,
          transition: running ? "none" : "opacity 0.8s ease",
        }}
      />

      {/* ── 进度条 ─ */}
      <div
        className="absolute flex items-center gap-2"
        style={{
          left: "50%",
          bottom: 20,
          transform: "translateX(-50%)",
          width: 168,
          zIndex: 8,
        }}
      >
        <span
          ref={labelRef}
          className="text-[10px] uppercase tracking-wider"
          style={{
            color: "color-mix(in srgb, var(--muted) 80%, transparent)",
            fontFamily:
              'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          }}
        >
          Thinking
        </span>
        <span
          className="block flex-1 h-1 rounded-full overflow-hidden"
          style={{
            border: "1px solid color-mix(in srgb, var(--muted) 20%, transparent)",
            background: "color-mix(in srgb, var(--muted) 8%, transparent)",
          }}
        >
          <span
            ref={fillRef}
            className="block h-full rounded-full transition-[width] duration-[280ms]"
            style={{
              width: "0%",
              background: `linear-gradient(90deg, color-mix(in srgb, var(--accent) 70%, transparent), color-mix(in srgb, var(--accent) 80%, transparent))`,
            }}
          />
        </span>
        <span
          ref={numRef}
          className="text-[10px] tracking-wider min-w-[28px] text-center"
          style={{
            color: "color-mix(in srgb, var(--muted) 70%, transparent)",
            fontFamily:
              'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          }}
        >
          0%
        </span>
      </div>
    </div>
  );
}
