import React from "react";
import { CalculateMetadataFunction, Composition, staticFile } from "remotion";
import episodes from "./episodes.json";
import { StoryVideo } from "./StoryVideo";
import type { StoryProps, Timeline } from "./types";

const calculateMetadata: CalculateMetadataFunction<StoryProps> = async ({ props, abortSignal }) => {
  const res = await fetch(staticFile(`episodes/${props.episode}/timeline.json`), {
    signal: abortSignal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`读取 episodes/${props.episode}/timeline.json 失败，请先运行 npm run voice -- ${props.episode}`);
  }
  const timeline = (await res.json()) as Timeline;
  return {
    durationInFrames: Math.max(1, Math.ceil(timeline.duration * timeline.fps)),
    fps: timeline.fps,
    width: timeline.width,
    height: timeline.height,
    defaultOutName: props.episode,
    props: { ...props, timeline },
  };
};

// 每一集对应一个合成（如 ep001），列表由 npm run voice 自动写入 src/episodes.json
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {episodes.map((ep) => (
        <Composition
          key={ep.id}
          id={`ep${ep.id}`}
          component={StoryVideo}
          durationInFrames={300}
          fps={30}
          width={1080}
          height={1920}
          defaultProps={{ episode: ep.id, timeline: null } as StoryProps}
          calculateMetadata={calculateMetadata}
        />
      ))}
    </>
  );
};
