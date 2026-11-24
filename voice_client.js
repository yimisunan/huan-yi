(function (global) {
    'use strict';
    const TTS_TIMEOUT_MS = 65000;
    const fishDefaults = Object.freeze({
        speed: 1, volume: 0, normalize_loudness: true,
        temperature: 0.68, top_p: 0.75,
        latency: 'balanced', chunk_length: 180, min_chunk_length: 40,
        repetition_penalty: 1.18, condition_on_previous_chunks: true,
        normalize: true, language: 'zh-CN', format: 'mp3',
        mp3_bitrate: 128, opus_bitrate: -1000, sample_rate: 44100,
        max_new_tokens: 1024, early_stop_threshold: 1.0,
        quality_guard: true,
        pronunciation_dictionary_id: '', pronunciation_dictionary_version: ''
    });
    const VOICE_CLIENT_HEADER = Object.freeze({ 'X-Voice-Client': '1' });
    const FORMAT_RATES = Object.freeze({
        mp3: [32000, 44100],
        opus: [48000],
        wav: [8000, 16000, 24000, 32000, 44100]
    });
    const channels = new Map();
    function number(value, fallback, min, max) {
        const n = parseFloat(value);
        return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : fallback;
    }
    function flag(value, fallback = true) {
        if (value === undefined || value === null) return fallback;
        if (typeof value === 'boolean') return value;
        const s = String(value).trim().toLowerCase();
        if (['1', 'true', 'yes', 'on'].includes(s)) return true;
        if (['0', 'false', 'no', 'off'].includes(s)) return false;
        return fallback;
    }
    function cleanToken(value, pattern, maxLen = 64) {
        const s = String(value == null ? '' : value).trim();
        if (!s || s.length > maxLen) return '';
        return pattern.test(s) ? s : '';
    }
    function normalizeFish(cfg = {}) {
        const chunk = Math.round(number(cfg.chunk_length, 180, 100, 300));
        const fmt = ['mp3', 'opus', 'wav'].includes(cfg.format) ? cfg.format : 'mp3';
        const mp3Rate = [64, 128, 192].includes(Number(cfg.mp3_bitrate)) ? Number(cfg.mp3_bitrate) : 128;
        const opusRate = [-1000, 24000, 32000, 48000, 64000].includes(Number(cfg.opus_bitrate)) ? Number(cfg.opus_bitrate) : -1000;
        const allowedRates = FORMAT_RATES[fmt];
        const rawRate = Number(cfg.sample_rate);
        const sampleRate = allowedRates.includes(rawRate) ? rawRate : allowedRates[allowedRates.length - 1];
        return {
            speed: +number(cfg.speed, 1, 0.5, 2).toFixed(2),
            volume: +number(cfg.volume, 0, -20, 20).toFixed(1),
            normalize_loudness: flag(cfg.normalize_loudness, true),
            temperature: +number(cfg.temperature, 0.68, 0, 1).toFixed(2),
            top_p: +number(cfg.top_p, 0.75, 0, 1).toFixed(2),
            latency: ['low', 'normal', 'balanced'].includes(cfg.latency) ? cfg.latency : 'balanced',
            chunk_length: chunk,
            min_chunk_length: Math.min(chunk, Math.round(number(cfg.min_chunk_length, 40, 0, 100))),
            repetition_penalty: +number(cfg.repetition_penalty, 1.18, 1, 2).toFixed(2),
            condition_on_previous_chunks: flag(cfg.condition_on_previous_chunks, true),
            normalize: flag(cfg.normalize, true),
            language: cfg.language === undefined || cfg.language === null ? fishDefaults.language : cleanToken(cfg.language, /^[A-Za-z0-9_-]{1,35}$/, 35),
            format: fmt,
            mp3_bitrate: mp3Rate,
            opus_bitrate: opusRate,
            sample_rate: sampleRate,
            max_new_tokens: Math.round(number(cfg.max_new_tokens, 1024, 128, 4096)),
            early_stop_threshold: +number(cfg.early_stop_threshold, 1.0, 0, 1).toFixed(2),
            quality_guard: flag(cfg.quality_guard, true),
            pronunciation_dictionary_id: cleanToken(cfg.pronunciation_dictionary_id, /^[A-Za-z0-9._:-]{1,128}$/, 128),
            pronunciation_dictionary_version: cleanToken(cfg.pronunciation_dictionary_version, /^[A-Za-z0-9._:-]{1,64}$/, 64)
        };
    }
    function buildPayload(text, cfg = {}, settings = {}, emotion = '', speaker = '', prosodyMod = null) {
        const voice = cfg.voice || 'fish:';
        const body = { text, voice, emotion };
        if (speaker) body.speaker = String(speaker);
        if (voice.startsWith('edge:')) {
            Object.assign(body, { rate: cfg.rate || '-8%', pitch: cfg.pitch || '-4Hz', volume: cfg.volume || '+0%', emotion: '' });
        } else {
            Object.assign(body, normalizeFish(cfg), { tts_model: cfg.tts_model || settings.fish_tts_model || 's2.1-pro-free' });
            if (prosodyMod && typeof prosodyMod === 'object') {
                const sc = number(prosodyMod.speed_scale, 1, 0.85, 1.10);
                if (Math.abs(sc - 1) >= 0.005) body.speed_scale = +sc.toFixed(2);
                const eb = number(prosodyMod.expressive_boost, 0, 0, 0.12);
                if (eb >= 0.01) body.expressive_boost = +eb.toFixed(2);
            }
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
            const headers = { ...VOICE_CLIENT_HEADER, ...(options.headers || {}) };
            const response = await checkedResponse(await fetch(url, { ...options, headers, signal: controller.signal }));
            return await response.json();
        } catch (error) {
            if (controller.signal.aborted) throw new Error('连接等待超时，请检查服务后重试。');
            throw error;
        } finally { clearTimeout(timer); }
    }
    function getFishKeyStatus() {
        return requestJson('/api/fish_key?t=' + Date.now(), { cache: 'no-store' }, 8000);
    }
    function saveFishKey(apiKey, verify = false) {
        return requestJson('/api/fish_key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: String(apiKey || '').trim(), verify: !!verify })
        }, verify ? 15000 : 8000);
    }
    function clearFishKey() {
        return requestJson('/api/fish_key', { method: 'DELETE' }, 8000);
    }
    function setVoiceTier(tier) {
        return requestJson('/api/voice_tier', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier: String(tier || 'free') })
        }, 10000);
    }
    function getAudioAssets() {
        return requestJson('/api/audio_assets?t=' + Date.now(), { cache: 'no-store' }, 6000);
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
                method: 'POST', headers: { 'Content-Type': 'application/json', ...VOICE_CLIENT_HEADER },
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
        const fmt = String(payload.format || 'mp3').toLowerCase();
        if (fmt !== 'mp3' || !global.MediaSource || !MediaSource.isTypeSupported('audio/mpeg') || String(payload.voice || '').startsWith('edge:')) return null;
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
                    method: 'POST', headers: { 'Content-Type': 'application/json', ...VOICE_CLIENT_HEADER },
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
    function prefetchBatch(items) {
        if (!Array.isArray(items) || !items.length) return Promise.resolve({ scheduled: 0 });
        const clean = items.slice(0, 6).filter(it => it && typeof it.text === 'string' && it.text.trim()).map(it => {
            const row = {
                text: it.text,
                speaker: it.speaker || '',
                voice: it.voice || ''
            };
            if (it.speed_scale !== undefined) row.speed_scale = it.speed_scale;
            if (it.expressive_boost !== undefined) row.expressive_boost = it.expressive_boost;
            return row;
        });
        if (!clean.length) return Promise.resolve({ scheduled: 0 });
        return fetch('/api/tts/prefetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...VOICE_CLIENT_HEADER },
            body: JSON.stringify({ items: clean })
        }).then(r => (r.ok ? r.json().catch(() => ({ scheduled: clean.length })) : { scheduled: 0 })).catch(() => ({ scheduled: 0 }));
    }

    function setVoiceRouting(patch) {
        return requestJson('/api/voice_routing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patch && typeof patch === 'object' ? patch : {})
        }, 10000);
    }

    global.VoiceClient = Object.freeze({ TTS_TIMEOUT_MS, fishDefaults, normalizeFish, buildPayload,
        requestJson, requestAudio, requestStream, prefetchBatch, cancel, cancelAll, AudioUrlStore,
        getFishKeyStatus, saveFishKey, clearFishKey, setVoiceTier, setVoiceRouting, getAudioAssets });
})(typeof window === 'undefined' ? globalThis : window);
