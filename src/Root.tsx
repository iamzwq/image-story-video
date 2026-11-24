import React from "react";
import { CalculateMetadataFunction, Composition, staticFile, Still } from "remotion";
import { Cover } from "./Cover";
import episodes from "./episodes.json";
import { StoryVideo } from "./StoryVideo";
import type { StoryProps, Timeline } from "./types";

const loadTimeline = async (episode: string, signal: AbortSignal) => {
  const res = await fetch(staticFile(`episodes/${episode}/timeline.json`), { signal, cache: "no-store" });
  if (!res.ok) {
    throw new Error(`读取 episodes/${episode}/timeline.json 失败，请先运行 npm run voice -- ${episode}`);
  }
  return (await res.json()) as Timeline;
};

const calculateMetadata: CalculateMetadataFunction<StoryProps> = async ({ props, abortSignal }) => {
  const timeline = await loadTimeline(props.episode, abortSignal);
  return {
    durationInFrames: Math.max(1, Math.ceil(timeline.duration * timeline.fps)),
    fps: timeline.fps,
    width: timeline.width,
    height: timeline.height,
    defaultOutName: props.episode,
    props: { ...props, timeline },
  };
};

const calculateCoverMetadata: CalculateMetadataFunction<StoryProps> = async ({ props, abortSignal }) => {
  const timeline = await loadTimeline(props.episode, abortSignal);
  return {
    width: timeline.width,
    height: timeline.height,
    defaultOutName: `${props.episode}-cover`,
    props: { ...props, timeline },
  };
};

// 每一集对应一个视频（如 ep001）和一张封面（如 ep001-cover），列表由 npm run voice 自动写入 src/episodes.json
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {episodes.map((ep) => (
        <React.Fragment key={ep.id}>
          <Composition
            id={`ep${ep.id}`}
            component={StoryVideo}
            durationInFrames={300}
            fps={30}
            width={1080}
            height={1920}
            defaultProps={{ episode: ep.id, timeline: null } as StoryProps}
            calculateMetadata={calculateMetadata}
          />
          <Still
            id={`ep${ep.id}-cover`}
            component={Cover}
            width={1080}
            height={1920}
            defaultProps={{ episode: ep.id, timeline: null } as StoryProps}
            calculateMetadata={calculateCoverMetadata}
          />
        </React.Fragment>
      ))}
    </>
  );
};
