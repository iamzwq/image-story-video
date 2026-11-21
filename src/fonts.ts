import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

// 思源黑体 / 思源宋体（SIL OFL 协议，可免费商用）。微软雅黑等系统字体商用需要授权，所以不用。
loadFont({ family: "StorySans", url: staticFile("fonts/NotoSansSC-Bold.otf"), weight: "700" });
loadFont({ family: "StorySerif", url: staticFile("fonts/NotoSerifSC-Bold.otf"), weight: "700" });

export const SANS = '"StorySans", sans-serif';
export const SERIF = '"StorySerif", serif';
