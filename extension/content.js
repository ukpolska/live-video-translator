// Wrapped so the script can safely be added to a tab more than once (Chrome adds it when a
// page loads, and the extension adds it again on click if the page never got it).
(() => {
  if (window.__liveTranslateLoaded) return;
  window.__liveTranslateLoaded = true;

  const POSITION_KEY = "__live_translate_pos__";

  let overlay = null;

  function makeDraggable(el) {
    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;

    el.addEventListener("mousedown", (e) => {
      dragging = true;
      const rect = el.getBoundingClientRect();
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      e.preventDefault();
    });

    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      el.style.left = `${e.clientX - offsetX}px`;
      el.style.top = `${e.clientY - offsetY}px`;
      el.style.transform = "none";
    });

    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      try {
        localStorage.setItem(POSITION_KEY, JSON.stringify({ left: el.style.left, top: el.style.top }));
      } catch (e) {
        // localStorage can be unavailable (e.g. sandboxed iframe) - dragging just won't persist.
      }
    });
  }

  function restorePosition(el) {
    try {
      const saved = JSON.parse(localStorage.getItem(POSITION_KEY));
      if (saved && saved.left && saved.top) {
        el.style.left = saved.left;
        el.style.top = saved.top;
        el.style.transform = "none";
      }
    } catch (e) {
      // ignore malformed/missing saved position
    }
  }

  function ensureOverlay() {
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "__live_translate_overlay__";
      restorePosition(overlay);
      makeDraggable(overlay);
    }
    // When the page is fullscreen (the normal way to actually watch a video),
    // the browser only renders the fullscreened element's subtree - anything
    // appended elsewhere on the page becomes invisible even if it's still
    // updating. Keep the overlay inside whichever element is currently
    // fullscreen so it stays visible.
    const host = document.fullscreenElement || document.documentElement;
    if (overlay.parentElement !== host) {
      host.appendChild(overlay);
    }
    return overlay;
  }

  document.addEventListener("fullscreenchange", ensureOverlay);

  // Tell the extension when the page's video goes fullscreen or leaves it, so it can make the
  // whole Chrome window fullscreen too (Chrome does not do that by itself for a captured tab).
  document.addEventListener("fullscreenchange", () => {
    try {
      chrome.runtime.sendMessage({ type: "page-fullscreen", on: !!document.fullscreenElement }).catch(() => {});
    } catch (e) {
      // The extension was just reloaded: this page needs a refresh.
    }
  });

  // ---- Settings (changed on the extension's Options page; defaults suit most screens) ----
  const DEFAULTS = { widthPercent: 85, fontSize: 26, holdFactor: 1, maxLines: 3 };
  let settings = { ...DEFAULTS };

  function applySettings() {
    if (!overlay) return;
    overlay.style.maxWidth = `${settings.widthPercent}vw`;
    overlay.style.fontSize = `${settings.fontSize}px`;
  }

  try {
    chrome.storage.local.get(DEFAULTS, (saved) => {
      settings = { ...DEFAULTS, ...saved };
      applySettings();
      render();
    });
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local") return;
      for (const key of Object.keys(DEFAULTS)) {
        if (changes[key]) settings[key] = changes[key].newValue;
      }
      applySettings();
      render();
    });
  } catch (e) {
    // Storage can be unavailable (extension just reloaded): the defaults are used.
  }

  // ---- Resize grip: drag the bottom-right corner to make the whole caption box bigger or smaller ----
  // The text size and the width limit are scaled together (like zooming) and the result is saved
  // in the same settings the Options page uses.
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  let grip = null;

  function makeGrip() {
    const el = document.createElement("div");
    el.className = "lt-grip";
    el.title = "Drag to make the captions bigger or smaller";
    el.addEventListener("mousedown", (down) => {
      down.preventDefault();
      down.stopPropagation(); // do not start dragging the whole box
      const rect = overlay.getBoundingClientRect();
      // A box in its default place is centred (it grows both ways); a moved box grows to the right.
      const anchorX = overlay.style.transform === "none" ? rect.left : rect.left + rect.width / 2;
      const span = Math.max(40, rect.right - anchorX);
      const startFont = settings.fontSize;
      const startWidth = settings.widthPercent;
      const onMove = (move) => {
        const scale = clamp((move.clientX - anchorX) / span, 0.3, 4);
        settings.fontSize = Math.round(clamp(startFont * scale, 16, 60));
        settings.widthPercent = Math.round(clamp(startWidth * scale, 40, 98));
        applySettings();
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", onUp, true);
        try {
          chrome.storage.local.set({ fontSize: settings.fontSize, widthPercent: settings.widthPercent });
        } catch (e) {
          // Storage unavailable: the size only lasts until the page is reloaded.
        }
      };
      window.addEventListener("mousemove", onMove, true);
      window.addEventListener("mouseup", onUp, true);
    });
    return el;
  }

  // ---- Captions: a short stack of lines, each kept up long enough to be read ----
  // Each new sentence is added under the previous ones instead of replacing them. A line goes
  // away only after its own reading time (about 70 ms per character, 4 to 12 seconds, scaled by
  // the "how long text stays" setting), and never before the line above it.
  let lines = []; // { text, kind, expires }
  let timer = null;

  function holdFor(text) {
    return Math.min(12000, Math.max(4000, 1500 + text.length * 70)) * settings.holdFactor;
  }

  function render() {
    clearTimeout(timer);
    const now = Date.now();
    lines = lines.filter((line) => line.expires > now).slice(-settings.maxLines);
    if (!lines.length) {
      if (overlay) {
        overlay.classList.remove("visible");
        overlay.replaceChildren();
        // Take the empty box off the page entirely so no ghost shape is left over a video.
        overlay.remove();
      }
      return;
    }
    const el = ensureOverlay();
    applySettings();
    if (!grip) grip = makeGrip();
    el.replaceChildren(
      grip, // first, so the newest caption line is still the :last-child that the styling relies on
      ...lines.map((line) => {
        const row = document.createElement("div");
        row.className = "lt-line";
        row.dataset.kind = line.kind;
        row.textContent = line.text;
        return row;
      })
    );
    el.classList.add("visible");
    const next = Math.min(...lines.map((line) => line.expires));
    timer = setTimeout(render, Math.max(50, next - now));
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "caption" || message.type === "notice") {
      const isNotice = message.type === "notice";
      const now = Date.now();
      if (isNotice) {
        lines = []; // a notice ("Starting...", "Translator ready.") replaces everything
      } else {
        lines = lines.filter((line) => line.kind !== "notice"); // real captions replace notices
      }
      let hold = holdFor(message.text);
      // A "starting" notice stays until the translator is ready (the next caption replaces it).
      if (isNotice && message.text.startsWith("Starting")) hold = 60000;
      const last = lines[lines.length - 1];
      lines.push({
        text: message.text,
        kind: isNotice ? "notice" : message.kind || "",
        expires: Math.max(now + hold, last ? last.expires + 1500 : 0),
      });
      render();
    } else if (message.type === "clear") {
      lines = [];
      render();
    }
  });
})();
