import { translateError } from "./presentation";


const DEFAULT_API_PORT = "8100";

export function getApiBaseUrl() {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  if (typeof window !== "undefined") {
    if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
      return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_API_PORT}`;
    }
    return window.location.origin;
  }
  return `http://127.0.0.1:${DEFAULT_API_PORT}`;
}

async function parseError(response) {
  try {
    const payload = await response.json();
    return translateError(payload.detail || payload.message || "Request failed");
  } catch {
    return "请求失败，请稍后重试。";
  }
}

export async function api(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export function downloadText(filename, content, type = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadJson(filename, payload) {
  downloadText(filename, JSON.stringify(payload, null, 2), "application/json;charset=utf-8");
}

export async function exportSvgToPng(svgId, filename) {
  const svgNode = document.getElementById(svgId);
  if (!svgNode) {
    throw new Error("图表尚未准备好，暂时无法导出。");
  }
  const serializer = new XMLSerializer();
  const svgString = serializer.serializeToString(svgNode);
  const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const image = new Image();
  image.src = url;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = svgNode.viewBox.baseVal.width || svgNode.clientWidth || 880;
  canvas.height = svgNode.viewBox.baseVal.height || svgNode.clientHeight || 280;
  const context = canvas.getContext("2d");
  context.fillStyle = "#f5f1e8";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0);
  const anchor = document.createElement("a");
  anchor.href = canvas.toDataURL("image/png");
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
