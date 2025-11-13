import type { QueryRequest, Source } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export class ApiService {
  static async askQuestion(request: QueryRequest): Promise<ReadableStream<Uint8Array>> {
    console.log('🌐 [API] 요청 URL:', `${API_BASE_URL}/api/ask`);
    console.log('📤 [API] 요청 데이터:', request);
    
    const response = await fetch(`${API_BASE_URL}/api/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    console.log('📥 [API] 응답 상태:', response.status);
    console.log('📋 [API] 응답 헤더:', Object.fromEntries(response.headers.entries()));

    if (!response.ok) {
      const errorText = await response.text();
      console.error('❌ [API] 에러 응답:', errorText);
      throw new Error(`HTTP error! status: ${response.status}, body: ${errorText}`);
    }

    console.log('✅ [API] 스트림 반환');
    return response.body!;
  }

  static async getSources(query: string): Promise<Source[]> {
    const response = await fetch(`${API_BASE_URL}/api/sources?query=${encodeURIComponent(query)}`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }
}
