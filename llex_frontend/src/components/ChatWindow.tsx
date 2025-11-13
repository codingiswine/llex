import React, { useEffect, useRef, useState } from "react";
import ChatMessage from "./ChatMessage";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface ChatWindowProps {
  messages: { role: string; content: string }[];
  activeQuestion: string | null;
  onStreamStart?: () => void;
  onStreamComplete?: (answer: string) => void;
  onStreamError?: (message: string) => void;
}

const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  activeQuestion,
  onStreamStart,
  onStreamComplete,
  onStreamError,
}) => {
  const [answer, setAnswer] = useState("");
  const [statusMessages, setStatusMessages] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const streamStartRef = useRef(onStreamStart);
  const streamCompleteRef = useRef(onStreamComplete);
  const streamErrorRef = useRef(onStreamError);

  useEffect(() => {
    streamStartRef.current = onStreamStart;
  }, [onStreamStart]);

  useEffect(() => {
    streamCompleteRef.current = onStreamComplete;
  }, [onStreamComplete]);

  useEffect(() => {
    streamErrorRef.current = onStreamError;
  }, [onStreamError]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, answer, statusMessages]);

  useEffect(() => {
    if (!activeQuestion) {
      return;
    }

    let isCancelled = false;
    const controller = new AbortController();
    const decoder = new TextDecoder("utf-8");
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    let buffer = "";
    let latestAnswer = "";

    const pushStatus = (message: unknown, isError = false) => {
      const text =
        typeof message === "string"
          ? message
          : message !== undefined
          ? JSON.stringify(message)
          : "";
      if (!text) {
        return;
      }
      setStatusMessages((prev) => [
        ...prev,
        isError ? `❌ ${text}` : text,
      ]);
    };

    const handleLine = (rawLine: string) => {
      const line = rawLine.trim();
      if (!line) return;
    
      // ✅ "data:" 접두어 제거
      const cleanLine = line.startsWith("data:") ? line.replace(/^data:\s*/, "") : line;
    
      try {
        const data = JSON.parse(cleanLine);
        const eventType = data.event || data.type;
    
        switch (eventType) {
          case "text": {
            const payload = typeof data.payload === "string" ? data.payload : "";
            latestAnswer += payload;
            setAnswer((prev) => prev + payload);
            break;
          }
          case "status":
            pushStatus(data.payload);
            break;
          case "error":
            pushStatus(data.payload, true);
            break;
          default:
            break;
        }
      } catch (err) {
        console.error("Stream parse error:", err, line);
      }
    };
    

    const fetchStream = async () => {
      try {
        setAnswer("");
        setStatusMessages([]);
        setIsStreaming(true);
        streamStartRef.current?.();

        const response = await fetch(`${API_BASE_URL}/api/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: "linkcampus", question: activeQuestion }),
          signal: controller.signal,
        });

        if (!response.ok) {
          pushStatus(`HTTP ${response.status}: ${response.statusText}`, true);
          return;
        }

        if (!response.body) {
          pushStatus("서버에서 빈 스트림이 반환되었습니다.", true);
          return;
        }

        reader = response.body.getReader();

        while (!isCancelled) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            handleLine(line);
          }
        }

        if (buffer.trim()) {
          handleLine(buffer);
        }
      } catch (error) {
        if (isCancelled) return;
        const message =
          error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";
        pushStatus(message, true);
        streamErrorRef.current?.(message);
      } finally {
        if (!isCancelled) {
          setIsStreaming(false);
          streamCompleteRef.current?.(latestAnswer);
        }
      }
    };

    fetchStream();

    return () => {
      isCancelled = true;
      controller.abort();
      if (reader) {
        reader.cancel().catch(() => undefined);
      }
    };
  }, [activeQuestion]);

  useEffect(() => {
    if (!isStreaming && !activeQuestion) {
      setAnswer("");
      setStatusMessages([]);
    }
  }, [isStreaming, activeQuestion]);

  const shouldShowLiveAnswer = isStreaming || (!!answer && activeQuestion);

  return (
    <div className="space-y-4">
      {messages.map((msg, idx) => (
        <ChatMessage
          key={`${msg.role}-${idx}-${msg.content.slice(0, 20)}`}
          role={msg.role}
          content={msg.content}
        />
      ))}

      {shouldShowLiveAnswer && (
        <div className="p-4 sm:p-6 bg-white/70 border border-gray-100 rounded-2xl shadow-sm space-y-3">
          <div
            className={`bg-gray-50 rounded-xl px-4 py-3 shadow-inner whitespace-pre-wrap text-sm leading-relaxed text-gray-800 transition-all ${
              isStreaming ? "animate-pulse" : ""
            }`}
          >
            {answer || "답변을 생성 중입니다..."}
          </div>
          <div className="space-y-1">
            {statusMessages.map((msg, i) => (
              <div
                key={`${msg}-${i}`}
                className={`text-sm ${
                  msg.startsWith("❌") ? "text-red-500" : "text-gray-400"
                }`}
              >
                {msg}
              </div>
            ))}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
};

export default ChatWindow;
