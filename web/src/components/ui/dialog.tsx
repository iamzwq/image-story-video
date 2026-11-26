import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import React from "react";

const backdrop =
  "fixed inset-0 z-50 bg-ink/45 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0";

/** 弹窗：打开时渲染、关闭时由父组件卸载。按 Esc 或点外面关闭 */
export const Dialog: React.FC<{
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  actions: React.ReactNode;
}> = ({ title, onClose, children, actions }) => (
  <BaseDialog.Root
    open
    onOpenChange={(open) => {
      if (!open) {
        onClose();
      }
    }}
  >
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className={backdrop} />
      <BaseDialog.Popup className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-48px)] w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-base border-2 border-ink bg-white shadow-brutal-lg outline-none transition-[scale,opacity] duration-150 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
        <div className="flex items-center gap-3 border-b-2 border-ink bg-main px-5 py-3">
          <BaseDialog.Title className="flex-1 text-lg font-black">{title}</BaseDialog.Title>
          <BaseDialog.Close
            aria-label="关闭"
            className="grid size-7 cursor-pointer place-items-center rounded-[4px] border-2 border-ink bg-white hover:bg-ink hover:text-white"
          >
            <X className="size-4" strokeWidth={2.5} />
          </BaseDialog.Close>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        <div className="flex justify-end gap-2.5 border-t-2 border-ink bg-paper px-5 py-3">{actions}</div>
      </BaseDialog.Popup>
    </BaseDialog.Portal>
  </BaseDialog.Root>
);

/** 看大图：点任意位置或按 Esc 关闭 */
export const Lightbox: React.FC<{ url: string; onClose: () => void }> = ({ url, onClose }) => (
  <BaseDialog.Root
    open
    onOpenChange={(open) => {
      if (!open) {
        onClose();
      }
    }}
  >
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className={`${backdrop} bg-ink/70`} />
      <BaseDialog.Popup
        aria-label="查看大图"
        className="fixed inset-0 z-50 grid cursor-zoom-out place-items-center p-6 outline-none"
        onClick={onClose}
      >
        <img
          src={url}
          alt=""
          className="max-h-[calc(100vh-48px)] max-w-full rounded-base border-2 border-ink bg-white shadow-brutal-lg"
        />
      </BaseDialog.Popup>
    </BaseDialog.Portal>
  </BaseDialog.Root>
);
