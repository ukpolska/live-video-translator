const SERVER_URL = "ws://localhost:8765";
// Audio is sent in small slices so the server can follow the speech as it happens.
const CHUNK_SECONDS = 0.2;

let audioContext = null;
let sourceNode = null;
let workletNode = null;
let mediaStream = null;
let ws = null;
let pcmBuffer = [];
let bufferedSamples = 0;
let nativeSampleRate = 48000;
let capturing = false; // true while the user wants capture running, so we know whether to reconnect
let reconnectTimer = null;
let session = 0; // changes on every start/stop, so a start that was overtaken can tell and give up

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "start-capture") start(message.streamId);
  if (message.type === "stop-capture") stop();
});

async function start(streamId) {
  // Never run two captures at once: a second audio feed would be added to the same
  // stream, doubling the audio sent to the server.
  stop();
  capturing = true;
  const mySession = session;

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
    video: false,
  });
  if (mySession !== session) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
  mediaStream = stream;

  const context = new AudioContext();
  audioContext = context;
  nativeSampleRate = context.sampleRate;
  await context.audioWorklet.addModule(chrome.runtime.getURL("capture-worklet.js"));
  if (mySession !== session) return; // stopped while the worklet was loading

  sourceNode = context.createMediaStreamSource(stream);

  // tabCapture mutes the tab by default, so route the audio back out to speakers.
  sourceNode.connect(context.destination);

  // A second path takes a copy of the audio for the translator. The worklet makes no sound
  // of its own, so connecting it to the output does not play anything twice.
  workletNode = new AudioWorkletNode(context, "capture-processor", {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    channelCount: 1,
    channelCountMode: "explicit",
    outputChannelCount: [1],
  });
  workletNode.port.onmessage = (event) => {
    pcmBuffer.push(event.data);
    bufferedSamples += event.data.length;
    if (bufferedSamples >= nativeSampleRate * CHUNK_SECONDS) {
      flushChunk();
    }
  };
  sourceNode.connect(workletNode);
  workletNode.connect(context.destination);

  connectSocket();
}

function connectSocket() {
  const socket = new WebSocket(SERVER_URL);
  ws = socket;

  socket.onopen = () => {
    // The server resamples, so it needs to know the rate the browser is sending at.
    socket.send(JSON.stringify({ type: "hello", sampleRate: nativeSampleRate }));
    notifyStatus("connected");
  };

  socket.onclose = () => {
    notifyStatus("disconnected");
    // The server connection can drop for reasons unrelated to the user (e.g. a
    // slow transcription on an older CPU). Reconnect automatically as long as
    // capture is still meant to be running, so the user doesn't have to notice
    // and manually restart it mid-film.
    if (capturing && ws === socket && !reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (capturing) connectSocket();
      }, 2000);
    }
  };

  socket.onerror = () => notifyStatus("error: is the server running on localhost:8765?");

  socket.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    if (data.text) {
      chrome.runtime.sendMessage({ type: "caption", text: data.text, kind: data.kind || "" });
    }
  };
}

function notifyStatus(text) {
  chrome.runtime.sendMessage({ type: "status", text });
}

function flushChunk() {
  const chunks = pcmBuffer;
  pcmBuffer = [];
  bufferedSamples = 0;

  const merged = new Float32Array(chunks.reduce((sum, c) => sum + c.length, 0));
  let offset = 0;
  for (const c of chunks) {
    merged.set(c, offset);
    offset += c.length;
  }

  // Slices that arrive while the server is (re)connecting are dropped.
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(merged.buffer);
  }
}

function stop() {
  session += 1;
  capturing = false;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (workletNode) {
    workletNode.port.onmessage = null;
    workletNode.disconnect();
  }
  if (sourceNode) sourceNode.disconnect();
  if (audioContext) audioContext.close().catch(() => {});
  // Stopping the tracks is essential: closing the AudioContext alone leaves
  // the underlying tabCapture stream "active" from Chrome's point of view,
  // and the tab refuses to be captured again until the tracks are stopped.
  if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
  if (ws) {
    // Detach first: the old socket's close event must not trigger a reconnect.
    ws.onclose = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.close();
  }
  ws = null;
  audioContext = null;
  sourceNode = null;
  workletNode = null;
  mediaStream = null;
  pcmBuffer = [];
  bufferedSamples = 0;
}
