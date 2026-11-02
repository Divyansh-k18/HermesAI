"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import * as THREE from "three";

/*
  The Hermes mark in 3D: a faceted core (the orchestrator) ringed by step nodes, joined by links that
  carry small pulses of data inward. One node is amber: the human approval checkpoint, using the same
  color meaning as the product. Motion is slow and stops entirely for reduced-motion users or when the
  scene is off screen.
*/

const ACCENT = new THREE.Color("#4f7cff");
const AMBER = new THREE.Color("#d9a441");
const NODE_COUNT = 7;
const APPROVAL_NODE = 2;

function subscribeReducedMotion(callback: () => void) {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

function usePrefersReducedMotion() {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
}

function useNodePositions() {
  return useMemo(
    () =>
      Array.from({ length: NODE_COUNT }, (_, i) => {
        const angle = (i / NODE_COUNT) * Math.PI * 2;
        const radius = 2.15 + (i % 2) * 0.4;
        const height = Math.sin(i * 1.9) * 0.75;
        return new THREE.Vector3(Math.cos(angle) * radius, height, Math.sin(angle) * radius);
      }),
    [],
  );
}

function Core() {
  const shell = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (!shell.current) return;
    shell.current.rotation.y -= delta * 0.12;
    shell.current.rotation.x += delta * 0.04;
  });
  return (
    <group>
      <mesh>
        <icosahedronGeometry args={[0.62, 1]} />
        <meshStandardMaterial
          color="#232a38"
          metalness={0.55}
          roughness={0.4}
          emissive={ACCENT}
          emissiveIntensity={0.05}
          flatShading
        />
      </mesh>
      <mesh ref={shell}>
        <icosahedronGeometry args={[0.92, 1]} />
        <meshBasicMaterial color={ACCENT} wireframe transparent opacity={0.16} />
      </mesh>
    </group>
  );
}

function Nodes({ positions }: { positions: THREE.Vector3[] }) {
  return (
    <>
      {positions.map((position, i) => (
        <mesh key={i} position={position}>
          <octahedronGeometry args={[i === APPROVAL_NODE ? 0.16 : 0.12, 0]} />
          <meshStandardMaterial
            color={i === APPROVAL_NODE ? AMBER : "#c4cad3"}
            emissive={i === APPROVAL_NODE ? AMBER : new THREE.Color("#000000")}
            emissiveIntensity={i === APPROVAL_NODE ? 0.35 : 0}
            metalness={0.25}
            roughness={0.45}
            flatShading
          />
        </mesh>
      ))}
    </>
  );
}

function Links({ positions }: { positions: THREE.Vector3[] }) {
  const geometry = useMemo(() => {
    const points: THREE.Vector3[] = [];
    positions.forEach((position, i) => {
      points.push(new THREE.Vector3(0, 0, 0), position);
      points.push(position, positions[(i + 1) % positions.length]);
    });
    return new THREE.BufferGeometry().setFromPoints(points);
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#59616e" transparent opacity={0.5} />
    </lineSegments>
  );
}

function Pulses({ positions }: { positions: THREE.Vector3[] }) {
  const meshes = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    positions.forEach((position, i) => {
      const mesh = meshes.current[i];
      if (!mesh) return;
      // Each link carries one pulse from its node into the core, staggered so they never move in lockstep.
      const progress = (t * 0.32 + i / positions.length) % 1;
      mesh.position.copy(position).multiplyScalar(1 - progress);
      const material = mesh.material as THREE.MeshBasicMaterial;
      material.opacity = Math.sin(progress * Math.PI) * 0.95;
    });
  });
  return (
    <>
      {positions.map((_, i) => (
        <mesh key={i} ref={(element) => void (meshes.current[i] = element)}>
          <sphereGeometry args={[0.045, 12, 12]} />
          <meshBasicMaterial color={i === APPROVAL_NODE ? AMBER : ACCENT} transparent opacity={0} />
        </mesh>
      ))}
    </>
  );
}

/** Slow orbit, plus a small tilt toward the pointer so the object feels attentive rather than spinning. */
function Rig({ children, still }: { children: React.ReactNode; still: boolean }) {
  const group = useRef<THREE.Group>(null);
  useFrame(({ pointer }, delta) => {
    const g = group.current;
    if (!g || still) return;
    g.rotation.y += delta * 0.07;
    g.rotation.x = THREE.MathUtils.lerp(g.rotation.x, 0.28 + pointer.y * 0.18, 0.04);
    g.rotation.z = THREE.MathUtils.lerp(g.rotation.z, -pointer.x * 0.1, 0.04);
  });
  return (
    <group ref={group} rotation={[0.28, 0.6, 0]}>
      {children}
    </group>
  );
}

export default function HeroScene() {
  const container = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const reducedMotion = usePrefersReducedMotion();
  const positions = useNodePositions();

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.05 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const animate = visible && !reducedMotion;

  return (
    <div ref={container} className="h-full w-full" aria-hidden>
      <Canvas
        // "demand" renders a single frame and then stops: used off screen and for reduced motion.
        frameloop={animate ? "always" : "demand"}
        dpr={[1, 1.75]}
        camera={{ position: [0, 1.3, 7.6], fov: 40 }}
        gl={{ antialias: true, powerPreference: "low-power", alpha: true }}
      >
        <ambientLight intensity={0.3} />
        {/* Neutral key and rim light show the facets. A faint blue fill keeps the brand accent. */}
        <directionalLight position={[3, 4, 5]} intensity={1.4} />
        <directionalLight position={[-4, 2, -3]} intensity={0.6} color="#dfe6f5" />
        <pointLight position={[-3, -1, 2]} intensity={1.6} color={ACCENT} distance={8} />
        <Rig still={!animate}>
          <Core />
          <Links positions={positions} />
          <Nodes positions={positions} />
          {!reducedMotion && <Pulses positions={positions} />}
        </Rig>
      </Canvas>
    </div>
  );
}
