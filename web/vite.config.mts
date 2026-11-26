import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// npm run web 用这个配置把网页构建到 web/dist，再由 web/server.py 提供。
// 改网页代码时：先运行 npm run web（或 uv run web/server.py --no-open），再另开终端运行 npm run web:dev 热更新，接口转发给 3100 端口
const backend = "http://127.0.0.1:3100";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react(), tailwindcss()],
  // public/ 里是各集的图片和配音，由 web/server.py 直接提供，不要复制进构建结果
  publicDir: false,
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 4000 },
  server: {
    proxy: Object.fromEntries(["/api", "/episodes", "/fonts", "/out"].map((path) => [path, backend])),
  },
});
