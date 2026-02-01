import React, { useState, useEffect } from 'react';
import { Upload, FileAudio, AlertCircle, Loader2, Download, Lock, Unlock } from 'lucide-react';

const API_Base = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

function App() {
    const [file, setFile] = useState(null);
    const [message, setMessage] = useState('');
    const [taskId, setTaskId] = useState(null);
    const [status, setStatus] = useState(null); // PENDING, PROCESSING, COMPLETED, ERROR
    const [resultUrl, setResultUrl] = useState(null);
    const [extractedMessage, setExtractedMessage] = useState(null);
    const [errorMsg, setErrorMsg] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isDragging, setIsDragging] = useState(false);

    // Mode: 'ENCODE' or 'DECODE'
    const [mode, setMode] = useState('ENCODE');

    // Poll for status
    useEffect(() => {
        if (!taskId || status === 'COMPLETED' || status === 'ERROR') return;

        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${API_Base}/tasks/${taskId}/`);
                const data = await res.json();

                setStatus(data.task_status);
                if (data.task_status === 'COMPLETED') {
                    if (data.task_type === 'ENCODE') {
                        setResultUrl(data.processed_file);
                    } else {
                        setExtractedMessage(data.hidden_message);
                    }
                } else if (data.task_status === 'ERROR') {
                    setErrorMsg(data.error_message || 'Unknown error occurred');
                }
            } catch (err) {
                console.error("Polling error", err);
            }
        }, 2000);

        return () => clearInterval(interval);
    }, [taskId, status, extractedMessage]);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const onDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const onDragLeave = (e) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const onDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
        }
    };

    const handleDownload = async (e) => {
        e.preventDefault();
        if (!resultUrl) return;

        try {
            // Construct absolute URL using API_Base
            // This correctly resolves /media/... against the API domain
            const downloadUrl = resultUrl.startsWith('http') ? resultUrl : new URL(resultUrl, API_Base).href;

            const response = await fetch(downloadUrl);
            if (!response.ok) throw new Error('Download failed');

            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);

            // Create temp link to force download
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = downloadUrl.split('/').pop() || 'stego_audio.wav';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (err) {
            console.error("Download error:", err);
            setErrorMsg("Failed to download file: " + err.message);
            // Don't set status to ERROR here to keep the completed state visible
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!file) return;
        if (mode === 'ENCODE' && !message) return;

        setIsSubmitting(true);
        setTaskId(null);
        setStatus(null);
        setResultUrl(null);
        setExtractedMessage(null);
        setErrorMsg(null);

        const formData = new FormData();
        formData.append('original_file', file);
        formData.append('task_type', mode);

        if (mode === 'ENCODE') {
            formData.append('hidden_message', message);
        }

        try {
            const res = await fetch(`${API_Base}/tasks/`, {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(JSON.stringify(errorData));
            }

            const data = await res.json();
            setTaskId(data.id);
            setStatus(data.task_status);
        } catch (err) {
            console.error("Upload error", err);
            setErrorMsg(err.message || 'Upload failed');
            setStatus('ERROR');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="container">
            <div className="card">
                <h1 className="title">SonicTag Web</h1>

                {/* Mode Toggle */}
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '2rem', gap: '1rem' }}>
                    <button
                        className={`btn ${mode === 'ENCODE' ? 'active' : ''}`}
                        style={{ width: 'auto', opacity: mode === 'ENCODE' ? 1 : 0.5 }}
                        onClick={() => { setMode('ENCODE'); setFile(null); setMessage(''); setStatus(null); setExtractedMessage(null); setResultUrl(null); setErrorMsg(null); }}
                    >
                        <Lock size={18} style={{ marginRight: '8px' }} /> Encode
                    </button>
                    <button
                        className={`btn ${mode === 'DECODE' ? 'active' : ''}`}
                        style={{ width: 'auto', opacity: mode === 'DECODE' ? 1 : 0.5 }}
                        onClick={() => { setMode('DECODE'); setFile(null); setMessage(''); setStatus(null); setExtractedMessage(null); setResultUrl(null); setErrorMsg(null); }}
                    >
                        <Unlock size={18} style={{ marginRight: '8px' }} /> Decode
                    </button>
                </div>

                <form onSubmit={handleSubmit}>
                    {/* File Upload Area */}
                    <div className="form-group">
                        <label>{mode === 'ENCODE' ? 'Source Audio' : 'Stego Audio (with hidden message)'}</label>
                        <div
                            className={`file-drop ${isDragging ? 'dragging' : ''}`}
                            onDragOver={onDragOver}
                            onDragLeave={onDragLeave}
                            onDrop={onDrop}
                            onClick={() => document.getElementById('fileInput').click()}
                            style={{
                                borderColor: isDragging ? '#3b82f6' : 'var(--border)',
                                backgroundColor: isDragging ? 'rgba(59, 130, 246, 0.05)' : 'transparent'
                            }}
                        >
                            {file ? (
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
                                    <FileAudio size={32} color="#3b82f6" />
                                    <span>{file.name}</span>
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
                                    <Upload size={32} color="#94a3b8" />
                                    <span>Click to select WAV/MP3 file</span>
                                </div>
                            )}
                            <input
                                id="fileInput"
                                type="file"
                                accept="audio/*"
                                onChange={handleFileChange}
                                style={{ display: 'none' }}
                            />
                        </div>
                    </div>

                    {/* Message Input - Only for Encode */}
                    {mode === 'ENCODE' && (
                        <div className="form-group">
                            <label>Hidden Message</label>
                            <textarea
                                rows={4}
                                placeholder="Enter the secret message needed to be hidden..."
                                value={message}
                                onChange={(e) => setMessage(e.target.value)}
                            />
                        </div>
                    )}

                    <button
                        type="submit"
                        className="btn"
                        disabled={!file || (mode === 'ENCODE' && !message) || isSubmitting}
                    >
                        {isSubmitting ? (
                            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                                <Loader2 className="animate-spin" size={20} /> Processing...
                            </span>
                        ) : (mode === 'ENCODE' ? 'Embed Watermark' : 'Extract Message')}
                    </button>
                </form>

                {/* Status Display */}
                {status && (
                    <div className="result-box">
                        <div style={{ textAlign: 'center' }}>
                            <h3>Status</h3>
                            <div className={`status-badge status-${status}`}>
                                {status}
                            </div>

                            {status === 'PROCESSING' && (
                                <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
                                    {mode === 'ENCODE' ? 'Encoding message into audio spectrum...' : 'Analyzing audio spectrum for hidden message...'}
                                </p>
                            )}

                            {status === 'ERROR' && (
                                <div style={{ marginTop: '1rem', color: 'var(--error)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                                    <AlertCircle size={20} />
                                    {errorMsg}
                                </div>
                            )}

                            {status === 'COMPLETED' && (
                                <div style={{ marginTop: '1.5rem' }}>
                                    {mode === 'ENCODE' && resultUrl && (
                                        <button
                                            onClick={handleDownload}
                                            className="btn"
                                            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', width: 'auto', backgroundColor: 'var(--success)' }}
                                        >
                                            <Download size={20} /> Download Stego Audio
                                        </button>
                                    )}

                                    {mode === 'DECODE' && extractedMessage && (
                                        <div className="message-box" style={{
                                            background: 'rgba(59, 130, 246, 0.1)',
                                            padding: '1.5rem',
                                            borderRadius: '8px',
                                            marginTop: '1rem',
                                            border: '1px solid rgba(59, 130, 246, 0.3)'
                                        }}>
                                            <h4 style={{ marginBottom: '0.5rem', color: '#3b82f6' }}>Extracted Message:</h4>
                                            <p style={{ fontSize: '1.2rem', fontWeight: '500' }}>{extractedMessage}</p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;
