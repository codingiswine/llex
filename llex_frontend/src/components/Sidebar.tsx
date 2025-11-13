import React from "react";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  return (
    <div
      className={`fixed top-0 left-0 h-full w-64 bg-white shadow-lg transform transition-transform duration-300 z-50 ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <div className="flex justify-between items-center p-4 border-b">
        <h2 className="text-lg font-semibold">Menu</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
          ✕
        </button>
      </div>

      <div className="p-4 space-y-3">
        <button className="w-full text-left hover:text-blue-600">새 대화</button>
        <button className="w-full text-left hover:text-blue-600">저장된 대화</button>
        <button className="w-full text-left hover:text-blue-600">법령 목록</button>
      </div>
    </div>
  );
};

export default Sidebar;
