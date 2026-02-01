/**
 * AudioWorklet Processor for capturing microphone audio
 *
 * Runs in a separate audio thread for better performance and lower latency
 * than the deprecated ScriptProcessorNode.
 */

class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._bufferSize = 2048;  // Match the chunk size from main.ts
    this._buffer = new Float32Array(this._bufferSize);
    this._bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];

    if (input.length > 0) {
      const inputChannel = input[0];

      // Accumulate samples into buffer
      for (let i = 0; i < inputChannel.length; i++) {
        this._buffer[this._bufferIndex++] = inputChannel[i];

        // When buffer is full, send it to main thread
        if (this._bufferIndex >= this._bufferSize) {
          // Copy buffer and send to main thread
          this.port.postMessage({
            type: 'audio',
            data: this._buffer.slice()
          });
          this._bufferIndex = 0;
        }
      }
    }

    // Return true to keep the processor running
    return true;
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor);
