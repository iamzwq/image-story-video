import { Player } from "@remotion/player";
import React, { useMemo } from "react";
import { StoryVideo } from "../../src/StoryVideo";
import type { Timeline } from "../../src/types";

// 和导出用的是同一个视频模板（src/StoryVideo.tsx），预览看到的就是成片的样子
export const Preview: React.FC<{ episode: string; timeline: Timeline; version: string }> = ({
  episode,
  timeline,
  version,
}) => {
  // 时间线文件变了（version 变）才换新的 props，避免轮询刷新时打断播放
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const inputProps = useMemo(() => ({ episode, timeline }), [episode, version]);
  const portrait = timeline.height > timeline.width;
  return (
    <div
      className="mx-auto w-full overflow-hidden rounded-base border-2 border-ink bg-black max-lg:max-w-[320px]!"
      style={{
        aspectRatio: `${timeline.width} / ${timeline.height}`,
        maxWidth: portrait ? `calc(66vh * ${timeline.width} / ${timeline.height})` : undefined,
      }}
    >
      <Player
        key={version}
        component={StoryVideo}
        inputProps={inputProps}
        durationInFrames={Math.max(1, Math.ceil(timeline.duration * timeline.fps))}
        fps={timeline.fps}
        compositionWidth={timeline.width}
        compositionHeight={timeline.height}
        controls
        clickToPlay
        allowFullscreen
        doubleClickToFullscreen
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
};
