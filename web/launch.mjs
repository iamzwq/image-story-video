// npm run web 的入口：检查 uv 和 FFmpeg（没装的话问要不要帮忙装）→ 构建网页 → 启动后台 web/server.py。
// npm run web -- --port 3200 这样的参数原样交给 server.py。
import { spawn, spawnSync } from "node:child_process";
import { join } from "node:path";
import { createInterface } from "node:readline/promises";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const WINDOWS = process.platform === "win32";

const TOOLS = [
  { key: "uv", name: "uv", use: "后台和各个脚本都靠它运行", checks: ["uv --version"] },
  { key: "ffmpeg", name: "FFmpeg", use: "配音、出图和导出都要用到", checks: ["ffmpeg -version", "ffprobe -version"] },
];

// 能帮忙安装的包管理器，用第一个找得到的
const MANAGERS = {
  win32: [
    {
      name: "winget",
      check: "winget --version",
      uv: "winget install --id astral-sh.uv -e --source winget",
      ffmpeg: "winget install --id Gyan.FFmpeg -e --source winget",
    },
    { name: "Scoop", check: "scoop --version", uv: "scoop install uv", ffmpeg: "scoop install ffmpeg" },
  ],
  darwin: [{ name: "Homebrew", check: "brew --version", uv: "brew install uv", ffmpeg: "brew install ffmpeg" }],
};

const MANUAL = {
  win32: { uv: "winget install astral-sh.uv", ffmpeg: "winget install Gyan.FFmpeg" },
  darwin: { uv: "brew install uv", ffmpeg: "brew install ffmpeg" },
  other: { uv: "curl -LsSf https://astral.sh/uv/install.sh | sh", ffmpeg: "sudo apt install ffmpeg（或者用系统自带的包管理器）" },
};

// 交给终端去找命令，和用户自己在终端里输入时的结果一样（Windows 上的 .cmd 也找得到）
const runs = (command) => spawnSync(command, { shell: true, stdio: "ignore", timeout: 30_000 }).status === 0;

const findMissing = () => TOOLS.filter((tool) => !tool.checks.every(runs));

/** Windows 上刚装的程序，之前打开的终端找不到：从注册表读最新的 PATH 补进当前进程，后台也会继承 */
function refreshPath() {
  if (!WINDOWS) {
    return;
  }
  // 转成 base64 再输出，路径里有中文也不会因为控制台编码乱码
  const script =
    "$p = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User');" +
    "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($p))";
  const result = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], { encoding: "utf8" });
  if (result.status !== 0) {
    return;
  }
  const latest = Buffer.from(result.stdout.trim(), "base64").toString("utf8").split(";");
  const seen = new Set();
  process.env.PATH = [...(process.env.PATH ?? "").split(";"), ...latest]
    .filter((dir) => dir && !seen.has(dir.toLowerCase()) && seen.add(dir.toLowerCase()))
    .join(";");
}

async function confirm(question) {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  rl.on("SIGINT", () => {
    rl.close();
    process.exit(130);
  });
  try {
    return ["", "y", "yes"].includes((await rl.question(question)).trim().toLowerCase());
  } finally {
    rl.close();
  }
}

async function ensureTools() {
  let missing = findMissing();
  if (missing.length && WINDOWS) {
    refreshPath(); // 可能已经装好了，只是这个终端是装之前打开的
    missing = findMissing();
  }
  if (!missing.length) {
    return;
  }

  console.log("没有找到运行需要的工具：");
  for (const tool of missing) {
    console.log(`  - ${tool.name}：${tool.use}`);
  }
  const manager = (MANAGERS[process.platform] ?? []).find((m) => runs(m.check));
  const offer = Boolean(manager && process.stdin.isTTY);
  if (offer) {
    console.log(`\n可以用 ${manager.name} 帮你安装，会运行：`);
    for (const tool of missing) {
      console.log(`  ${manager[tool.key]}`);
    }
    if (await confirm("现在安装吗？[Y/n] ")) {
      for (const tool of missing) {
        console.log(`\n> ${manager[tool.key]}`);
        spawnSync(manager[tool.key], { shell: true, stdio: "inherit" });
      }
      refreshPath();
      missing = findMissing();
      if (!missing.length) {
        console.log("\n装好了，继续启动网页。\n");
        return;
      }
      console.log(`\n${missing.map((tool) => tool.name).join("、")} 还是没有找到，可能没装成功，看看上面的输出。`);
    }
  }

  const manual = MANUAL[process.platform] ?? MANUAL.other;
  console.log(`\n${offer ? "也可以自己安装" : "请先安装"}，装好后重新运行 npm run web（还找不到就重新打开终端）：`);
  for (const tool of missing) {
    console.log(`  ${manual[tool.key]}`);
  }
  if (missing.some((tool) => tool.key === "uv")) {
    console.log("\n没有 uv 没法启动网页。");
    process.exit(1);
  }
  console.log(); // 只缺 FFmpeg 时照样启动，后台会再提醒一次，网页上也会显示
}

async function buildWeb() {
  let vite;
  try {
    vite = await import("vite");
  } catch {
    console.error("没有找到项目依赖，请先在项目文件夹里运行 npm install");
    process.exit(1);
  }
  try {
    await vite.build({ configFile: join(ROOT, "web", "vite.config.mts"), logLevel: "warn" });
  } catch (err) {
    console.error(`网页构建失败：${err?.message ?? err}`);
    process.exit(1);
  }
}

function startServer() {
  const server = spawn("uv", ["run", "web/server.py", ...process.argv.slice(2)], { cwd: ROOT, stdio: "inherit" });
  server.on("error", (err) => {
    console.error(`没能启动后台：${err.message}`);
    process.exit(1);
  });
  server.on("exit", (code) => process.exit(code ?? 1));
  // 按 Ctrl+C 时终端会把信号同时发给后台，这里等它停好正在运行的任务再退出
  process.on("SIGINT", () => {});
  process.on("SIGTERM", () => server.kill("SIGTERM"));
}

await ensureTools();
await buildWeb();
startServer();
