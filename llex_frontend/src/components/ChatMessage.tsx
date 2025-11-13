import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatMessageProps {
  role: string;
  content: string;
}

interface MarkdownProps {
  children?: React.ReactNode;
}

interface LinkProps {
  href?: string;
  children?: React.ReactNode;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ role, content }) => {
  const isUser = role === "user";
  
  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[90%] sm:max-w-[85%] md:max-w-[80%] lg:max-w-[75%] px-3 sm:px-4 py-2 rounded-2xl text-sm shadow-sm break-words overflow-hidden ${
          isUser
            ? "bg-blue-600 text-white rounded-br-none"
            : "bg-gray-200 text-gray-800 rounded-bl-none"
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-line break-words">{content}</div>
        ) : (
          <div className="prose prose-sm max-w-none" style={{ 
            wordBreak: 'break-word', 
            overflowWrap: 'break-word',
            hyphens: 'auto',
            maxWidth: '100%',
            overflow: 'hidden'
          }}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }: MarkdownProps) => (
                  <p className="mb-3 leading-relaxed" style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}>
                    {children}
                  </p>
                ),
                strong: ({ children }: MarkdownProps) => (
                  <strong className="font-bold text-gray-900">{children}</strong>
                ),
                hr: () => (
                  <hr className="my-6 border-gray-300" />
                ),
                a: ({ href, children }: LinkProps) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                    style={{ wordBreak: 'break-all' }}
                  >
                    {children}
                  </a>
                ),
                li: ({ children }: MarkdownProps) => (
                  <li className="mb-2 leading-relaxed" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </li>
                ),
                h1: ({ children }: MarkdownProps) => (
                  <h1 className="text-2xl font-bold mb-4 text-gray-900 border-b-2 border-gray-300 pb-2" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </h1>
                ),
                h2: ({ children }: MarkdownProps) => (
                  <h2 className="text-xl font-semibold mb-4 text-gray-800" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </h2>
                ),
                h3: ({ children }: MarkdownProps) => (
                  <h3 className="text-lg font-semibold mb-3 text-gray-700" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </h3>
                ),
                code: ({ children }: MarkdownProps) => (
                  <code className="bg-gray-100 px-2 py-1 rounded text-sm font-mono" style={{ wordBreak: 'break-all' }}>
                    {children}
                  </code>
                ),
                pre: ({ children }: MarkdownProps) => (
                  <pre className="bg-gray-100 p-4 rounded-lg text-sm font-mono" style={{ 
                    wordBreak: 'break-word', 
                    whiteSpace: 'pre-wrap',
                    overflow: 'hidden',
                    maxWidth: '100%'
                  }}>
                    {children}
                  </pre>
                ),
                blockquote: ({ children }: MarkdownProps) => (
                  <blockquote className="border-l-4 border-gray-300 pl-4 my-4 italic text-gray-700 bg-gray-50 py-2" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </blockquote>
                ),
                ul: ({ children }: MarkdownProps) => (
                  <ul className="list-disc ml-6 mb-4 space-y-2" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </ul>
                ),
                ol: ({ children }: MarkdownProps) => (
                  <ol className="list-decimal ml-6 mb-4 space-y-2" style={{ wordBreak: 'break-word' }}>
                    {children}
                  </ol>
                ),
              }}
            >
              {String(content || "").replaceAll("\\n", "\n")}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatMessage;
