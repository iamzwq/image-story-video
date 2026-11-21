export type Motion = "zoomIn" | "zoomOut" | "panLeft" | "panRight" | "panUp" | "panDown";

export type ImageScene = {
  id: string;
  type: "image";
  start: number;
  end: number;
  /** public/ 下的相对路径；还没出图时为 null，显示占位图 */
  image: string | null;
  /** 实际使用哪个分镜的图片（复用其它分镜时与 id 不同） */
  source: string;
  visual: string;
  motion: Motion;
  chapter: string | null;
};

export type ChapterScene = {
  id: string;
  type: "chapter";
  start: number;
  end: number;
  kicker: string;
  title: string;
};

export type Scene = ImageScene | ChapterScene;

export type Caption = {
  text: string;
  start: number;
  end: number;
};

/** 由 scripts/build_episode.py 生成的 public/episodes/<集数>/timeline.json，时间单位均为秒 */
export type Timeline = {
  version: number;
  episode: string;
  title: string;
  subtitle: string;
  width: number;
  height: number;
  fps: number;
  duration: number;
  audio: string;
  bgm: { src: string; volume: number } | null;
  scenes: Scene[];
  captions: Caption[];
};

export type StoryProps = {
  episode: string;
  timeline: Timeline | null;
};
