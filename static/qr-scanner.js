/**
 * Reusable QR scanner — supports Event Pass and future pass types.
 */
function createQrScanner(opts = {}) {
  const video = document.getElementById(opts.videoId || "ep-scanner-video");
  const onScan = opts.onScan || (() => {});
  const cooldownMs = opts.cooldownMs ?? 2000;

  let stream = null;
  let track = null;
  let raf = null;
  let lastScan = "";
  let lastAt = 0;
  let detector = null;

  if ("BarcodeDetector" in window) {
    try {
      detector = new BarcodeDetector({ formats: ["qr_code"] });
    } catch {
      detector = null;
    }
  }

  function extractPassCode(raw) {
    if (!raw) return "";
    try {
      const u = new URL(raw);
      const parts = u.pathname.split("/").filter(Boolean);
      for (const segment of ["pass", "card", "product", "checkin", "qr"]) {
        const idx = parts.indexOf(segment);
        if (idx >= 0 && parts[idx + 1]) return parts[idx + 1].toLowerCase();
      }
    } catch {
      /* plain code */
    }
    return raw.trim().toLowerCase();
  }

  function emitScan(raw) {
    const code = extractPassCode(raw);
    if (!code) return;
    if (code !== lastScan || Date.now() - lastAt > cooldownMs) {
      lastScan = code;
      lastAt = Date.now();
      onScan(code);
    }
  }

  function cameraSupported() {
    return !!(navigator.mediaDevices?.getUserMedia && window.isSecureContext);
  }

  async function start() {
    if (!video) throw new Error("no_video");
    if (!cameraSupported()) throw new Error("insecure_context");

    const attempts = [
      { video: { facingMode: { ideal: "environment" } }, audio: false },
      { video: true, audio: false },
    ];

    let lastError = null;
    for (const constraints of attempts) {
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        break;
      } catch (err) {
        lastError = err;
      }
    }
    if (!stream) throw lastError || new Error("camera_failed");

    video.srcObject = stream;
    await video.play();
    track = stream.getVideoTracks()[0];
    loop();
    return true;
  }

  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    track = null;
    if (video) video.srcObject = null;
  }

  async function toggleFlash() {
    if (!track) return false;
    const caps = track.getCapabilities?.();
    if (!caps?.torch) return false;
    const cur = track.getSettings?.().torch;
    await track.applyConstraints({ advanced: [{ torch: !cur }] });
    return true;
  }

  async function scanFromFile(file) {
    if (!file || !detector) throw new Error("no_detector");
    const bitmap = await createImageBitmap(file);
    const codes = await detector.detect(bitmap);
    bitmap.close?.();
    if (!codes.length) throw new Error("no_code");
    emitScan(codes[0].rawValue || "");
    return true;
  }

  async function loop() {
    if (!detector || !video || video.readyState < 2) {
      raf = requestAnimationFrame(loop);
      return;
    }
    try {
      const codes = await detector.detect(video);
      if (codes.length) emitScan(codes[0].rawValue || "");
    } catch {
      /* ignore frame errors */
    }
    raf = requestAnimationFrame(loop);
  }

  function cameraErrorMessage(err) {
    const name = err?.name || String(err?.message || err);
    if (name === "insecure_context" || !window.isSecureContext) {
      return {
        label: "Camera needs HTTPS",
        msg: "Use localhost, enable HTTPS, or scan from photo / enter code below.",
      };
    }
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      return {
        label: "Permission denied",
        msg: "Allow camera in browser settings, or use manual entry.",
      };
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return {
        label: "No camera found",
        msg: "Use manual entry or upload a photo of the QR code.",
      };
    }
    if (name === "NotReadableError") {
      return {
        label: "Camera in use",
        msg: "Close other apps using the camera, then try again.",
      };
    }
    return {
      label: "Camera unavailable",
      msg: "Use manual entry or upload a photo of the QR code.",
    };
  }

  return {
    start,
    stop,
    toggleFlash,
    scanFromFile,
    extractPassCode,
    cameraSupported,
    cameraErrorMessage,
    hasDetector: () => !!detector,
  };
}

if (typeof window !== "undefined") {
  window.createQrScanner = createQrScanner;
}
