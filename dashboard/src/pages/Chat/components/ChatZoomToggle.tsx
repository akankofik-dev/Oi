import { useCallback, useEffect, useState } from "react";
import { Minus, Plus } from "lucide-react";
import styles from "../index.module.less";

const MIN_ZOOM = 0.8;
const MAX_ZOOM = 1.3;
const STEP = 0.1;
const STORAGE_KEY = "oi-chat-zoom";
const DEFAULT_ZOOM = 1.0;

function loadZoom(): number {
  try {
    const v = parseFloat(localStorage.getItem(STORAGE_KEY) || "");
    if (!isNaN(v) && v >= MIN_ZOOM && v <= MAX_ZOOM) return v;
  } catch {}
  return DEFAULT_ZOOM;
}

function applyZoomToLists(zoom: number) {
  document.querySelectorAll('[class*="messageList"]').forEach((el) => {
    (el as HTMLElement).style.zoom = String(zoom);
  });
}

export default function ChatZoomToggle() {
  const [zoom, setZoom] = useState<number>(loadZoom);

  useEffect(() => {
    applyZoomToLists(zoom);
    try { localStorage.setItem(STORAGE_KEY, String(zoom)); } catch {}
    const timer = setInterval(() => applyZoomToLists(zoom), 2000);
    return () => clearInterval(timer);
  }, [zoom]);

  const zoomOut = useCallback(() => {
    setZoom((z) => Math.max(MIN_ZOOM, Math.round((z - STEP) * 10) / 10));
  }, []);

  const zoomIn = useCallback(() => {
    setZoom((z) => Math.min(MAX_ZOOM, Math.round((z + STEP) * 10) / 10));
  }, []);

  return (
    <div className={styles.chatZoomToggle} role="group" aria-label="Ukuran tampilan chat">
      <button type="button" className={styles.chatZoomBtn} onClick={zoomOut} disabled={zoom <= MIN_ZOOM} title="Kecilkan tampilan" aria-label="Kecilkan tampilan chat">
        <Minus size={13} strokeWidth={2.5} aria-hidden />
      </button>
      <span className={styles.chatZoomLabel} aria-live="polite">{Math.round(zoom * 100)}%</span>
      <button type="button" className={styles.chatZoomBtn} onClick={zoomIn} disabled={zoom >= MAX_ZOOM} title="Besarkan tampilan" aria-label="Besarkan tampilan chat">
        <Plus size={13} strokeWidth={2.5} aria-hidden />
      </button>
    </div>
  );
}
