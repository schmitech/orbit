class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.inputSampleRate = 24000; // Default expected input rate
    
    // Buffer settings (in Input Samples)
    // 200ms initial buffer for smoother playback, still low-latency
    this.bufferThresholdMs = 200; 
    this.maxBufferThresholdMs = 600;
    this.targetBufferMs = 350;
    
    this.updateThresholds();
    
    this.frames = [];
    this.sampleOffset = 0.0; // Float index in current frame (0)
    this.started = false;
    this.buffering = true;
    
    this.port.onmessage = (e) => {
        if (e.data.type === 'config') {
            if (e.data.inputSampleRate) {
                this.inputSampleRate = e.data.inputSampleRate;
                this.updateThresholds();
            }
        } else if (e.data.type === 'audio') {
            this.frames.push(e.data.data);
            this.checkBuffer();
        } else if (e.data.type === 'reset') {
            this.frames = [];
            this.sampleOffset = 0.0;
            this.started = false;
            this.buffering = true;
        }
    };
  }
  
  updateThresholds() {
     this.minStartSamples = Math.floor(this.bufferThresholdMs * this.inputSampleRate / 1000);
     this.targetBufferSamples = Math.floor(this.targetBufferMs * this.inputSampleRate / 1000);
     // Drop buffer if it gets too large (> max threshold) to reduce latent backlog
     this.maxBufferSamples = Math.floor(this.maxBufferThresholdMs * this.inputSampleRate / 1000); 
  }
  
  currentInputSamples() {
      let total = 0;
      for (let i = 0; i < this.frames.length; i++) {
          total += this.frames[i].length;
      }
      total -= this.sampleOffset;
      return total;
  }
  
  checkBuffer() {
      // If not started, check if we have enough to start
      if ((!this.started || this.buffering) && this.currentInputSamples() >= this.minStartSamples) {
          this.started = true;
          this.buffering = false;
      }
      
      // Latency check: if we have too much buffer, skip some old frames
      if (this.currentInputSamples() > this.maxBufferSamples) {
          // Drop oldest frames until we are back to a comfortable target
          while (this.currentInputSamples() > this.targetBufferSamples) {
              if (this.frames.length === 0) break;
              const frame = this.frames[0];
              const remainingInFrame = frame.length - this.sampleOffset;
              
              // Just drop the rest of this frame
              this.frames.shift();
              this.sampleOffset = 0;
          }
      }
  }

  process(inputs, outputs) {
    const output = outputs[0];
    const channel = output[0];
    if (!channel) return true;
    
    if (!this.started || this.buffering) {
        // Output silence
        return true; 
    }

    // ratio = input / output
    // If input=24k, output=48k, step = 0.5. We read 0.5 input samples per output sample.
    const step = this.inputSampleRate / sampleRate;

    for (let i = 0; i < channel.length; i++) {
        // Check if we have data
        if (this.frames.length === 0) {
            // Underrun
            this.buffering = true;
            // Fill rest with 0
            for(let j=i; j<channel.length; j++) channel[j] = 0;
            break;
        }

        const frame = this.frames[0];
        
        // Linear Interpolation
        const idx = Math.floor(this.sampleOffset);
        const frac = this.sampleOffset - idx;
        
        const s0 = frame[idx];
        // Look ahead for s1
        let s1 = s0;
        if (idx + 1 < frame.length) {
            s1 = frame[idx + 1];
        } else if (this.frames.length > 1) {
            // Next sample is in next frame
            s1 = this.frames[1][0];
        }
        
        channel[i] = s0 + (s1 - s0) * frac;
        
        // Advance
        this.sampleOffset += step;
        
        if (this.sampleOffset >= frame.length) {
            this.sampleOffset -= frame.length;
            this.frames.shift(); // Remove processed frame
        }
    }
    
    // Copy to other channels
    for (let c = 1; c < output.length; c++) {
        output[c].set(channel);
    }

    return true;
  }
}

registerProcessor("playback-processor", PlaybackProcessor);
