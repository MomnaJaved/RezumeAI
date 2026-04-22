/**
 * Light preprocessing before OCR (CamScanner-style *lite*, no heavy CV WASM):
 * - Browser-corrects JPEG orientation when supported (`createImageBitmap` + `from-image`)
 * - Caps max dimension, grayscale + 1–99% contrast stretch + mild sharpen for Tesseract
 */
function clampByte(n: number): number {
  return Math.max(0, Math.min(255, Math.round(n)));
}

function contrastStretchGray(data: Uint8ClampedArray, w: number, h: number): void {
  const hist = new Uint32Array(256);
  for (let i = 0; i < data.length; i += 4) {
    hist[data[i]!] += 1;
  }
  const total = w * h;
  let lo = 0;
  let acc = 0;
  const lowCut = Math.max(1, Math.floor(total * 0.01));
  while (lo < 255 && (acc += hist[lo]!) < lowCut) lo++;
  let hi = 255;
  acc = 0;
  const highCut = Math.max(1, Math.floor(total * 0.01));
  while (hi > 0 && (acc += hist[hi]!) < highCut) hi--;
  if (hi <= lo + 8) return;
  const scale = 255 / (hi - lo);
  for (let i = 0; i < data.length; i += 4) {
    const v = clampByte((data[i]! - lo) * scale);
    data[i] = data[i + 1] = data[i + 2] = v;
    data[i + 3] = 255;
  }
}

function mildSharpen(data: Uint8ClampedArray, w: number, h: number): void {
  const copy = new Uint8ClampedArray(data);
  const k = [0, -0.25, 0, -0.25, 2, -0.25, 0, -0.25, 0];
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      let s = 0;
      let ki = 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++, ki++) {
          const j = ((y + dy) * w + (x + dx)) * 4;
          s += copy[j]! * k[ki]!;
        }
      }
      const i = (y * w + x) * 4;
      const v = clampByte(s);
      data[i] = data[i + 1] = data[i + 2] = v;
    }
  }
}

async function decodeToDrawable(file: File): Promise<{ el: CanvasImageSource; w: number; h: number; close?: () => void }> {
  if (typeof createImageBitmap === "function") {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
      return {
        el: bmp,
        w: bmp.width,
        h: bmp.height,
        close: () => {
          try {
            bmp.close();
          } catch {
            /* ignore */
          }
        },
      };
    } catch {
      /* fall through */
    }
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("decode"));
    img.src = url;
  });
  return {
    el: img,
    w: img.naturalWidth || img.width,
    h: img.naturalHeight || img.height,
    close: () => URL.revokeObjectURL(url),
  };
}

export async function enhanceCaptureForOcr(
  file: File,
  opts?: { maxDimension?: number; jpegQuality?: number },
): Promise<File> {
  const maxDim = opts?.maxDimension ?? 2000;
  const jpegQuality = opts?.jpegQuality ?? 0.9;

  let drawable: { el: CanvasImageSource; w: number; h: number; close?: () => void };
  try {
    drawable = await decodeToDrawable(file);
  } catch {
    return file;
  }

  try {
    const { el, w: nw, h: nh } = drawable;
    if (!nw || !nh) return file;

    let scale = 1;
    if (Math.max(nw, nh) > maxDim) {
      scale = maxDim / Math.max(nw, nh);
    }
    const tw = Math.max(1, Math.round(nw * scale));
    const th = Math.max(1, Math.round(nh * scale));

    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return file;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, tw, th);
    ctx.drawImage(el, 0, 0, tw, th);

    const id = ctx.getImageData(0, 0, tw, th);
    contrastStretchGray(id.data, tw, th);
    mildSharpen(id.data, tw, th);
    ctx.putImageData(id, 0, 0);

    const blob: Blob | null = await new Promise((res) =>
      canvas.toBlob((b) => res(b), "image/jpeg", jpegQuality),
    );
    if (!blob || blob.size === 0) return file;

    const base = file.name.replace(/\.[^.]+$/, "") || "scan";
    return new File([blob], `${base}-enhanced.jpg`, { type: "image/jpeg" });
  } catch {
    return file;
  } finally {
    drawable.close?.();
  }
}
