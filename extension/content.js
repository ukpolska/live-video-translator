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

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "caption" || message.type === "notice") {
      const el = ensureOverlay();
      el.textContent = message.text;
      // "unclear", "inaudible", "music" and "notice" texts are drawn differently (see overlay.css).
      el.dataset.kind = message.type === "notice" ? "notice" : message.kind || "";
      el.classList.add("visible");
      clearTimeout(el._hideTimer);
      // Long sentences stay up longer (about 55 ms per character, between 3.5 and 9 seconds).
      let showFor = Math.min(9000, Math.max(3500, 1500 + message.text.length * 55));
      // A "starting" notice stays until the translator is ready (it is replaced by the next text).
      if (message.type === "notice" && message.text.startsWith("Starting")) showFor = 60000;
      el._hideTimer = setTimeout(() => {
        el.classList.remove("visible");
        el.textContent = "";
      }, showFor);
    } else if (message.type === "clear" && overlay) {
      clearTimeout(overlay._hideTimer);
      overlay.classList.remove("visible");
      overlay.textContent = "";
    }
  });
})();
