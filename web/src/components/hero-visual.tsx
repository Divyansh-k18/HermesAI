"use client";

import dynamic from "next/dynamic";
import { useSyncExternalStore } from "react";

/** Flat version of the hero: shown while the 3D scene loads and on devices without WebGL. */
function HeroFallback() {
  const nodes = Array.from({ length: 7 }, (_, i) => {
    const angle = (i / 7) * Math.PI * 2 - Math.PI / 2;
    return { x: 200 + Math.cos(angle) * 140, y: 170 + Math.sin(angle) * 105, approval: i === 2 };
  });
  return (
    <svg viewBox="0 0 400 340" className="h-full w-full" aria-hidden>
      {nodes.map((node, i) => {
        const next = nodes[(i + 1) % nodes.length];
        return (
          <g key={i} stroke="var(--line-strong)">
            <line x1="200" y1="170" x2={node.x} y2={node.y} />
            <line x1={node.x} y1={node.y} x2={next.x} y2={next.y} />
          </g>
        );
      })}
      <circle cx="200" cy="170" r="34" fill="var(--surface-2)" stroke="var(--accent)" />
      {nodes.map((node, i) => (
        <rect
          key={i}
          x={node.x - 7}
          y={node.y - 7}
          width="14"
          height="14"
          transform={`rotate(45 ${node.x} ${node.y})`}
          fill={node.approval ? "var(--warning)" : "var(--text-muted)"}
        />
      ))}
    </svg>
  );
}

const HeroScene = dynamic(() => import("@/components/hero-scene"), {
  ssr: false,
  loading: () => <HeroFallback />,
});

let webglSupport: boolean | null = null;
function supportsWebGL(): boolean {
  if (webglSupport === null) {
    try {
      const canvas = document.createElement("canvas");
      webglSupport = Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
    } catch {
      webglSupport = false;
    }
  }
  return webglSupport;
}

const noopSubscribe = () => () => {};

export function HeroVisual() {
  const canRender3D = useSyncExternalStore(noopSubscribe, supportsWebGL, () => false);
  return (
    <div className="relative h-[300px] w-full sm:h-[380px] lg:h-[440px]" data-hero={canRender3D ? "3d" : "flat"}>
      {canRender3D ? <HeroScene /> : <HeroFallback />}
    </div>
  );
}
