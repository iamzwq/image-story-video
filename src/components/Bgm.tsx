import { Audio } from "@remotion/media";
import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { assetUrl } from "../assets";

// 背景音乐：循环播放，开头 2 秒淡入、结尾 3 秒淡出
export const Bgm: React.FC<{ src: string; volume: number }> = ({ src, volume }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const fadeIn = fps * 2;
  const fadeOut = fps * 3;
  const level =
    durationInFrames > fadeIn + fadeOut + 1
      ? interpolate(frame, [0, fadeIn, durationInFrames - fadeOut, durationInFrames], [0, volume, volume, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : volume;
  return <Audio src={assetUrl(src)} volume={level} loop name="背景音乐" />;
};
