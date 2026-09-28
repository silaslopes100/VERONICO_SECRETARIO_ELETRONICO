import { useCallback, useRef, useState } from "react";
import { api } from "../services/api";

/**
 * Captura o microfone no navegador (MediaRecorder) e devolve o Blob de áudio,
 * que é enviado ao backend para transcrição com Whisper.
 */
export function useVoiceRecorder() {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microfone indisponível");
      setRecording(false);
    }
  }, []);

  const stop = useCallback((): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      setRecording(false);
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      recorder.onstop = () => {
        recorder.stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        recorderRef.current = null;
        setRecording(false);
        resolve(blob.size > 0 ? blob : null);
      };
      recorder.stop();
    });
  }, []);

  const recordAndTranscribe = useCallback(async (): Promise<string> => {
    await start();
    await new Promise((resolve) => setTimeout(resolve, 5000));
    const blob = await stop();
    if (!blob) return "";
    const { text } = await api.transcribeAudio(blob);
    return text;
  }, [start, stop]);

  return { recording, error, start, stop, recordAndTranscribe };
}
