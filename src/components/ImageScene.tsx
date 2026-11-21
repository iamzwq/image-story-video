import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { SANS, SERIF } from "../fonts";
import type { ImageScene as ImageSceneData, Motion } from "../types";

// 缓慢推拉/平移（Ken Burns），让静态图有镜头感。x/y 为百分比位移，放大 1.15 倍时 ±4% 不会露边
const MOTIONS: Record<Motion, { scale: [number, number]; x: [number, number]; y: [number, number] }> = {
  zoomIn: { scale: [1, 1.15], x: [0, 0], y: [0, 0] },
  zoomOut: { scale: [1.15, 1], x: [0, 0], y: [0, 0] },
  panLeft: { scale: [1.15, 1.15], x: [-4, 4], y: [0, 0] },
  panRight: { scale: [1.15, 1.15], x: [4, -4], y: [0, 0] },
  panUp: { scale: [1.15, 1.15], x: [0, 0], y: [-4, 4] },
  panDown: { scale: [1.15, 1.15], x: [0, 0], y: [4, -4] },
};

const Placeholder: React.FC<{ scene: ImageSceneData; index: number }> = ({ scene, index }) => {
  const { width, height } = useVideoConfig();
  const unit = Math.min(width, height) / 1080;
  const hue = (index * 37) % 360;
  const hint =
    scene.source === scene.id
      ? `占位图 · 出图后命名为 ${scene.id}.png 放进 images 文件夹`
      : `复用 ${scene.source} 的图片（${scene.source} 出图后自动显示）`;
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 40%, hsl(${hue} 26% 28%) 0%, hsl(${(hue + 40) % 360} 30% 9%) 78%)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: height * 0.3,
          left: 70 * unit,
          right: 70 * unit,
          textAlign: "center",
          color: "#f3e6cf",
        }}
      >
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 150 * unit, color: "rgba(255,255,255,0.16)" }}>
          {scene.source}
        </div>
        <div style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 64 * unit, marginTop: 8 * unit }}>
          {scene.visual || "画面待定"}
        </div>
        <div
          style={{
            fontFamily: SANS,
            fontWeight: 700,
            fontSize: 30 * unit,
            marginTop: 28 * unit,
            color: "rgba(255,255,255,0.5)",
          }}
        >
          {hint}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const ImageScene: React.FC<{ scene: ImageSceneData; index: number; durationInFrames: number }> = ({
  scene,
  index,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const motion = MOTIONS[scene.motion] ?? MOTIONS.zoomIn;
  const at = (range: [number, number]) =>
    interpolate(frame, [0, Math.max(1, durationInFrames)], range, {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${at(motion.scale)}) translate(${at(motion.x)}%, ${at(motion.y)}%)` }}>
        {scene.image ? (
          <Img src={staticFile(scene.image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <Placeholder scene={scene} index={index} />
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
