import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Bgm } from "./components/Bgm";
import { Captions } from "./components/Captions";
import { ChapterCard } from "./components/ChapterCard";
import { ImageScene } from "./components/ImageScene";
import { Overlay } from "./components/Overlay";
import type { StoryProps } from "./types";

const FADE_SECONDS = 0.4;

const FadeIn: React.FC<{ frames: number; children: React.ReactNode }> = ({ frames, children }) => {
  const frame = useCurrentFrame();
  const opacity =
    frames > 0 ? interpolate(frame, [0, frames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

export const StoryVideo: React.FC<StoryProps> = ({ timeline }) => {
  const { fps } = useVideoConfig();
  if (!timeline) {
    return <AbsoluteFill style={{ backgroundColor: "#000" }} />;
  }
  const fade = Math.round(FADE_SECONDS * fps);
  const last = timeline.scenes.length - 1;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0d0b09" }}>
      {timeline.scenes.map((scene, i) => {
        const from = Math.round(scene.start * fps);
        const length = Math.max(1, Math.round(scene.end * fps) - from);
        // 每个画面多停留一个淡入时长，让下一个画面叠在它上面淡入，形成交叉淡化
        const total = length + (i < last ? fade : 0);
        return (
          <Sequence key={scene.id} name={scene.id} from={from} durationInFrames={total} premountFor={fps}>
            <FadeIn frames={i === 0 ? 0 : fade}>
              {scene.type === "chapter" ? (
                <ChapterCard scene={scene} />
              ) : (
                <ImageScene scene={scene} index={i} durationInFrames={total} />
              )}
            </FadeIn>
          </Sequence>
        );
      })}
      <Overlay timeline={timeline} />
      <Captions captions={timeline.captions} />
      <Audio src={staticFile(timeline.audio)} name="配音" />
      {timeline.bgm ? <Bgm src={timeline.bgm.src} volume={timeline.bgm.volume} /> : null}
    </AbsoluteFill>
  );
};
