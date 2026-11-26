import React from "react";
import { AbsoluteFill, Img, useVideoConfig } from "remotion";
import { assetUrl } from "./assets";
import { MOTIONS } from "./components/ImageScene";
import { SANS, SERIF } from "./fonts";
import type { ImageScene, StoryProps } from "./types";

// 英文、数字大约半个字宽
const textWidth = (text: string) => [...text].reduce((sum, ch) => sum + (ch.charCodeAt(0) < 0x2000 ? 0.55 : 1), 0);

// 尽量少折行：从一行开始试，字号不小于 min 就用；折成几行时每行字数按平均算（配合 textWrap: balance）
const fitText = (text: string, avail: number, max: number, min: number) => {
  const total = Math.max(textWidth(text), 1);
  for (let lines = 1; ; lines++) {
    const size = Math.min(max, (avail * 0.92) / Math.ceil(total / lines));
    if (size >= min || total / lines <= 1) {
      return size;
    }
  }
};

// 封面：视频第一个画面（含开场镜头的初始缩放），叠一条黑底白字的标题栏
export const Cover: React.FC<StoryProps> = ({ timeline }) => {
  const { width, height } = useVideoConfig();
  const unit = Math.min(width, height) / 1080;
  if (!timeline) {
    return <AbsoluteFill style={{ backgroundColor: "#000" }} />;
  }
  const first = timeline.scenes.find((s): s is ImageScene => s.type === "image" && Boolean(s.image));
  const motion = first ? (MOTIONS[first.motion] ?? MOTIONS.zoomIn) : null;
  const avail = width - 120 * unit;
  const titleSize = fitText(timeline.title, avail, 132 * unit, 84 * unit);
  const subtitleSize = fitText(timeline.subtitle, avail, 50 * unit, 36 * unit);

  return (
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, #3b2b1b 0%, #18110b 55%, #070504 100%)" }}>
      {first?.image && motion ? (
        <AbsoluteFill
          style={{ transform: `scale(${motion.scale[0]}) translate(${motion.x[0]}%, ${motion.y[0]}%)` }}
        >
          <Img src={assetUrl(first.image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </AbsoluteFill>
      ) : null}
      {/* 标题栏放在画面中部偏下：在 3:4 等裁切预览里也能完整显示 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: height * 0.6,
          transform: "translateY(-50%)",
          padding: `${56 * unit}px ${60 * unit}px`,
          background: "rgba(0,0,0,0.86)",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontFamily: SERIF,
            fontWeight: 700,
            fontSize: titleSize,
            lineHeight: 1.3,
            color: "#ffffff",
            letterSpacing: 0.04 * titleSize,
            textWrap: "balance",
          }}
        >
          {timeline.title}
        </div>
        {timeline.subtitle ? (
          <div
            style={{
              marginTop: 24 * unit,
              fontFamily: SANS,
              fontWeight: 700,
              fontSize: subtitleSize,
              lineHeight: 1.4,
              color: "rgba(255,255,255,0.82)",
              textWrap: "balance",
            }}
          >
            {timeline.subtitle}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
