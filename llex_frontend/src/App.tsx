import { useCallback, useState } from "react";
import Sidebar from "./components/Sidebar";
import SearchBar from "./components/SearchBar";
import ChatWindow from "./components/ChatWindow";

function App() {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "안녕하세요 👋 LLeX.Ai 입니다. 무엇을 도와드릴까요?" },
  ]);
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null);

  const handleSearch = (query: string) => {
    if (!query.trim()) return;
    
    console.log('🔍 [프론트엔드] 검색 시작:', query);
    
    const userMessage = { role: "user", content: query };
    setMessages(prev => [...prev, userMessage]);

    setActiveQuestion(query);
  };

  const handleStreamComplete = useCallback((answer: string) => {
    if (answer.trim()) {
      setMessages((prev) => [...prev, { role: "assistant", content: answer }]);
    }
    setActiveQuestion(null);
  }, []);

  const handleStreamError = useCallback((message: string) => {
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: `죄송합니다. 오류가 발생했습니다: ${message}`,
      },
    ]);
    setActiveQuestion(null);
  }, []);

  return (
    <div className="flex h-screen bg-gray-50 text-gray-800 overflow-hidden">
      {/* Sidebar */}
      <Sidebar isOpen={isSidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* 햄버거 버튼 - 메인 컨테이너 밖으로 이동 */}
      <button
        onClick={() => setSidebarOpen(true)}
        className="fixed top-4 left-4 p-3 rounded-lg bg-white shadow-lg hover:bg-gray-100 z-50 border border-gray-200"
      >
        ☰
      </button>

      {/* Main Content */}
      <div className="flex flex-col flex-1 items-center justify-center relative min-h-screen overflow-x-hidden">
      <h1 className="text-center text-5xl sm:text-6xl font-extrabold italic tracking-tight text-gray-900 mb-6">
        LLeX.Ai
      </h1>
        





          


        {/* 채팅창 */}
        <div className="flex flex-col w-full max-w-sm sm:max-w-md md:max-w-lg lg:max-w-xl xl:max-w-2xl px-2 sm:px-4">
          <div className="h-[60vh] sm:h-[65vh] bg-white rounded-2xl shadow-md border border-gray-200 p-3 sm:p-4 overflow-y-auto">
            <ChatWindow 
              messages={messages}
              activeQuestion={activeQuestion}
              onStreamComplete={handleStreamComplete}
              onStreamError={handleStreamError}
            />
          </div>

          {/* 검색창 */}
          <div className="w-full mt-4 mb-4">
            <SearchBar onSearch={handleSearch} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
