import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SANS, SERIF } from "../fonts";
import type { Timeline } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// 顶部常驻标题 + 当前章节标签 + 上下渐变遮罩（保证文字在任何图片上都清晰）
export const Overlay: React.FC<{ timeline: Timeline }> = ({ timeline }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const unit = Math.min(width, height) / 1080;
  const portrait = height > width;
  const scenes = timeline.scenes;

  // 章节卡出现时把标题和遮罩淡出
  let chapterCover = 0;
  for (const s of scenes) {
    if (s.type !== "chapter" || s.end - s.start < 0.6 || t < s.start || t > s.end + 0.4) {
      continue;
    }
    chapterCover = Math.max(
      chapterCover,
      interpolate(t, [s.start, s.start + 0.4, s.end - 0.1, s.end + 0.4], [0, 1, 1, 0], clamp),
    );
  }
  const titleOpacity = (1 - chapterCover) * interpolate(t, [0, 0.6], [0, 1], clamp);

  let current = -1;
  for (let i = 0; i < scenes.length && scenes[i].start <= t; i++) {
    current = i;
  }
  const scene = current >= 0 ? scenes[current] : null;
  const chapter = scene && scene.type === "image" ? scene.chapter : null;
  // 第一个章节之前（开场）显示副标题，之后显示当前章节
  const label = scene && scene.type === "image" ? (chapter ?? (timeline.subtitle || null)) : null;
  let labelStart = scene ? scene.start : 0;
  for (let i = current; i >= 0; i--) {
    const s = scenes[i];
    if (s.type !== "image" || s.chapter !== chapter) {
      break;
    }
    labelStart = s.start;
  }
  const labelIn = interpolate(t - labelStart, [0.2, 0.8], [0, 1], clamp);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <AbsoluteFill
        style={{
          opacity: 1 - chapterCover,
          background: `linear-gradient(to bottom, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0) ${portrait ? 26 : 30}%, rgba(0,0,0,0) ${portrait ? 52 : 55}%, rgba(0,0,0,0.72) 100%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: portrait ? height * 0.105 : height * 0.06,
          left: 60 * unit,
          right: 60 * unit,
          textAlign: "center",
          opacity: titleOpacity,
        }}
      >
        <div
          style={{
            fontFamily: SERIF,
            fontWeight: 700,
            fontSize: (portrait ? 78 : 60) * unit,
            color: "#ffffff",
            letterSpacing: 4 * unit,
            textShadow: `0 ${4 * unit}px ${20 * unit}px rgba(0,0,0,0.65)`,
          }}
        >
          {timeline.title}
        </div>
        {label ? (
          <div style={{ marginTop: 22 * unit, opacity: labelIn, transform: `translateY(${(1 - labelIn) * 12 * unit}px)` }}>
            <span
              style={{
                display: "inline-block",
                fontFamily: SANS,
                fontWeight: 700,
                fontSize: (portrait ? 34 : 28) * unit,
                color: "#efd9a7",
                padding: `${10 * unit}px ${28 * unit}px`,
                borderRadius: 999,
                border: `${2 * unit}px solid rgba(217,178,111,0.75)`,
                background: "rgba(12,9,6,0.55)",
              }}
            >
              {label}
            </span>
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
