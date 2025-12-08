class VideoParser {
    constructor(onNaluCallback, debug = false) {
        this.debug = debug
        this.buffer = new Uint8Array(0);
        this.name = null;
        this.width = null;
        this.height = null;
        this.hasKeyFrame = null;
        this.sps = null;
        this.pps = null;
        this.mimeCodec = null;
        this.onNaluCallback = onNaluCallback;
        this.hasSentSpsPps = false;
    }

    appendData(data) {
        // Guard against empty or null payloads to avoid slice/read errors.
        if (!data || data.length === 0) {
            return;
        }
        const newBuffer = new Uint8Array(this.buffer.length + data.length);
        newBuffer.set(this.buffer, 0);
        newBuffer.set(data, this.buffer.length);
        this.buffer = newBuffer;
        this.scrcpyProcessBuffer();
    }

    scrcpyProcessBuffer() {
        let startIndex = 0;
        if (this.name == null) {
            if (this.buffer.length >= 64) {
                const name = this.buffer.slice(0, 64);
                this.name = new TextDecoder().decode(name);
                console.log("Device name:" + this.name);
                if (this.onNaluCallback) {
                    this.onNaluCallback({
                        type: 'name',
                        data: { "name": this.name }
                    });
                }
                startIndex = 64;
            }
        } else if (this.width == null) {
            if (this.buffer.length >= 12) {
                const id = new DataView(this.buffer.buffer).getInt32(0, false);
                this.width = new DataView(this.buffer.buffer).getInt32(4, false);
                this.height = new DataView(this.buffer.buffer).getInt32(8, false);
                console.log("width:" + this.width + " height:" + this.height);
                if (this.onNaluCallback) {
                    this.onNaluCallback({
                        type: 'screen_size',
                        data: { "width": this.width, "height": this.height }
                    });
                }
                startIndex += 12;
            }
        } else while (this.buffer.length - startIndex > 12) {
            // const flag = new DataView(this.buffer.buffer).getInt64(0, false);
            const size = new DataView(this.buffer.buffer).getInt32(startIndex + 8, false);
            if (this.buffer.length - startIndex >= 12 + size) {
                const nalu = this.buffer.slice(startIndex + 12, startIndex + 12 + size);
                this.processBuffer(nalu)
                startIndex = startIndex + 12 + size;
            } else {
                break;
            }
        }
        this.buffer = this.buffer.slice(startIndex);
    }

    findSequence(arr, sequence, startIndex = 0) {
        const seqLength = sequence.length;
        for (let i = startIndex; i <= arr.length - seqLength; i++) {
            let match = true;
            for (let j = 0; j < seqLength; j++) {
                if (arr[i + j] !== sequence[j]) {
                    match = false;
                    break;
                }
            }
            if (match) {
                return i;
            }
        }
        return -1;
    }

    processBuffer(nalu) {
        // Need at least NALU header (0 0 0 1 XX)
        if (!nalu || nalu.length < 5) {
            if (this.debug) console.warn('skip short nalu', nalu && nalu.length);
            return;
        }
        const nalu_type = nalu[4] & 0x1f;
        if (nalu_type === 1) {
            if (this.debug)
                console.log("P frame", nalu.length)
        } else if (nalu_type === 5) {
            if (this.debug)
                console.log("I frame", nalu.length)
        } else if (nalu_type === 7) {
            const next_pos = this.findSequence(nalu, [0, 0, 0, 1], 5)
            if (next_pos > 0) {
                this.sps = nalu.slice(0, next_pos)
                if (this.debug)
                    console.log("sps", next_pos)
                this.processBuffer(nalu.slice(next_pos))
            } else {
                this.sps = nalu
                if (this.debug)
                    console.log("sps", nalu.length)
            }
            // Guard against malformed SPS
            if (!this.sps || this.sps.length < 5) {
                if (this.debug) console.warn('skip malformed sps', this.sps && this.sps.length);
                return;
            }
            let ret = SPSParser.parseSPS(this.sps.slice(4));
            if (this.onNaluCallback) {
                this.onNaluCallback({
                    type: 'size_change',
                    data: {"width" : ret.present_size.width, "height" : ret.present_size.height}
                });
            }
            return;
        } else if (nalu_type === 8) {
            const next_pos = this.findSequence(nalu, [0, 0, 0, 1], 5)
            if (next_pos > 0) {
                this.pps = nalu.slice(0, next_pos)
                if (this.debug)
                    console.log("pps", next_pos)
                this.processBuffer(nalu.slice(next_pos))
            } else {
                this.pps = nalu
                if (this.debug)
                    console.log("pps", nalu.length)
            }
            if (!this.pps || this.pps.length === 0) {
                if (this.debug) console.warn('skip malformed pps');
                return;
            }
            return;
        } else {
            console.log("unknow frame type", nalu[0], nalu[1], nalu[2], nalu[3], nalu_type)
        }

        if (this.pps != null && this.sps != null) {
            if (this.onNaluCallback) {
                this.onNaluCallback({
                    type: 'init',
                    data: { "width": this.width, "height": this.height, "pps": this.pps, "sps": this.sps }
                });
            }
            this.pps = null;
            this.sps = null;
        }
        if (this.onNaluCallback) {
            this.onNaluCallback({
                type: 'nalu',
                data: nalu
            });
        }
    }
}
