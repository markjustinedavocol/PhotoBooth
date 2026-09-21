/* Shared camera + shooting helpers for the booth pages (booth.js, solo.js). */
window.Shoot = (() => {
  "use strict";

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let audioCtx = null;

  function audio() {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
  }

  function beep(freq = 660, duration = 0.08) {
    try {
      const ctx = audio();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch {}
  }

  function shutterSound() {
    try {
      const ctx = audio();
      const len = ctx.sampleRate * 0.12;
      const buffer = ctx.createBuffer(1, len, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
      const src = ctx.createBufferSource();
      const gain = ctx.createGain();
      gain.gain.value = 0.35;
      src.buffer = buffer;
      src.connect(gain).connect(ctx.destination);
      src.start();
    } catch {}
  }

  function flash(el) {
    el.classList.remove("is-flashing");
    void el.offsetWidth; // restart the animation
    el.classList.add("is-flashing");
  }

  /** Big 3-2-1 over the stage, one beep per second. */
  async function countdown(el, seconds) {
    el.hidden = false;
    for (let s = seconds; s > 0; s--) {
      el.textContent = s;
      el.classList.remove("pop");
      void el.offsetWidth;
      el.classList.add("pop");
      beep(s === 1 ? 880 : 660);
      await sleep(1000);
    }
    el.hidden = true;
  }

  /** Resolves to a MediaStream, or rejects with an Error whose message is shown to the user. */
  async function openCamera({ audio: withAudio = false } = {}) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("This browser can't reach your camera here. Open the site over HTTPS (or on localhost) in a recent browser.");
    }
    const video = { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } };
    try {
      return await navigator.mediaDevices.getUserMedia({ video, audio: withAudio });
    } catch (err) {
      if (err && err.name === "NotAllowedError") {
        throw new Error("Camera access was blocked. Allow the camera for this site in your browser's address bar, then reload.");
      }
      if (withAudio) {
        // No microphone (or it's busy)? Video alone is enough.
        try {
          return await navigator.mediaDevices.getUserMedia({ video, audio: false });
        } catch (err2) {
          err = err2;
        }
      }
      throw new Error(
        err && err.name === "NotFoundError"
          ? "We couldn't find a camera on this device."
          : "Your camera couldn't start. Is another app using it?"
      );
    }
  }

  function captureFrame(video) {
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 960;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    // Mirror, so the photo matches the selfie preview you were posing in.
    ctx.translate(w, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, w, h);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  }

  async function post(url, csrfToken, body) {
    const res = await fetch(url, {
      method: "POST",
      body,
      headers: { "X-CSRFToken": csrfToken },
      credentials: "same-origin",
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || `Request failed (${res.status})`);
    return json;
  }

  /** Upload one frame, retrying twice. Resolves to the server's JSON. */
  async function uploadFrame(cfg, blob, index, attempt = 1) {
    const body = new FormData();
    body.append("index", String(index));
    body.append("image", blob, `frame-${index}.jpg`);
    try {
      return await post(cfg.uploadUrl, cfg.csrfToken, body);
    } catch (err) {
      if (attempt >= 3) throw err;
      await sleep(800 * attempt);
      return uploadFrame(cfg, blob, index, attempt + 1);
    }
  }

  async function fetchStatus(cfg) {
    const res = await fetch(cfg.statusUrl, { credentials: "same-origin" });
    if (!res.ok) throw new Error("status");
    return res.json();
  }

  /** Row of little previews under the stage, dimmed until each upload lands. */
  function thumbs(container, filterCss) {
    return {
      add(blob, index) {
        const img = document.createElement("img");
        img.src = URL.createObjectURL(blob);
        img.alt = `Shot ${index + 1}`;
        img.style.filter = filterCss;
        img.dataset.index = index;
        img.className = "thumb is-uploading";
        container.appendChild(img);
      },
      mark(index, state) {
        const img = container.querySelector(`[data-index="${index}"]`);
        if (img) img.className = `thumb is-${state}`;
      },
    };
  }

  return { sleep, beep, shutterSound, flash, countdown, openCamera, captureFrame, post, uploadFrame, fetchStatus, thumbs };
})();
