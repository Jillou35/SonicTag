import React, { useState, useEffect, useRef } from 'react';
import { Send, Radio, Activity, Volume2, Wifi, Zap, Mic, ShieldCheck, Terminal, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import classNames from 'classnames';

function App() {
    const [mode, setMode] = useState('transmit');
    const modeRef = useRef(mode);
    useEffect(() => { modeRef.current = mode; }, [mode]);

    // Input Mode: 'url' or 'json'
    const [inputType, setInputType] = useState('url');
    const [urlInput, setUrlInput] = useState('https://github.com/jillou35');
    const [payload, setPayload] = useState(JSON.stringify({ status: "ok", id: 1 }, null, 2));

    const [messages, setMessages] = useState([]);
    const [isTransmitting, setIsTransmitting] = useState(false);
    const [isConnected, setIsConnected] = useState(false);
    const [isListening, setIsListening] = useState(false);
    const [packetsSent, setPacketsSent] = useState(0);
    const [sampleRate, setSampleRate] = useState(null);

    const socketRef = useRef(null);
    const audioContextRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const messagesEndRef = useRef(null);

    useEffect(() => {
        const connectWS = () => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/receive`;
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                setIsConnected(true);
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'message') {
                        const receivedData = msg.data;

                        // Auto-Open Logic for URL (Only if Listening)
                        if (modeRef.current === 'listen' && receivedData && receivedData.type === 'url' && receivedData.url) {
                            // Verify valid URL before opening to avoid security risks
                            try {
                                const urlObj = new URL(receivedData.url);
                                // Navigate in same tab
                                window.location.href = urlObj.href;
                            } catch (e) {
                                console.error("Invalid URL received:", receivedData.url);
                            }
                        }

                        setMessages(prev => [{
                            id: Date.now(),
                            timestamp: new Date().toLocaleTimeString(),
                            data: receivedData

                        }, ...prev].slice(0, 50));
                    }
                } catch (e) {
                    console.error("Parse error", e);
                }
            };

            ws.onclose = () => setIsConnected(false);
            socketRef.current = ws;
        }
        connectWS();

        return () => {
            if (socketRef.current) socketRef.current.close();
            stopListening();
        };
    }, []);

    const [audioDevices, setAudioDevices] = useState([]);
    const [selectedDeviceId, setSelectedDeviceId] = useState('');
    const [volume, setVolume] = useState(0);

    // Load Devices
    useEffect(() => {
        const getDevices = async () => {
            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                const inputs = devices.filter(d => d.kind === 'audioinput');
                setAudioDevices(inputs);

                if (inputs.length > 0 && !selectedDeviceId) {
                    setSelectedDeviceId(inputs[0].deviceId);
                }
            } catch (e) {
                console.error("Device Enumeration Error", e);
            }
        };

        getDevices();
        navigator.mediaDevices.ondevicechange = getDevices;

        return () => { navigator.mediaDevices.ondevicechange = null; }
    }, []);

    const startListening = async () => {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error("Microphone API not supported. Use HTTPS or Localhost.");
            }
            if (socketRef.current?.readyState !== WebSocket.OPEN) return;

            const constraints = {
                audio: {
                    deviceId: selectedDeviceId ? { exact: selectedDeviceId } : undefined,
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false,
                    googEchoCancellation: false,
                    googAutoGainControl: false,
                    googNoiseSuppression: false,
                    googHighpassFilter: false
                }
            };

            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            streamRef.current = stream;

            const track = stream.getAudioTracks()[0];
            const settings = track.getSettings();
            const nativeRate = settings.sampleRate || 48000;

            const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: nativeRate
            });
            audioContextRef.current = audioCtx;
            setSampleRate(nativeRate);

            if (socketRef.current?.readyState === WebSocket.OPEN) {
                socketRef.current.send(JSON.stringify({
                    type: "config",
                    sampleRate: nativeRate
                }));
            }

            if (audioCtx.state === 'suspended') {
                await audioCtx.resume();
            }

            const source = audioCtx.createMediaStreamSource(stream);

            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 256;
            source.connect(analyser);

            const processor = audioCtx.createScriptProcessor(4096, 1, 1);
            processorRef.current = processor;

            const dataArray = new Uint8Array(analyser.frequencyBinCount);

            processor.onaudioprocess = (e) => {
                analyser.getByteFrequencyData(dataArray);
                const avg = dataArray.reduce((p, c) => p + c, 0) / dataArray.length;
                setVolume(avg);

                if (socketRef.current?.readyState === WebSocket.OPEN) {
                    const inputData = e.inputBuffer.getChannelData(0);

                    const bufferCopy = new Float32Array(inputData);
                    socketRef.current.send(bufferCopy);
                    setPacketsSent(prev => prev + 1);
                }
            };

            source.connect(processor);
            processor.connect(audioCtx.destination);
            setIsListening(true);

        } catch (e) {
            console.error("Mic Access Error", e);
            alert("Microphone Error: " + e.message);
        }
    };

    const stopListening = () => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
        }
        if (processorRef.current) {
            processorRef.current.disconnect();
        }
        if (audioContextRef.current) {
            audioContextRef.current.close();
        }
        setIsListening(false);
        setVolume(0);
    };

    useEffect(() => {
        if (mode === 'listen') {
            startListening();
        } else {
            stopListening();
        }
    }, [mode, selectedDeviceId]);

    // Loop Logic
    const [isLooping, setIsLooping] = useState(false);

    useEffect(() => {
        let interval;
        if (isLooping && !isTransmitting) {
            interval = setInterval(() => {
                handleTransmit();
            }, 500);
        }
        return () => clearInterval(interval);
    }, [isLooping, isTransmitting, payload, inputType, urlInput]);

    const handleTransmit = async () => {
        try {
            if (isTransmitting) return;
            setIsTransmitting(true);

            let dataToSend;

            if (inputType === 'url') {
                // Validate URL
                try {
                    new URL(urlInput); // Will throw if invalid
                    dataToSend = { type: 'url', url: urlInput };
                } catch (e) {
                    alert("Please enter a valid URL (include http:// or https://)");
                    setIsTransmitting(false);
                    return;
                }
            } else {
                try {
                    dataToSend = JSON.parse(payload);
                } catch (e) {
                    alert("Invalid JSON");
                    setIsTransmitting(false);
                    return;
                }
            }

            const response = await fetch(`/api/transmit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ payload: dataToSend })
            });

            if (!response.ok) throw new Error("Server Error");

            const arrayBuffer = await response.arrayBuffer();

            let ctx = audioContextRef.current;
            if (!ctx) {
                ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
                audioContextRef.current = ctx;
                setSampleRate(ctx.sampleRate);
            }
            if (ctx.state === 'suspended') await ctx.resume();

            const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);

            source.onended = () => {
                setIsTransmitting(false);
            };

            source.start(0);

        } catch (e) {
            console.error(e);
            setIsTransmitting(false);
            setIsLooping(false);
        }
    };

    return (
        <div className="w-screen h-screen bg-slate-950 text-slate-100 font-sans flex items-center justify-center overflow-hidden relative selection:bg-cyan-500/30">

            {/* Background Ambience */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,rgba(6,182,212,0.1),transparent_50%)]" />
            <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 brightness-100 contrast-150 mix-blend-overlay" />

            <motion.div
                initial={{ scale: 0.95, opacity: 0, y: 10 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                className="relative w-full max-w-2xl bg-slate-900/80 backdrop-blur-xl rounded-3xl border border-slate-800 shadow-2xl flex flex-col md:flex-row overflow-hidden max-h-[90vh]"
            >

                {/* Sidebar / Navigation */}
                <div className="md:w-20 bg-slate-950/50 border-b md:border-b-0 md:border-r border-slate-800 flex md:flex-col items-center justify-between p-4 z-10">
                    <div className="p-2 bg-cyan-500/10 rounded-xl border border-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.1)]">
                        <Volume2 className="w-6 h-6 text-cyan-400" />
                    </div>

                    <div className="flex md:flex-col gap-4">
                        <NavButton
                            active={mode === 'transmit'}
                            onClick={() => setMode('transmit')}
                            icon={Send}
                            label="Transmit"
                        />
                        <NavButton
                            active={mode === 'listen'}
                            onClick={() => setMode('listen')}
                            icon={Radio}
                            label="Listen"
                        />
                    </div>

                    <div className="flex flex-col items-center gap-2">
                        <div className={classNames("w-2 h-2 rounded-full shadow-[0_0_10px_currentColor] transition-colors duration-500", isConnected ? "bg-emerald-500 text-emerald-500" : "bg-rose-500 text-rose-500")} />
                    </div>
                </div>

                {/* Main Content Area */}
                <div className="flex-1 flex flex-col min-h-[500px]">

                    {/* Header */}
                    <header className="p-6 pb-2">
                        <div className="flex justify-between items-center mb-1">
                            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                                SonicTag <span className="text-cyan-500">App</span>
                            </h1>
                            <div className="flex items-center gap-2 px-3 py-1 bg-slate-950 rounded-full border border-slate-800 text-xs font-mono text-slate-400">
                                <Terminal size={12} />
                                <span>v0.1.0</span>
                            </div>
                        </div>
                        <p className="text-slate-500 text-sm">Ultrasonic Data Transmission Protocol</p>
                    </header>

                    {/* Content View */}
                    <div className="flex-1 p-6 relative overflow-hidden">
                        <AnimatePresence mode="wait">

                            {mode === 'transmit' && (
                                <motion.div
                                    key="transmit"
                                    initial={{ opacity: 0, x: 10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -10 }}
                                    className="h-full flex flex-col gap-4"
                                >
                                    {/* Input Type Toggle */}
                                    <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 w-fit">
                                        <button
                                            onClick={() => setInputType('url')}
                                            className={classNames("px-3 py-1.5 text-xs font-medium rounded-lg transition-all", inputType === 'url' ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" : "text-slate-500 hover:text-slate-300")}
                                        >
                                            URL Link
                                        </button>
                                        <button
                                            onClick={() => setInputType('json')}
                                            className={classNames("px-3 py-1.5 text-xs font-medium rounded-lg transition-all", inputType === 'json' ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" : "text-slate-500 hover:text-slate-300")}
                                        >
                                            Raw JSON
                                        </button>
                                    </div>

                                    <div className="flex-1 relative group">
                                        <div className="absolute -inset-0.5 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-2xl opacity-20 blur group-focus-within:opacity-40 transition duration-500" />

                                        {inputType === 'url' ? (
                                            <div className="relative w-full h-full bg-slate-950 rounded-xl border border-slate-800 p-6 flex flex-col justify-center gap-2">
                                                <label className="text-xs text-slate-500 font-semibold uppercase tracking-wider">Target URL</label>
                                                <input
                                                    type="url"
                                                    value={urlInput}
                                                    onChange={(e) => setUrlInput(e.target.value)}
                                                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-cyan-300 font-mono focus:ring-2 focus:ring-cyan-500 outline-none"
                                                    placeholder="https://example.com"
                                                />
                                                <p className="text-xs text-slate-600">Receiver will auto-open this link upon detection.</p>
                                            </div>
                                        ) : (
                                            <>
                                                <div className="absolute top-0 right-0 p-3 flex gap-2">
                                                    <div className="px-2 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400 border border-slate-700">JSON</div>
                                                </div>
                                                <textarea
                                                    value={payload}
                                                    onChange={(e) => setPayload(e.target.value)}
                                                    className="relative w-full h-full bg-slate-950 rounded-xl border border-slate-800 p-4 font-mono text-sm text-cyan-100 placeholder-slate-700 focus:outline-none focus:border-cyan-500/50 resize-none transition-colors"
                                                    placeholder="// Enter JSON payload..."
                                                    spellCheck={false}
                                                />
                                            </>
                                        )}
                                    </div>

                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => setIsLooping(!isLooping)}
                                            className={classNames(
                                                "flex-1 group relative h-14 rounded-xl font-semibold text-white shadow-lg transition-all overflow-hidden",
                                                isLooping
                                                    ? "bg-gradient-to-r from-rose-600 to-orange-600 hover:from-rose-500 hover:to-orange-500 shadow-rose-900/20"
                                                    : "bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 shadow-cyan-900/20"
                                            )}
                                        >
                                            <div className="absolute inset-0 flex items-center justify-center gap-3 z-10">
                                                {isLooping ? (
                                                    <>
                                                        <Activity className="animate-spin" />
                                                        <span>Stop Broadcast</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <Zap className="fill-current" />
                                                        <span>Start Broadcast</span>
                                                    </>
                                                )}
                                            </div>
                                            {/* Shine effect only when active or hovering */}
                                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent skew-x-12 translate-x-[-150%] group-hover:animate-shine" />
                                        </button>
                                    </div>
                                </motion.div>
                            )}

                            {mode === 'listen' && (
                                <motion.div
                                    key="listen"
                                    initial={{ opacity: 0, x: 10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -10 }}
                                    className="h-full flex flex-col"
                                >
                                    {/* Listening Status Orb */}
                                    <div className="flex flex-col gap-4 mb-4 p-4 bg-slate-950/50 rounded-xl border border-slate-800/50">
                                        <div className="flex items-center gap-4">
                                            <div className="relative">
                                                <div className={classNames("w-10 h-10 rounded-full flex items-center justify-center transition-colors", isListening ? "bg-rose-500/20 text-rose-500" : "bg-slate-800 text-slate-500")}>
                                                    <Mic size={20} />
                                                </div>
                                                {isListening && (
                                                    <span className="absolute -top-1 -right-1 w-3 h-3 bg-rose-500 rounded-full border-2 border-slate-950 animate-pulse" />
                                                )}
                                            </div>
                                            <div className="flex-1">
                                                <h3 className="font-medium text-slate-200">
                                                    {isListening ? "Microphone Active" : "Microphone Inactive"}
                                                </h3>
                                                <p className="text-xs text-slate-500">
                                                    {isListening ? `Demodulating... (Sent: ${packetsSent}) ${sampleRate ? `| ${sampleRate}Hz` : ''}` : "Select input source"}
                                                </p>
                                            </div>

                                            {/* Volume Meter */}
                                            {isListening && (
                                                <div className="flex gap-1 items-end h-8 w-16 bg-slate-900/50 p-1 rounded border border-slate-800">
                                                    {/* Simple Volume Bar */}
                                                    <div
                                                        className="w-full bg-cyan-500 rounded-sm transition-all duration-75 ease-out"
                                                        style={{ height: `${Math.min(100, (volume / 255) * 400)}%` }} // Boost visual
                                                    />
                                                </div>
                                            )}
                                        </div>

                                        {/* Device Selector */}
                                        <div className="w-full">
                                            <select
                                                value={selectedDeviceId}
                                                onChange={(e) => setSelectedDeviceId(e.target.value)}
                                                className="w-full bg-slate-900 border border-slate-700 text-slate-300 text-xs rounded-lg p-2 focus:ring-1 focus:ring-cyan-500 outline-none"
                                            >
                                                {audioDevices.map(device => (
                                                    <option key={device.deviceId} value={device.deviceId}>
                                                        {device.label || `Microphone ${device.deviceId.slice(0, 5)}...`}
                                                    </option>
                                                ))}
                                                {audioDevices.length === 0 && <option>Default Microphone (System)</option>}
                                            </select>
                                        </div>
                                    </div>

                                    {/* Message Feed */}
                                    <div className="flex-1 bg-slate-950 rounded-xl border border-slate-800 relative overflow-hidden flex flex-col">
                                        <div className="absolute top-0 inset-x-0 h-6 bg-gradient-to-b from-slate-950 to-transparent z-10 pointer-events-none" />

                                        <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                                            <AnimatePresence initial={false}>
                                                {messages.map((msg) => (
                                                    <motion.div
                                                        key={msg.id}
                                                        initial={{ opacity: 0, y: 20, scale: 0.95 }}
                                                        animate={{ opacity: 1, y: 0, scale: 1 }}
                                                        className="bg-slate-900/50 hover:bg-slate-900 border border-slate-800 p-3 rounded-lg group transition-colors"
                                                    >
                                                        <div className="flex justify-between items-start mb-2 opacity-50 text-[10px] uppercase tracking-wider font-semibold">
                                                            <span className="flex items-center gap-1 text-cyan-400">
                                                                <ShieldCheck size={10} /> Verified
                                                            </span>
                                                            <span>{msg.timestamp}</span>
                                                        </div>
                                                        <div className="font-mono text-sm text-slate-300 break-all whitespace-pre-wrap">
                                                            {msg.data.type === 'url' ? (
                                                                <a href={msg.data.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-cyan-400 hover:text-cyan-300 underline underline-offset-4">
                                                                    <span>{msg.data.url}</span>
                                                                    <AlertCircle size={14} className="inline opacity-50" />
                                                                </a>
                                                            ) : (
                                                                <pre>{JSON.stringify(msg.data, null, 2)}</pre>
                                                            )}
                                                        </div>
                                                    </motion.div>
                                                ))}
                                            </AnimatePresence>
                                            {messages.length === 0 && (
                                                <div className="h-full flex flex-col items-center justify-center text-slate-700 gap-2 opacity-50">
                                                    <Radio size={48} strokeWidth={1} />
                                                    <p className="text-sm">No transmissions detected</p>
                                                </div>
                                            )}
                                            <div ref={messagesEndRef} />
                                        </div>

                                        <div className="absolute bottom-0 inset-x-0 h-6 bg-gradient-to-t from-slate-950 to-transparent z-10 pointer-events-none" />
                                    </div>
                                </motion.div>
                            )}

                        </AnimatePresence>
                    </div>
                </div>
            </motion.div >
        </div >
    );
}

function NavButton({ active, onClick, icon: Icon, label }) {
    return (
        <button
            onClick={onClick}
            className={classNames(
                "p-3 rounded-xl transition-all duration-300 relative group",
                active ? "bg-slate-800/50 text-cyan-400 shadow-lg shadow-cyan-900/10" : "text-slate-500 hover:text-slate-300 hover:bg-slate-900"
            )}
            title={label}
        >
            <Icon size={20} />
            {active && (
                <motion.div
                    layoutId="active-indicator"
                    className="absolute inset-y-0 -right-4 w-1 bg-cyan-500 rounded-l-full md:block hidden"
                />
            )}
            <span className="md:hidden sr-only">{label}</span>
        </button>
    )
}

export default App;
