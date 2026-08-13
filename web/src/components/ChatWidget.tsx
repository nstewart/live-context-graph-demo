import { useState, useRef, useEffect } from 'react';
import { MessageCircle, Trash2, X, Send, ChevronDown, ChevronRight, Maximize2, Minimize2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useChat, ChatMessage, ThinkingEvent } from '../contexts/ChatContext';
import label from '../label';

// Format timestamp for display
function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Truncate long content and add ellipsis indicator
function truncateContent(content: string | undefined, maxLength: number = 200): { text: string; truncated: boolean } {
  if (!content) return { text: '', truncated: false };
  if (content.length <= maxLength) return { text: content, truncated: false };
  return { text: content.slice(0, maxLength), truncated: true };
}

// Thinking indicator component - shows tool calls and thinking in real-time
function ThinkingDisplay({ events, isLive }: { events: ThinkingEvent[]; isLive: boolean }) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (events.length === 0) return null;

  return (
    <div className={`text-xs space-y-1 ${isLive ? 'animate-pulse' : ''}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1 text-gray-400 hover:text-gray-300"
      >
        {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span>{events.length} step{events.length !== 1 ? 's' : ''}</span>
      </button>
      {isExpanded && (
        <div className="space-y-1 pl-4 border-l border-gray-700">
          {events.map((event, idx) => (
            <div key={idx} className="flex items-start gap-2 text-gray-400">
              {event.type === 'tool_call' && (
                <div className="flex flex-wrap items-center gap-1">
                  <span className="text-blue-400">Calling</span>
                  <span className="font-mono text-cyan-400">{event.data.name}</span>
                  {event.data.args && Object.keys(event.data.args).length > 0 && (
                    (() => {
                      const argsStr = Object.entries(event.data.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ');
                      const { text, truncated } = truncateContent(argsStr, 100);
                      return (
                        <span className="text-gray-500">
                          ({text}{truncated && '...'})
                        </span>
                      );
                    })()
                  )}
                </div>
              )}
              {event.type === 'tool_result' && (
                <div className="flex items-start gap-1">
                  <span className="text-green-400 shrink-0">Result:</span>
                  <span className="text-gray-300 break-words">{event.data.content}</span>
                </div>
              )}
              {event.type === 'thinking' && (
                <span className="text-purple-400 italic break-words">{event.data.content}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Message bubble component
function MessageBubble({ message, isStreaming }: { message: ChatMessage; isStreaming: boolean }) {
  const isUser = message.role === 'user';
  const showThinking = message.thinking && message.thinking.length > 0;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 ${
          isUser
            ? 'bg-brand-600 text-white'
            : 'bg-gray-800 text-gray-100'
        }`}
      >
        {/* Thinking events (for assistant messages) */}
        {!isUser && showThinking && (
          <div className="mb-2 pb-2 border-b border-gray-700">
            <ThinkingDisplay
              events={message.thinking!}
              isLive={isStreaming && message.status === 'streaming'}
            />
          </div>
        )}

        {/* Message content */}
        {message.status === 'streaming' && !message.content ? (
          <div className="flex items-center gap-2 text-gray-400">
            <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
            <span>Thinking...</span>
          </div>
        ) : message.status === 'error' ? (
          <span className="text-red-400">{message.content}</span>
        ) : (
          <div className="text-sm prose prose-invert prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-headings:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-xs mt-1 ${isUser ? 'text-green-200' : 'text-gray-500'}`}>
          {formatTime(message.timestamp)}
        </div>
      </div>
    </div>
  );
}

// Chat input component with auto-growing textarea
function ChatInput() {
  const { sendMessage, isStreaming } = useChat();
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isStreaming) {
      sendMessage(input);
      setInput('');
      // Reset textarea height after sending
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  // Handle Enter to submit, Shift+Enter for new line
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !isStreaming) {
        sendMessage(input);
        setInput('');
        if (textareaRef.current) {
          textareaRef.current.style.height = 'auto';
        }
      }
    }
  };

  // Auto-resize textarea as content grows
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Reset height to auto to get the correct scrollHeight
    e.target.style.height = 'auto';
    // Set height to scrollHeight, capped at 150px
    e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
  };

  // Focus input when widget opens
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 p-3 border-t border-gray-700 items-end">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={label.agent.placeholder}
        disabled={isStreaming}
        rows={1}
        className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50 resize-none overflow-y-auto"
        style={{ minHeight: '40px', maxHeight: '150px' }}
      />
      <button
        type="submit"
        disabled={!input.trim() || isStreaming}
        className="px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium flex items-center gap-1 shrink-0"
      >
        <Send className="h-4 w-4" />
      </button>
    </form>
  );
}

// Chat panel content - shared between normal and expanded views
function ChatPanelContent({
  isExpanded,
  onToggleExpand
}: {
  isExpanded: boolean;
  onToggleExpand: () => void;
}) {
  const { messages, setIsOpen, isStreaming, clearMessages, currentThinking, threadId } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentThinking]);

  return (
    <div className="flex flex-col h-full bg-gray-900 border-l border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-5 w-5 text-green-500" />
          <span className="font-medium text-white">{label.agent.persona}</span>
          {isStreaming && (
            <span className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onToggleExpand}
            className="p-1.5 hover:bg-gray-800 rounded transition-colors"
            title={isExpanded ? "Collapse to panel" : "Expand to full screen"}
          >
            {isExpanded ? (
              <Minimize2 className="h-4 w-4 text-gray-400 hover:text-green-400" />
            ) : (
              <Maximize2 className="h-4 w-4 text-gray-400 hover:text-green-400" />
            )}
          </button>
          <button
            onClick={clearMessages}
            className="p-1.5 hover:bg-gray-800 rounded transition-colors"
            title="Clear chat"
          >
            <Trash2 className="h-4 w-4 text-gray-400 hover:text-red-400" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 hover:bg-gray-800 rounded transition-colors"
            title="Close panel"
          >
            <X className="h-4 w-4 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Thread ID indicator */}
      {threadId && (
        <div className="px-3 py-1 bg-gray-800/50 text-xs text-gray-500 border-b border-gray-700 shrink-0">
          Session: <span className="font-mono">{threadId}</span>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 text-sm">
            <MessageCircle className="h-12 w-12 mb-2 opacity-50" />
            <p className="text-center px-4">{label.agent.empty_state}</p>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                isStreaming={isStreaming}
              />
            ))}
            {/* Live thinking indicator during streaming */}
            {isStreaming && currentThinking.length > 0 && (
              <div className="bg-gray-800 rounded-lg px-3 py-2">
                <ThinkingDisplay events={currentThinking} isLive={true} />
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <ChatInput />
    </div>
  );
}

// Main widget component
export default function ChatWidget() {
  const { messages, isOpen, setIsOpen, isExpanded, setIsExpanded } = useChat();

  // Handle escape key to close expanded view
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isExpanded) {
        setIsExpanded(false);
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isExpanded, setIsExpanded]);

  // Floating bubble when closed - positioned above the PropagationWidget (h-10 = 40px)
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-16 right-6 h-14 w-14 bg-brand-600 hover:bg-brand-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all z-50 hover:scale-105"
        title={`Open ${label.agent.persona}`}
      >
        <MessageCircle className="h-6 w-6" />
        {messages.length > 0 && (
          <span className="absolute -top-1 -right-1 h-5 w-5 bg-red-500 rounded-full text-xs flex items-center justify-center font-medium">
            {messages.length}
          </span>
        )}
      </button>
    );
  }

  // Expanded modal mode
  if (isExpanded) {
    return (
      <>
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-black/60 z-50"
          onClick={() => setIsExpanded(false)}
        />
        {/* Modal */}
        <div className="fixed inset-4 md:inset-8 lg:inset-12 z-50 flex items-center justify-center">
          <div className="w-full h-full max-w-6xl bg-gray-900 rounded-lg shadow-2xl overflow-hidden">
            <ChatPanelContent
              isExpanded={true}
              onToggleExpand={() => setIsExpanded(false)}
            />
          </div>
        </div>
      </>
    );
  }

  // Panel mode when open - NOT fixed positioning, fills parent container
  return (
    <ChatPanelContent
      isExpanded={false}
      onToggleExpand={() => setIsExpanded(true)}
    />
  );
}
