// Runs on Chrome's audio thread. Collects the tab's audio (already mixed down to mono by the
// AudioWorkletNode settings in offscreen.js) and hands it over in blocks of 2048 samples.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(2048);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    let offset = 0;
    while (offset < channel.length) {
      const count = Math.min(channel.length - offset, this.block.length - this.filled);
      this.block.set(channel.subarray(offset, offset + count), this.filled);
      this.filled += count;
      offset += count;
      if (this.filled === this.block.length) {
        // Transfer the memory instead of copying it, then start a fresh block.
        this.port.postMessage(this.block, [this.block.buffer]);
        this.block = new Float32Array(2048);
        this.filled = 0;
      }
    }
    return true; // keep running
  }
}

registerProcessor("capture-processor", CaptureProcessor);
