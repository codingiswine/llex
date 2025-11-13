export interface Source {
  law_name: string;
  article_number: string;
  title: string;
  text: string;
  similarity: number;
  // SourcesTab에서 사용하는 필드들 추가
  relevance?: number;
  summary?: string;
  domain?: string;
  link?: string;
}


export interface QueryRequest {
  question: string;
  search_mode: "general" | "law";
}

export interface AskResponse {
  answer: string;
  sources?: Source[];
}
