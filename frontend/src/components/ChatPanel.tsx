import { Bot, Loader2, Send, User } from "lucide-react";
import { useState } from "react";

import type { ChatMessage } from "../types/chat";

type ChatPanelProps = {
  messages: ChatMessage[];
  examples: string[];
  isLoading: boolean;
  error: string;
  onSubmit: (question: string) => void;
};

export function ChatPanel({ messages, examples, isLoading, error, onSubmit }: ChatPanelProps) {
  const [draft, setDraft] = useState("");

  function submitQuestion(question: string) {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) return;
    onSubmit(trimmedQuestion);
    setDraft("");
  }

  return (
    <>
      <div className="message-list">
        {messages.length === 0 ? (
          <div className="assistant-message">
            <span className="message-role">Agent</span>
            <p>等待查询</p>
          </div>
        ) : (
          messages.map((message) => <ChatMessageItem key={message.id} message={message} />)
        )}
      </div>

      <div className="example-row">
        {examples.map((example) => (
          <button
            className="example-button"
            disabled={isLoading}
            key={example}
            type="button"
            onClick={() => submitQuestion(example)}
          >
            {example}
          </button>
        ))}
      </div>

      <form
        className="question-form"
        onSubmit={(event) => {
          event.preventDefault();
          submitQuestion(draft);
        }}
      >
        <textarea
          aria-label="自然语言问题"
          disabled={isLoading}
          placeholder="输入自然语言问题"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submitQuestion(draft);
            }
          }}
        />
        <button
          className="send-button"
          disabled={isLoading || !draft.trim()}
          type="submit"
          aria-label="发送"
          title="发送"
        >
          {isLoading ? <Loader2 className="spin-icon" size={18} /> : <Send size={18} />}
        </button>
      </form>

      {error && <div className="chat-error">{error}</div>}
    </>
  );
}

function ChatMessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={isUser ? "chat-message user-chat-message" : "chat-message assistant-chat-message"}>
      <div className="chat-avatar" aria-hidden="true">
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className="chat-bubble">
        <div className="message-meta">
          <span>{isUser ? "You" : "Agent"}</span>
          {message.status && <strong>{message.status}</strong>}
          {typeof message.rowCount === "number" && <strong>{message.rowCount} rows</strong>}
        </div>
        <p>{message.content}</p>
      </div>
    </div>
  );
}
