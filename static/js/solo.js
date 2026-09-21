/* Miles Apart solo booth: one camera, a local countdown, four shots. */
(() => {
  "use strict";

  const cfg = JSON.parse(document.getElementById("booth-config").textContent);
  const $ = (id) => document.getElementById(id);
  const el = {
    video: $("local-video"),
    placeholder: $("local-placeholder"),
    placeholderText: $("local-placeholder-text"),
    startBtn: $("start-btn"),
    message: $("booth-message"),
    countdown: $("countdown"),
    flash: $("flash"),
    shotCounter: $("shot-counter"),
    thumbs: $("thumbs"),
    finishPanel: $("finish-panel"),
    finishBtn: $("finish-btn"),
  };
  const { sleep } = Shoot;
  const thumbs = Shoot.thumbs(el.thumbs, el.video.style.filter);
  const PROMPTS = ["Big smile! 😊", "Now a silly one!", "Blow a kiss 💋", "Last one, make it count!"];
  let finished = false;

  const say = (text) => (el.message.textContent = text);

  function goTo(url) {
    finished = true;
    window.location.href = url;
  }

  async function startCamera() {
    try {
      el.video.srcObject = await Shoot.openCamera();
      el.placeholder.hidden = true;
      el.startBtn.disabled = false;
      say("Strike a pose and press start. You'll get a 3-second countdown before each shot.");
    } catch (err) {
      el.placeholder.classList.add("is-error");
      el.placeholderText.textContent = err.message;
      say(err.message);
    }
  }

  async function upload(blob, index) {
    try {
      const json = await Shoot.uploadFrame(cfg, blob, index);
      thumbs.mark(index, "done");
      if (json.strip_url) goTo(json.strip_url);
    } catch (err) {
      thumbs.mark(index, "failed");
      console.warn(err);
    }
  }

  async function waitForStrip() {
    const startedAt = Date.now();
    while (!finished) {
      try {
        const s = await Shoot.fetchStatus(cfg);
        if (s.strip_url) return goTo(s.strip_url);
        if (Date.now() - startedAt > 15000) el.finishPanel.hidden = false;
      } catch {}
      await sleep(2000);
    }
  }

  el.startBtn.addEventListener("click", async () => {
    el.startBtn.disabled = true;
    Shoot.beep(740, 0.06); // unlocks audio for the countdown
    let plan;
    try {
      plan = await Shoot.post(cfg.startUrl, cfg.csrfToken);
    } catch (err) {
      say(err.message);
      return;
    }

    document.body.classList.add("is-shooting");
    const uploads = [];
    for (let i = 0; i < plan.shots; i++) {
      el.shotCounter.hidden = false;
      el.shotCounter.textContent = `${i + 1} / ${plan.shots}`;
      say(PROMPTS[i % PROMPTS.length]);
      await Shoot.countdown(el.countdown, plan.seconds);
      Shoot.flash(el.flash);
      Shoot.shutterSound();
      const blob = await Shoot.captureFrame(el.video);
      thumbs.add(blob, i);
      uploads.push(upload(blob, i));
      if (i < plan.shots - 1) await sleep(plan.pause);
    }
    el.shotCounter.hidden = true;
    document.body.classList.remove("is-shooting");
    say("Developing your strip… ✨");
    await Promise.all(uploads);
    waitForStrip();
  });

  el.finishBtn.addEventListener("click", async () => {
    el.finishBtn.disabled = true;
    try {
      const json = await Shoot.post(cfg.finishUrl, cfg.csrfToken);
      if (json.strip_url) return goTo(json.strip_url);
    } catch (err) {
      say(err.message);
    }
    el.finishBtn.disabled = false;
  });

  if (cfg.status === "waiting") {
    startCamera();
  } else {
    // Reloaded mid-shoot: offer to finish with the photos that made it.
    el.placeholder.hidden = true;
    el.finishPanel.hidden = false;
    say("This shoot already started. Checking on your strip…");
    waitForStrip();
  }
})();
