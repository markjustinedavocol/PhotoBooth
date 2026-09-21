/* Miles Apart booth room.
 *
 * Talks to booth.consumers.BoothConsumer over a WebSocket:
 *   hello/ready  – presence + ready state, relayed to the partner
 *   signal       – WebRTC offer/answer/ICE, relayed to the partner
 *   start        – asks the server to begin; the server broadcasts "countdown"
 * and receives "countdown", "strip_ready", "cancelled", "presence", "error".
 */
(() => {
  "use strict";

  const cfg = JSON.parse(document.getElementById("booth-config").textContent);
  const $ = (id) => document.getElementById(id);
  const el = {
    localVideo: $("local-video"),
    remoteVideo: $("remote-video"),
    localPlaceholder: $("local-placeholder"),
    localPlaceholderText: $("local-placeholder-text"),
    remotePlaceholder: $("remote-placeholder"),
    remotePlaceholderText: $("remote-placeholder-text"),
    presence: $("presence"),
    presenceText: $("presence-text"),
    readyBtn: $("ready-btn"),
    startBtn: $("start-btn"),
    muteBtn: $("mute-btn"),
    message: $("booth-message"),
    countdown: $("countdown"),
    flash: $("flash"),
    shotCounter: $("shot-counter"),
    thumbs: $("thumbs"),
    finishPanel: $("finish-panel"),
    finishText: $("finish-text"),
    finishBtn: $("finish-btn"),
  };

  const RTC_CONFIG = { iceServers: [{ urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"] }] };
  const iAmCaller = cfg.userId < cfg.partnerId; // exactly one side makes offers: no glare

  const state = {
    stream: null,
    ws: null,
    pc: null,
    pendingCandidates: [],
    signalChain: Promise.resolve(),
    ready: false,
    partnerOnline: false,
    partnerReady: false,
    status: cfg.status,
    capturing: false,
    finished: false,
    uploads: [],
  };

  // ------------------------------------------------------------------ UI

  function say(text) {
    el.message.textContent = text;
  }

  function render() {
    const waiting = state.status === "waiting";
    el.presence.dataset.state = state.partnerOnline ? (state.partnerReady ? "ready" : "online") : "offline";
    el.presenceText.textContent = state.partnerOnline
      ? `${cfg.partnerName} is here${state.partnerReady ? " and ready ♥" : ""}`
      : `Waiting for ${cfg.partnerName}…`;

    el.readyBtn.disabled = !waiting || !state.stream || !state.ws || state.ws.readyState !== WebSocket.OPEN;
    el.readyBtn.textContent = state.ready ? "✓ Ready" : "I'm ready";
    el.readyBtn.classList.toggle("is-on", state.ready);
    el.startBtn.disabled = !(waiting && state.ready && state.partnerOnline && state.partnerReady);

    if (!state.partnerOnline) {
      el.remotePlaceholder.hidden = false;
      el.remotePlaceholderText.textContent = `Waiting for ${cfg.partnerName} to step in…`;
    }

    if (waiting && !state.capturing) {
      if (!state.stream) return;
      if (!state.partnerOnline) say(`Send ${cfg.partnerName} the link to this page, or tell them to open their home page.`);
      else if (!state.ready) say("Tap “I'm ready” when you're set.");
      else if (!state.partnerReady) say(`Waiting for ${cfg.partnerName} to get ready…`);
      else say("You're both ready. Start the countdown!");
    }
  }

  // ------------------------------------------------------------------ camera

  async function startCamera() {
    try {
      state.stream = await Shoot.openCamera({ audio: true });
    } catch (err) {
      cameraError(err.message);
      return false;
    }
    el.localVideo.srcObject = state.stream;
    el.localPlaceholder.hidden = true;
    if (state.stream.getAudioTracks().length) el.muteBtn.hidden = false;
    return true;
  }

  function cameraError(text) {
    el.localPlaceholder.hidden = false;
    el.localPlaceholder.classList.add("is-error");
    el.localPlaceholderText.textContent = text;
    say(text);
  }

  el.muteBtn.addEventListener("click", () => {
    const tracks = state.stream ? state.stream.getAudioTracks() : [];
    const enabled = !(tracks[0] && tracks[0].enabled);
    tracks.forEach((t) => (t.enabled = enabled));
    el.muteBtn.textContent = enabled ? "🎙️ Mic on" : "🔇 Muted";
  });

  // ------------------------------------------------------------------ websocket

  function send(msg) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(msg));
  }

  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}${cfg.wsPath}`);
    state.ws = ws;
    ws.addEventListener("open", () => {
      send({ type: "hello", ready: state.ready, reply: false });
      render();
    });
    ws.addEventListener("message", (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      handle(msg);
    });
    ws.addEventListener("close", (event) => {
      state.partnerOnline = false;
      state.partnerReady = false;
      render();
      if (event.code === 4403) {
        say("You don't have access to this booth.");
        return;
      }
      if (!state.finished) {
        say("Connection lost, reconnecting…");
        setTimeout(connect, 2000);
      }
    });
  }

  function handle(msg) {
    switch (msg.type) {
      case "hello":
        state.partnerOnline = true;
        state.partnerReady = !!msg.ready;
        if (!msg.reply) send({ type: "hello", ready: state.ready, reply: true });
        if (iAmCaller) call();
        break;
      case "ready":
        state.partnerReady = !!msg.ready;
        break;
      case "presence":
        if (!msg.online) {
          state.partnerOnline = false;
          state.partnerReady = false;
          hangUp();
        }
        break;
      case "signal":
        state.signalChain = state.signalChain.then(() => onSignal(msg.data)).catch((e) => console.warn("signal", e));
        break;
      case "countdown":
        runShoot(msg);
        break;
      case "strip_ready":
        goTo(msg.url);
        break;
      case "cancelled":
        state.finished = true;
        say(`${msg.by || "Your partner"} closed this session.`);
        setTimeout(() => goTo(cfg.dashboardUrl), 1800);
        break;
      case "error":
        say(msg.message);
        break;
    }
    render();
  }

  // ------------------------------------------------------------------ WebRTC

  function newPeer() {
    hangUp();
    const pc = new RTCPeerConnection(RTC_CONFIG);
    state.pc = pc;
    state.pendingCandidates = [];
    if (state.stream) state.stream.getTracks().forEach((t) => pc.addTrack(t, state.stream));
    pc.addEventListener("icecandidate", (e) => {
      if (e.candidate) send({ type: "signal", data: { candidate: e.candidate.toJSON() } });
    });
    pc.addEventListener("track", (e) => {
      if (el.remoteVideo.srcObject !== e.streams[0]) {
        el.remoteVideo.srcObject = e.streams[0];
        el.remoteVideo.play().catch(() => {});
      }
      el.remotePlaceholder.hidden = true;
    });
    pc.addEventListener("connectionstatechange", () => {
      if (pc !== state.pc) return;
      if (pc.connectionState === "failed") {
        el.remotePlaceholder.hidden = false;
        el.remotePlaceholderText.textContent =
          "Live video couldn't connect on this network, but the synced booth still works.";
      }
    });
    return pc;
  }

  function hangUp() {
    if (state.pc) {
      state.pc.close();
      state.pc = null;
    }
    el.remoteVideo.srcObject = null;
  }

  async function call() {
    if (!state.stream) return;
    const pc = newPeer();
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    send({ type: "signal", data: { description: pc.localDescription.toJSON() } });
  }

  async function onSignal(data) {
    if (!data) return;
    if (data.description) {
      const desc = data.description;
      if (desc.type === "offer") {
        const pc = newPeer();
        await pc.setRemoteDescription(desc);
        await pc.setLocalDescription(await pc.createAnswer());
        send({ type: "signal", data: { description: pc.localDescription.toJSON() } });
      } else if (desc.type === "answer" && state.pc && state.pc.signalingState === "have-local-offer") {
        await state.pc.setRemoteDescription(desc);
      }
      await flushCandidates();
    } else if (data.candidate) {
      if (state.pc && state.pc.remoteDescription) {
        await state.pc.addIceCandidate(data.candidate).catch(() => {});
      } else {
        state.pendingCandidates.push(data.candidate);
      }
    }
  }

  async function flushCandidates() {
    const pending = state.pendingCandidates.splice(0);
    for (const c of pending) await state.pc.addIceCandidate(c).catch(() => {});
  }

  // ------------------------------------------------------------------ shooting

  const { sleep, beep } = Shoot;
  const thumbs = Shoot.thumbs(el.thumbs, el.localVideo.style.filter);

  async function upload(blob, index) {
    try {
      const json = await Shoot.uploadFrame(cfg, blob, index);
      thumbs.mark(index, "done");
      if (json.strip_url) goTo(json.strip_url);
      return true;
    } catch (err) {
      thumbs.mark(index, "failed");
      console.warn(err);
      return false;
    }
  }

  async function runShoot({ shots, seconds, pause }) {
    if (state.capturing) return;
    state.capturing = true;
    state.status = "capturing";
    document.body.classList.add("is-shooting");
    render();
    if (!state.stream) {
      say("Your camera isn't on, so only your partner's photos will be taken.");
      document.body.classList.remove("is-shooting");
      waitForStrip();
      return;
    }

    for (let i = 0; i < shots; i++) {
      el.shotCounter.hidden = false;
      el.shotCounter.textContent = `${i + 1} / ${shots}`;
      say(i === 0 ? "Get close… 💞" : ["Now a silly one!", "Show some love ♥", "Last one, make it count!"][Math.min(i - 1, 2)]);
      await Shoot.countdown(el.countdown, seconds);
      Shoot.flash(el.flash);
      Shoot.shutterSound();
      const blob = await Shoot.captureFrame(el.localVideo);
      thumbs.add(blob, i);
      state.uploads.push(upload(blob, i));
      if (i < shots - 1) await sleep(pause);
    }

    el.shotCounter.hidden = true;
    document.body.classList.remove("is-shooting");
    say("Developing your strip… ✨");
    await Promise.all(state.uploads);
    waitForStrip();
  }

  // ------------------------------------------------------------------ after the shoot

  async function waitForStrip() {
    const startedAt = Date.now();
    while (!state.finished) {
      try {
        const s = await Shoot.fetchStatus(cfg);
        if (s.strip_url) return goTo(s.strip_url);
        if (s.status === "cancelled") return goTo(cfg.dashboardUrl);
        if (Date.now() - startedAt > 20000) {
          el.finishPanel.hidden = false;
          el.finishText.textContent =
            s.my_frames < s.shots
              ? "Some of your photos didn't upload."
              : `${cfg.partnerName}'s photos haven't all arrived (${s.partner_frames}/${s.shots}).`;
        }
      } catch {}
      await sleep(2000);
    }
  }

  el.finishBtn.addEventListener("click", async () => {
    el.finishBtn.disabled = true;
    try {
      const json = await Shoot.post(cfg.finishUrl, cfg.csrfToken);
      if (json.strip_url) return goTo(json.strip_url);
    } catch (err) {
      say(err.message || "Couldn't reach the server. Try again.");
    }
    el.finishBtn.disabled = false;
  });

  function goTo(url) {
    state.finished = true;
    window.location.href = url;
  }

  // ------------------------------------------------------------------ controls

  el.readyBtn.addEventListener("click", () => {
    state.ready = !state.ready;
    send({ type: "ready", ready: state.ready });
    beep(state.ready ? 740 : 440, 0.06); // also unlocks audio for the countdown
    render();
  });

  el.startBtn.addEventListener("click", () => {
    el.startBtn.disabled = true;
    send({ type: "start" });
  });

  // ------------------------------------------------------------------ boot

  (async function boot() {
    if (state.status === "capturing" || state.status === "processing") {
      // Page reloaded mid-shoot: offer to finish with what we have.
      say("This shoot already happened. Checking on your strip…");
      el.finishPanel.hidden = false;
      el.localPlaceholder.hidden = true;
      connect();
      waitForStrip();
      return;
    }
    await startCamera();
    connect();
    render();
  })();
})();
