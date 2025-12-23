import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';

// Types for chat
export interface ThinkingEvent {
  type: 'tool_call' | 'tool_result' | 'thinking';
  timestamp: number;
  data: {
    name?: string;
    args?: Record<string, unknown>;
    content?: string;
    tool_call_id?: string;
  };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  status: 'sending' | 'streaming' | 'complete' | 'error';
  thinking?: ThinkingEvent[];
}

interface ChatContextValue {
  messages: ChatMessage[];
  isOpen: boolean;
  isStreaming: boolean;
  threadId: string | null;
  currentThinking: ThinkingEvent[];
  setIsOpen: (open: boolean) => void;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

// Agent API URL - configurable via environment with validation
const getAgentApiUrl = (): string => {
  const url = import.meta.env.VITE_AGENT_URL;
  if (url && typeof url === 'string' && url.trim() !== '') {
    return url;
  }
  // Fallback to localhost in development
  return 'http://localhost:8081';
};

const AGENT_API_URL = getAgentApiUrl();

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [currentThinking, setCurrentThinking] = useState<ThinkingEvent[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Generate unique ID for messages
  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  // Send a message and stream the response
  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isStreaming) return;

    // Add user message
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: Date.now(),
      status: 'complete',
    };

    // Add placeholder for assistant response
    const assistantMessageId = generateId();
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      status: 'streaming',
      thinking: [],
    };

    setMessages(prev => [...prev, userMessage, assistantMessage]);
    setIsStreaming(true);
    setCurrentThinking([]);

    // Create abort controller for this request
    abortControllerRef.current = new AbortController();

    // Timeout handler
    const timeoutId = setTimeout(() => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    }, 120000); // 2 minute timeout

    // Declare variables at function scope so they're accessible in finally block
    let responseContent = '';
    const thinkingEvents: ThinkingEvent[] = [];

    try {
      const response = await fetch(`${AGENT_API_URL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          message: content.trim(),
          thread_id: threadId,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      // Get thread_id from response header
      const newThreadId = response.headers.get('X-Thread-Id');
      if (newThreadId && !threadId) {
        setThreadId(newThreadId);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              // Parse each SSE event safely
              let event;
              try {
                event = JSON.parse(line.slice(6));
              } catch (parseError) {
                console.error('Failed to parse SSE event:', parseError, 'Raw line:', line);
                continue; // Skip malformed events
              }

              try {
                switch (event.type) {
                  case 'tool_call': {
                    const toolCallEvent: ThinkingEvent = {
                      type: 'tool_call',
                      timestamp: Date.now(),
                      data: event.data,
                    };
                    thinkingEvents.push(toolCallEvent);
                    setCurrentThinking(prev => [...prev, toolCallEvent]);
                    break;
                  }

                  case 'tool_result': {
                    const toolResultEvent: ThinkingEvent = {
                      type: 'tool_result',
                      timestamp: Date.now(),
                      data: event.data,
                    };
                    thinkingEvents.push(toolResultEvent);
                    setCurrentThinking(prev => [...prev, toolResultEvent]);
                    break;
                  }

                  case 'thinking': {
                    const thinkingEvent: ThinkingEvent = {
                      type: 'thinking',
                      timestamp: Date.now(),
                      data: { content: event.data.content },
                    };
                    thinkingEvents.push(thinkingEvent);
                    setCurrentThinking(prev => [...prev, thinkingEvent]);
                    break;
                  }

                  case 'response':
                    responseContent = event.data;
                    break;

                  case 'error':
                    throw new Error(event.data.message);

                  case 'done':
                    // Finalize message
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantMessageId
                        ? {
                            ...msg,
                            content: responseContent,
                            status: 'complete' as const,
                            thinking: thinkingEvents,
                          }
                        : msg
                    ));
                    break;
                }
              } catch (eventError) {
                console.error('Failed to process SSE event:', eventError, 'Event type:', event?.type);
              }
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        // Request was cancelled
        setMessages(prev => prev.map(msg =>
          msg.id === assistantMessageId
            ? { ...msg, status: 'error' as const, content: 'Request cancelled' }
            : msg
        ));
      } else {
        console.error('Chat error:', error);
        setMessages(prev => prev.map(msg =>
          msg.id === assistantMessageId
            ? { ...msg, status: 'error' as const, content: `Error: ${(error as Error).message}` }
            : msg
        ));
      }
    } finally {
      // Clear timeout
      clearTimeout(timeoutId);

      // Ensure message is finalized even if stream didn't complete properly
      setMessages(prev => prev.map(msg => {
        if (msg.id === assistantMessageId && msg.status === 'streaming') {
          return {
            ...msg,
            status: 'complete' as const,
            content: responseContent || 'Stream ended unexpectedly',
            thinking: thinkingEvents,
          };
        }
        return msg;
      }));

      setIsStreaming(false);
      setCurrentThinking([]);
      abortControllerRef.current = null;
    }
  }, [threadId, isStreaming]);

  // Clear all messages and start fresh
  const clearMessages = useCallback(() => {
    setMessages([]);
    setThreadId(null);
    setCurrentThinking([]);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages,
        isOpen,
        isStreaming,
        threadId,
        currentThinking,
        setIsOpen,
        sendMessage,
        clearMessages,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
