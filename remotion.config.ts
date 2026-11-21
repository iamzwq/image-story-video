/**
 * 渲染配置，所有选项见 https://remotion.dev/docs/config
 */
import { Config } from "@remotion/cli/config";

Config.setRspack(true);
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(90);
Config.setOverwriteOutput(true);
Config.setDefaultPremountInSeconds(2);
// Remotion 默认会把 .env 里的所有变量写进预览页面，而 .env 存放的是 API Key，
// 所以改为读取一个不放密钥的 remotion.env
Config.setDotEnvLocation("remotion.env");
