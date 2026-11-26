import { useEffect, useRef, useState } from "react";

export type Route = { page: "home" } | { page: "settings" } | { page: "new" } | { page: "episode"; id: string };

const parseRoute = (): Route => {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash === "settings") {
    return { page: "settings" };
  }
  if (hash === "new") {
    return { page: "new" };
  }
  const m = /^ep\/([A-Za-z0-9-]+)$/.exec(hash);
  return m ? { page: "episode", id: m[1] } : { page: "home" };
};

// 有未保存的修改时，页面设置一个离开前的确认；返回 false 就留在当前页
let leaveGuard: (() => boolean) | null = null;

export const setLeaveGuard = (guard: (() => boolean) | null) => {
  leaveGuard = guard;
};

export const confirmLeave = () => window.confirm("有未保存的修改，离开这一页会丢掉这些修改。确定离开吗？");

export const useRoute = () => {
  const [route, setRoute] = useState(parseRoute);
  useEffect(() => {
    let current = window.location.href;
    const onChange = () => {
      if (leaveGuard && !leaveGuard()) {
        // 网址已经变了，悄悄改回来（replaceState 不会再触发 hashchange）
        window.history.replaceState(null, "", current);
        return;
      }
      current = window.location.href;
      setRoute(parseRoute());
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
};

/** 有未保存的修改时：在网页内跳转先确认，关闭或刷新页面时浏览器也会提醒 */
export const useLeaveGuard = (dirty: boolean, allowLeave?: () => boolean) => {
  const allow = useRef(allowLeave);
  useEffect(() => {
    allow.current = allowLeave;
  });
  useEffect(() => {
    if (!dirty) {
      return;
    }
    setLeaveGuard(() => Boolean(allow.current?.()) || confirmLeave());
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => {
      setLeaveGuard(null);
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty]);
};

export const navigate = (path: string) => {
  window.location.hash = path;
};

export const useInterval = (callback: () => void, delay: number | null) => {
  const saved = useRef(callback);
  useEffect(() => {
    saved.current = callback;
  });
  useEffect(() => {
    if (delay === null) {
      return;
    }
    const id = window.setInterval(() => saved.current(), delay);
    return () => window.clearInterval(id);
  }, [delay]);
};

// 跳转到另一页之后要显示的提示（例如新建视频后，写分镜没能开始的原因）
let flash: string | null = null;

export const setFlash = (message: string) => {
  flash = message;
};

export const takeFlash = () => {
  const message = flash;
  flash = null;
  return message;
};
