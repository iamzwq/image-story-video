import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SANS } from "../fonts";
import type { Caption } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const findActive = (captions: Caption[], t: number) => {
  let lo = 0;
  let hi = captions.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (captions[mid].start <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found >= 0 && t < captions[found].end ? found : -1;
};

const textWidth = (s: string) => [...s].reduce((w, ch) => w + (ch.charCodeAt(0) < 128 ? 0.55 : 1), 0);

export const Captions: React.FC<{ captions: Caption[] }> = ({ captions }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const index = findActive(captions, frame / fps);
  if (index < 0) {
    return null;
  }
  const caption = captions[index];
  const portrait = height > width;
  const unit = Math.min(width, height) / 1080;
  // 竖屏左右各留 10%，避开抖音等平台右侧的点赞/评论按钮
  const maxWidth = portrait ? width * 0.8 : width * 0.7;
  // 一条字幕始终保持一行：字数多时自动缩小字号
  const fontSize = Math.min((portrait ? 62 : 56) * unit, maxWidth / Math.max(textWidth(caption.text), 1));
  const local = frame - Math.round(caption.start * fps);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: portrait ? height * 0.655 : undefined,
        bottom: portrait ? undefined : height * 0.08,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 700,
          fontSize,
          lineHeight: 1.3,
          letterSpacing: unit,
          color: "#ffffff",
          whiteSpace: "nowrap",
          WebkitTextStroke: `${Math.round(fontSize * 0.16)}px rgba(0,0,0,0.9)`,
          paintOrder: "stroke fill",
          textShadow: `0 ${4 * unit}px ${12 * unit}px rgba(0,0,0,0.55)`,
          opacity: interpolate(local, [0, 3], [0, 1], clamp),
          transform: `scale(${interpolate(local, [0, 4], [0.94, 1], clamp)})`,
        }}
      >
        {caption.text}
      </div>
    </div>
  );
};
