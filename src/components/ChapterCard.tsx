import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SERIF } from "../fonts";
import type { ChapterScene } from "../types";

// 按中文逗号断行（去掉行尾标点），并根据最长一行自动缩小字号，避免标题被折成奇怪的两行
const splitTitle = (title: string) =>
  title
    .split(/(?<=[，,：:])/)
    .map((s) => s.replace(/[，,：:]$/, "").trim())
    .filter((s) => s.length > 0);

export const ChapterCard: React.FC<{ scene: ChapterScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const unit = Math.min(width, height) / 1080;
  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: Math.round(fps * 0.8) });
  const titleEnter = spring({
    frame: frame - Math.round(fps * 0.2),
    fps,
    config: { damping: 200 },
    durationInFrames: Math.round(fps * 0.8),
  });

  const lines = splitTitle(scene.title);
  const longest = Math.max(...lines.map((l) => l.length));
  const titleSize = Math.min(92 * unit, (width - 140 * unit) / Math.max(longest, 1));

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at 50% 45%, #3b2b1b 0%, #18110b 55%, #070504 100%)",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ textAlign: "center", transform: `translateY(${-height * 0.02}px)` }}>
        {scene.kicker ? (
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 700,
              fontSize: 60 * unit,
              color: "#d9b26f",
              letterSpacing: 16 * unit,
              paddingLeft: 16 * unit,
              opacity: enter,
              transform: `translateY(${(1 - enter) * 24 * unit}px)`,
            }}
          >
            {scene.kicker}
          </div>
        ) : null}
        <div
          style={{
            height: 3 * unit,
            width: interpolate(enter, [0, 1], [0, 280 * unit]),
            background: "linear-gradient(90deg, transparent, #d9b26f, transparent)",
            margin: `${36 * unit}px auto`,
          }}
        />
        <div
          style={{
            fontFamily: SERIF,
            fontWeight: 700,
            fontSize: titleSize,
            lineHeight: 1.4,
            color: "#f6efe3",
            opacity: titleEnter,
            transform: `translateY(${(1 - titleEnter) * 30 * unit}px)`,
            textShadow: "0 6px 30px rgba(0,0,0,0.6)",
          }}
        >
          {lines.map((line) => (
            <div key={line} style={{ whiteSpace: "nowrap" }}>
              {line}
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
