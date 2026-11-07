const OFFSCREEN_URL = "offscreen.html";
const NATIVE_HOST = "com.ukpolska.live_video_translator";

// While the translator program is still loading its models (10-20 seconds), failed connection
// attempts are normal, so "not running" notices are held back until this time.
let holdErrorNoticesUntil = 0;
let lastErrorNoticeAt = 0;

async function hasOffscreenDocument() {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
  });
  return contexts.length > 0;
}

async function ensureOffscreen() {
  if (await hasOffscreenDocument()) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ["USER_MEDIA"],
    justification: "Capture tab audio and stream it to the local translation server.",
  });
}

// The background service worker can be killed by Chrome after ~30s idle and
// loses any plain JS variables when it restarts, so "which tab is active" is
// kept in session storage instead of a top-level `let activeTabId`.
async function getActiveTabId() {
  const { activeTabId } = await chrome.storage.session.get("activeTabId");
  return activeTabId ?? null;
}

// Chrome only adds the caption-display script to a page when the page loads (and only if the
// extension's site access allows it). Add it ourselves so captions work on a tab that was
// already open. Clicking the extension icon gives us temporary access to that tab.
async function ensureContentScript(tabId) {
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
    await chrome.scripting.insertCSS({ target: { tabId }, files: ["overlay.css"] });
    return true;
  } catch (err) {
    console.error("[LiveTranslate] could not add the caption display to tab", tabId, err);
    return false;
  }
}

// Asks the small helper program (registered by setup.bat) to start the translator program on
// this computer if it is not already running.
async function startTranslatorProgram() {
  try {
    return await chrome.runtime.sendNativeMessage(NATIVE_HOST, { command: "start" });
  } catch (err) {
    return { ok: false, error: String((err && err.message) || err) };
  }
}

// Sends a message to the page being captioned; if the page lost the caption display (e.g. it
// reloaded), adds it again and retries once.
async function sendToCaptionedTab(message) {
  const tabId = await getActiveTabId();
  if (tabId == null) return;
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch (err) {
    if (await ensureContentScript(tabId)) {
      await chrome.tabs.sendMessage(tabId, message).catch(() => {});
    }
  }
}

async function stopCapture(tabId) {
  await ensureOffscreen();
  await chrome.runtime.sendMessage({ type: "stop-capture" }).catch(() => {});
  await chrome.storage.session.remove("activeTabId");
  chrome.action.setBadgeText({ text: "", tabId }).catch(() => {});
  // Clear any caption left on screen so a later restart doesn't show stale text.
  chrome.tabs.sendMessage(tabId, { type: "clear" }).catch(() => {});
}

chrome.action.onClicked.addListener(async (tab) => {
  const activeTabId = await getActiveTabId();

  if (activeTabId === tab.id) {
    await stopCapture(tab.id);
    return;
  }

  // Capture was left running on a different tab: stop that one first.
  if (activeTabId !== null) {
    await stopCapture(activeTabId);
  }

  await ensureContentScript(tab.id);
  await chrome.storage.session.set({ activeTabId: tab.id });

  const helper = await startTranslatorProgram();
  if (helper.ok && helper.state === "starting") {
    holdErrorNoticesUntil = Date.now() + 90000;
    chrome.tabs
      .sendMessage(tab.id, { type: "notice", text: "Starting the translator... this takes about 20 seconds." })
      .catch(() => {});
  } else {
    // Already running (or the helper is not installed and the program was started by hand).
    holdErrorNoticesUntil = Date.now() + 4000;
  }

  await ensureOffscreen();
  const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
  chrome.action.setBadgeText({ text: "ON", tabId: tab.id });
  chrome.runtime.sendMessage({ type: "start-capture", streamId, tabId: tab.id });
});

// Messages from the offscreen document (which holds the connection to the translator program).
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "caption") {
    sendToCaptionedTab(message);
  } else if (message.type === "status") {
    if (message.text === "connected") {
      sendToCaptionedTab({ type: "notice", text: "Translator ready." });
    } else if (
      message.text.startsWith("error") &&
      Date.now() > holdErrorNoticesUntil &&
      Date.now() - lastErrorNoticeAt > 30000
    ) {
      lastErrorNoticeAt = Date.now();
      sendToCaptionedTab({
        type: "notice",
        text: "The translator is not running. Run setup.bat again, or open start_server.bat.",
      });
    }
  }
});
