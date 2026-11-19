(function (global) {
    'use strict';
    const TTS_TIMEOUT_MS = 65000;
    const fishDefaults = Object.freeze({ speed: 1, volume: 0, temperature: 0.72, top_p: 0.75,
        latency: 'normal', chunk_length: 220, min_chunk_length: 40,
        repetition_penalty: 1.18, condition_on_previous_chunks: true });
    const channels = new Map();
    function number(value, fallback, min, max) {
        const n = parseFloat(value);
        return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : fallback;
    }
    function normalizeFish(cfg = {}) {
        const chunk = Math.round(number(cfg.chunk_length, 220, 100, 300));
        return {
            speed: +number(cfg.speed, 1, 0.5, 2).toFixed(2),
            volume: +number(cfg.volume, 0, -20, 20).toFixed(1),
            temperature: +number(cfg.temperature, 0.72, 0, 1).toFixed(2),
            top_p: +number(cfg.top_p, 0.75, 0, 1).toFixed(2),
            latency: ['low', 'normal', 'balanced'].includes(cfg.latency) ? cfg.latency : 'normal',
            chunk_length: chunk,
            min_chunk_length: Math.min(chunk, Math.round(number(cfg.min_chunk_length, 40, 0, 100))),
            repetition_penalty: +number(cfg.repetition_penalty, 1.18, 1, 2).toFixed(2),
            condition_on_previous_chunks: ![false, 0, 'false', '0'].includes(cfg.condition_on_previous_chunks)
        };
    }
    function buildPayload(text, cfg = {}, settings = {}, emotion = '') {
        const voice = cfg.voice || 'fish:';
        const body = { text, voice, emotion };
        if (voice.startsWith('edge:')) {
            Object.assign(body, { rate: cfg.rate || '-8%', pitch: cfg.pitch || '-4Hz', volume: cfg.volume || '+0%', emotion: '' });
        } else {
            Object.assign(body, normalizeFish(cfg), { tts_model: cfg.tts_model || settings.fish_tts_model || 's2.1-pro' });
        }
        return body;
    }
    async function checkedResponse(response) {
        if (response.ok) return response;
        let message = '服务请求失败，请稍后重试。';
        try { const data = await response.json(); if (data.error) message = data.error; } catch (_) {}
        const error = new Error(message);
        error.status = response.status;
        throw error;
    }
    async function requestJson(url, options = {}, timeoutMs = 10000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const response = await checkedResponse(await fetch(url, { ...options, signal: controller.signal }));
            return await response.json();
        } catch (error) {
            if (controller.signal.aborted) throw new Error('连接等待超时，请检查服务后重试。');
            throw error;
        } finally { clearTimeout(timer); }
    }
    function cancel(channel) {
        const job = channels.get(channel);
        if (job) job.controller.abort();
    }
    function cancelAll() { for (const channel of channels.keys()) cancel(channel); }
    async function requestAudio(payload, { channel = 'audio', timeoutMs = TTS_TIMEOUT_MS, maxBytes = Infinity } = {}) {
        cancel(channel);
        const job = { controller: new AbortController(), timedOut: false };
        channels.set(channel, job);
        const timer = setTimeout(() => { job.timedOut = true; job.controller.abort(); }, timeoutMs);
        try {
            const response = await checkedResponse(await fetch('/api/tts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload), signal: job.controller.signal
            }));
            if (!(response.headers.get('content-type') || '').startsWith('audio/')) throw new Error('服务没有返回可播放的音频。');
            let blob;
            if (Number.isFinite(maxBytes) && response.body) {
                const reader = response.body.getReader(), parts = [];
                let size = 0;
                try {
                    while (true) {
                        const part = await reader.read();
                        if (part.done) break;
                        size += part.value.byteLength;
                        if (size > maxBytes) {
                            await reader.cancel();
                            throw new Error('音频超过预取容量限制。');
                        }
                        parts.push(part.value);
                    }
                    blob = new Blob(parts, { type: response.headers.get('content-type') });
                } finally { reader.releaseLock(); }
            } else blob = await response.blob();
            if (blob.size > maxBytes) throw new Error('音频超过预取容量限制。');
            if (!blob.size) throw new Error('生成的音频为空，请重试。');
            if (job.controller.signal.aborted) throw new DOMException('已取消语音等待', 'AbortError');
            return blob;
        } catch (error) {
            if (job.timedOut) { const timeout = new Error('语音生成等待超时，请稍后重试。'); timeout.name = 'TimeoutError'; throw timeout; }
            throw error;
        } finally {
            clearTimeout(timer);
            if (channels.get(channel) === job) channels.delete(channel);
        }
    }
    async function requestStream(payload, { channel = 'story', onReady } = {}) {
        if (!global.MediaSource || !MediaSource.isTypeSupported('audio/mpeg') || String(payload.voice || '').startsWith('edge:')) return null;
        cancel(channel);
        const controller = new AbortController();
        const job = { controller };
        channels.set(channel, job);
        const media = new MediaSource();
        const url = URL.createObjectURL(media);
        let reader, disposed = false;
        const timer = setTimeout(() => controller.abort(), TTS_TIMEOUT_MS);
        const dispose = () => {
            if (disposed) return;
            disposed = true; controller.abort(); clearTimeout(timer);
            if (reader) reader.cancel().catch(() => {});
            URL.revokeObjectURL(url);
            if (channels.get(channel) === job) channels.delete(channel);
        };
        const opened = new Promise((resolve, reject) => {
            media.addEventListener('sourceopen', resolve, { once: true });
            controller.signal.addEventListener('abort', () => reject(new DOMException('已取消', 'AbortError')), { once: true });
        });
        opened.catch(() => {});
        const done = (async () => {
            try {
                const response = await checkedResponse(await fetch('/api/tts', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...payload, stream: true }), signal: controller.signal
                }));
                if (!(response.headers.get('content-type') || '').startsWith('audio/') || !response.body) throw new Error('没有可播放的音频流。');
                reader = response.body.getReader();
                await opened;
                const buffer = media.addSourceBuffer('audio/mpeg');
                let first = true;
                while (true) {
                    const part = await reader.read();
                    if (part.done) break;
                    if (!part.value.length) continue;
                    await new Promise((resolve, reject) => {
                        const clean = () => {
                            buffer.removeEventListener('updateend', ok);
                            buffer.removeEventListener('error', fail);
                            controller.signal.removeEventListener('abort', abort);
                        };
                        const ok = () => { clean(); resolve(); };
                        const fail = () => { clean(); reject(new Error('音频解码失败。')); };
                        const abort = () => { clean(); reject(new DOMException('已取消', 'AbortError')); };
                        buffer.addEventListener('updateend', ok, { once: true });
                        buffer.addEventListener('error', fail, { once: true });
                        controller.signal.addEventListener('abort', abort, { once: true });
                        try { buffer.appendBuffer(part.value); } catch (error) { clean(); reject(error); }
                    });
                    if (first) { first = false; if (onReady) onReady(); }
                }
                if (first) throw new Error('音频为空。');
                if (media.readyState === 'open') media.endOfStream();
            } catch (error) {
                if (media.readyState === 'open') { try { media.endOfStream('network'); } catch (_) {} }
                throw error;
            } finally {
                clearTimeout(timer);
                if (channels.get(channel) === job) channels.delete(channel);
            }
        })();
        done.catch(() => {});
        return { url, done, dispose };
    }

    class AudioUrlStore {
        constructor(maxEntries = 24, maxBytes = 24 * 1024 * 1024) {
            this.entries = new Map(); this.maxEntries = maxEntries; this.maxBytes = maxBytes;
            this.bytes = 0; this.pinned = null;
        }
        add(blob) {
            const url = URL.createObjectURL(blob);
            this.entries.set(url, blob.size); this.bytes += blob.size;
            this.trim(url);
            return url;
        }
        pin(url) { this.pinned = url; this.trim(url); }
        has(url) { return this.entries.has(url); }
        trim(newest) {
            for (const [url, size] of this.entries) {
                if (this.entries.size <= this.maxEntries && this.bytes <= this.maxBytes) break;
                if (url === this.pinned || url === newest) continue;
                URL.revokeObjectURL(url); this.entries.delete(url); this.bytes -= size;
            }
        }
        clear() {
            for (const url of this.entries.keys()) URL.revokeObjectURL(url);
            this.entries.clear(); this.bytes = 0; this.pinned = null;
        }
    }
    global.VoiceClient = Object.freeze({ TTS_TIMEOUT_MS, fishDefaults, normalizeFish, buildPayload,
        requestJson, requestAudio, requestStream, cancel, cancelAll, AudioUrlStore });
})(typeof window === 'undefined' ? globalThis : window);
