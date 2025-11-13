import React, { useState } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
}

const SearchBar: React.FC<SearchBarProps> = ({ onSearch }) => {
  const [query, setQuery] = useState("");
  const [isComposing, setIsComposing] = useState(false); // 한글 IME 입력 중 여부

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Enter는 줄바꿈, Enter는 검색 (단, 한글 조합 중이면 무시)
    if (e.key === "Enter" && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedQuery = query.trim();
    
    if (trimmedQuery) {
      console.log('🔍 [SearchBar] 검색 요청:', trimmedQuery);
      onSearch(trimmedQuery);
      setQuery("");
    } else {
      console.log('⚠️ [SearchBar] 빈 검색어 무시');
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex bg-white border border-gray-300 rounded-2xl shadow-md overflow-hidden"
    >
      <textarea
        placeholder="무엇을 도와드릴까요? (Shift + Enter: 줄바꿈)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => {
          setIsComposing(true);
        }}
        onCompositionEnd={() => {
          setIsComposing(false);
        }}
        rows={1}
        className="flex-grow px-4 py-3 outline-none text-gray-700 resize-none"
      />
      <button
        type="submit"
        disabled={!query.trim() || isComposing}
        className="px-4 bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        검색
      </button>
    </form>
  );
};

export default SearchBar;
