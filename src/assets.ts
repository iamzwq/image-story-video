import { staticFile } from "remotion";

// timeline.json 里的路径相对 public/，交给 staticFile；网页版预览会换成以 / 开头、带版本号的网址，
// 这样重画图片或重新配音后，浏览器不会沿用改动前缓存的文件
export const assetUrl = (path: string) => (path.startsWith("/") ? path : staticFile(path));
