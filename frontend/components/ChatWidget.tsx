"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { Lang, t } from "@/lib/i18n";

interface ChatMessage {
  sender: "user" | "bot";
  text: string;
}

/** Minimal safe markdown: **bold** and line breaks, rendered as React nodes. */
function renderText(text: string) {
  return text.split("\n").map((line, i) => (
    <span key={i}>
      {i > 0 && <br />}
      {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={j}>{part.slice(2, -2)}</strong>
        ) : (
          <span key={j}>{part}</span>
        )
      )}
    </span>
  ));
}

export default function ChatWidget({ lang }: { lang: Lang }) {
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  const startChat = useCallback(async () => {
    setError("");
    setMessages([]);
    setDone(false);
    setTyping(true);
    try {
      const resp = await fetch(`${API_URL}/api/chat/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: lang }),
      });
      const body = await resp.json();
      setConversationId(body.conversation_id);
      setMessages([{ sender: "bot", text: body.bot_message }]);
      setQuickReplies(body.quick_replies || []);
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setTyping(false);
    }
  }, [lang]);

  useEffect(() => {
    if (open && !conversationId) startChat();
  }, [open, conversationId, startChat]);

  async function send(text: string) {
    if (!conversationId || !text.trim() || typing || done) return;
    setInput("");
    setQuickReplies([]);
    setError("");
    setMessages((m) => [...m, { sender: "user", text }]);
    setTyping(true);

    // Stream the reply over SSE; fall back to POST on failure.
    try {
      await streamReply(text);
    } catch {
      try {
        const resp = await fetch(`${API_URL}/api/chat/${conversationId}/msg`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.detail);
        setMessages((m) => [...m, { sender: "bot", text: body.bot_message }]);
        setQuickReplies(body.quick_replies || []);
        if (body.done) setDone(true);
      } catch {
        setError("Sorry, something went wrong. Please try again.");
      }
    } finally {
      setTyping(false);
    }
  }

  function streamReply(text: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const url = `${API_URL}/api/chat/${conversationId}/stream?text=${encodeURIComponent(text)}`;
      const source = new EventSource(url);
      let started = false;

      source.addEventListener("delta", (event) => {
        const { delta } = JSON.parse((event as MessageEvent).data);
        setTyping(false);
        setMessages((m) => {
          if (!started) return [...m, { sender: "bot", text: delta }];
          const copy = [...m];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            text: copy[copy.length - 1].text + delta,
          };
          return copy;
        });
        started = true;
      });

      source.addEventListener("meta", (event) => {
        const meta = JSON.parse((event as MessageEvent).data);
        setQuickReplies(meta.quick_replies || []);
        if (meta.done) setDone(true);
        source.close();
        resolve();
      });

      source.onerror = () => {
        source.close();
        if (!started) reject(new Error("SSE failed"));
        else resolve();
      };
    });
  }

  async function uploadFile(file: File) {
    if (!conversationId) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch(`${API_URL}/api/chat/${conversationId}/upload`, {
        method: "POST",
        body: form,
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.detail || "Upload failed");
      setMessages((m) => [...m, { sender: "user", text: `📎 ${file.name}` }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  }

  function restart() {
    setConversationId(null);
    setMessages([]);
    setQuickReplies([]);
    setDone(false);
    startChat();
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-indigo-600 px-5 py-3 text-white shadow-lg transition hover:bg-indigo-500"
      >
        <span className="text-xl">💬</span>
        <span className="font-medium">{t(lang, "chatOpen")}</span>
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[560px] w-[380px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
      <div className="flex items-center justify-between bg-indigo-600 px-4 py-3 text-white">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-lg">🤖</span>
          <div>
            <div className="text-sm font-semibold">{t(lang, "chatTitle")}</div>
            <div className="text-xs text-indigo-200">online 24/7</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={restart} title={t(lang, "chatRestart")} className="rounded p-1.5 hover:bg-white/15">
            ↺
          </button>
          <button onClick={() => setOpen(false)} className="rounded p-1.5 hover:bg-white/15">
            ✕
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4">
        {messages.map((message, i) => (
          <div key={i} className={`flex ${message.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                message.sender === "user"
                  ? "rounded-br-sm bg-indigo-600 text-white"
                  : "rounded-bl-sm border border-slate-200 bg-white text-slate-800"
              }`}
            >
              {renderText(message.text)}
            </div>
          </div>
        ))}
        {typing && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3">
              <span className="inline-flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </span>
            </div>
          </div>
        )}
        {error && <div className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}
        {done && (
          <div className="rounded-lg bg-emerald-50 px-3 py-2 text-center text-xs text-emerald-700">
            {t(lang, "chatDone")}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {quickReplies.length > 0 && !done && (
        <div className="flex flex-wrap gap-1.5 border-t border-slate-100 bg-white px-3 pt-2">
          {quickReplies.map((reply) => (
            <button
              key={reply}
              onClick={() => send(reply)}
              className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs text-indigo-700 transition hover:bg-indigo-100"
            >
              {reply}
            </button>
          ))}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-2 border-t border-slate-100 bg-white p-3"
      >
        <input
          ref={fileRef}
          type="file"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadFile(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          title={t(lang, "chatUpload")}
          onClick={() => fileRef.current?.click()}
          disabled={done || !conversationId}
          className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 disabled:opacity-40"
        >
          📎
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t(lang, "chatPlaceholder")}
          disabled={done}
          className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || typing || done}
          className="rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
