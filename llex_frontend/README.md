# LLeX.Ai React Frontend

Vite + React + Tailwind 기반의 GPT 스타일 스트리밍 UI입니다.  
FastAPI 백엔드에서 전송하는 Server-Sent Events(SSE)를 파싱해 ChatGPT 와 유사한 타자 효과를 제공합니다.

---

## 🚀 Quick start

```bash
cd llex_frontend
npm install
npm run dev
```

브라우저에서 <http://localhost:5173> 에 접속하면 됩니다.

### Useful scripts
| 명령어            | 설명                         |
| ---------------- | ---------------------------- |
| `npm run dev`    | 개발 서버 (Vite)             |
| `npm run build`  | 프로덕션 번들 + 타입체크     |
| `npm run preview`| 빌드 결과 미리보기           |
| `npm run lint`   | ESLint 점검                  |

Node 18.18+ / npm 9+ 이상을 사용하세요 (`requirements.txt` 참고).

---

## 🧱 Project layout

```
src/
├── App.tsx                 # 루트 컴포넌트 (챗 UI 레이아웃)
├── main.tsx                # React 엔트리포인트
├── components/
│   ├── ChatWindow.tsx      # SSE 파싱 + 스트리밍 렌더링
│   ├── ChatMessage.tsx     # User/Assistant 말풍선 (Markdown 지원)
│   ├── SearchBar.tsx       # 질문 입력 + IME 대응
│   ├── Sidebar.tsx         # 좌측 세션 메뉴
│   └── LoadingDots.tsx     # 타이핑 프리뷰 애니메이션
├── services/
│   └── api.ts              # (선택) API 호출 유틸
└── styles / config 파일    # Tailwind, ESLint, TS 설정
```

핵심 특징
- `ChatWindow.tsx`에서 Fetch Streaming + JSON 파싱을 수행하여 `text/status/error` 이벤트를 실시간 표시합니다.
- `App.tsx`는 사용자 메시지를 스택으로 관리하고, 스트리밍 완료 시 어시스턴트 답변을 기록합니다.
- Tailwind 유틸 클래스로 모바일/데스크탑 대응 레이아웃을 구성했습니다.

---

## 🔌 Backend integration

환경변수 없이 기본값으로 `http://127.0.0.1:8000/api/ask`를 호출합니다.  
백엔드가 다른 호스트/포트에 있을 경우 `ApiService` 또는 Fetch 호출의 URL만 수정하면 됩니다.

SSE 처리 흐름 요약:
```tsx
const response = await fetch("/api/ask", {...});
const reader = response.body?.getReader();
const decoder = new TextDecoder("utf-8");

while (reader) {
  const { value, done } = await reader.read();
  if (done) break;
  const chunk = decoder.decode(value, { stream: true }).trim();
  // JSON 라인별 파싱 → answer / statusMessages 업데이트
}
```

각 이벤트 타입의 UI 렌더링은 다음과 같이 표현됩니다.
- `text` → 메인 답변 버블 (`whitespace-pre-wrap`)
- `status` → 회색 작은 상태 라벨
- `error` → 빨간 상태 라벨

---

## 🎨 UI notes

- 본문은 Tailwind `bg-gray-50` · `rounded-2xl` 을 활용한 ChatGPT 스타일.
- `react-markdown` + `remark-gfm` 으로 목록/표/링크 렌더링 지원.
- 스크롤은 `useRef` + `scrollIntoView` 로 스트리밍 중 자동 내려갑니다.
- IME 한글 입력 중 `Enter` 키 이벤트가 무시되도록 `SearchBar`에서 `onCompositionStart/End` 를 처리합니다.

---

## 🔍 Quality checklist

- ESLint + TypeScript 로 빌드 이전에 기본 품질 체크
- Vite 개발 서버에서 HMR 지원
- 프로덕션 빌드(`npm run build`) 는 타입 확인(`tsc -b`)을 포함

---

## 🤝 Backend pairing

| 항목          | 프론트엔드                        | 백엔드                                |
| ------------- | --------------------------------- | ------------------------------------- |
| API Host      | `http://127.0.0.1:8000` (기본)    | `uvicorn app.main:app --port 8000`    |
| 응답 포맷     | SSE (`data: {...}\n\n`)           | `ToolChunk.to_json()`                 |
| 인증/보안     | (없음)                            | `.env`에서 API Key 관리               |
| 배포          | `npm run build` → 정적 자산 배포   | Docker / Uvicorn / Reverse proxy      |

---

## 🧪 Troubleshooting

| 문제 | 확인사항 |
| ---- | -------- |
| CORS 오류 | 백엔드 `app/main.py` 의 `allow_origins` 목록에 프론트 URL 추가 |
| 스트림 중지 | 브라우저 콘솔에서 `Stream parse error` 로그 확인, 백엔드 로그와 비교 |
| Tailwind 적용 안됨 | `npm install` 후 `npm run dev` 로 HMR 확인, `postcss.config.js` 존재 확인 |

프론트엔드 관련 문의는 `/src/components/*` 의 상태 흐름을 기반으로 해결할 수 있습니다.  
필요 시 `npm run lint`로 컨벤션을 맞추고, 브라우저 devtools 의 Network 탭에서 SSE 패킷을 디버깅하세요.

### 1. 실시간 스트리밍
- GPT-4o 응답을 실시간으로 표시
- 타이핑 효과로 자연스러운 사용자 경험

### 2. 검색 모드
- **일반 검색**: GPT-4o 기반 일반적인 답변
- **법령 검색**: Qdrant RAG 기반 법령 특화 답변

### 3. 출처 표시
- Perplexity 스타일의 출처 카드
- 관련도 점수 표시
- 원문 링크 제공

### 4. 반응형 디자인
- 모바일/데스크톱 최적화
- TailwindCSS 기반 반응형 레이아웃

## 🛠️ 개발 가이드

### 컴포넌트 개발

```typescript
// 새 컴포넌트 생성
interface ComponentProps {
  title: string;
  onAction: () => void;
}

export const NewComponent: React.FC<ComponentProps> = ({ 
  title, 
  onAction 
}) => {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <button 
        onClick={onAction}
        className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
      >
        실행
      </button>
    </div>
  );
};
```

### 스타일링 가이드

TailwindCSS 클래스를 사용하여 일관된 디자인을 유지하세요:

```typescript
// 색상 팔레트
const colors = {
  primary: 'bg-blue-600 hover:bg-blue-700',
  secondary: 'bg-green-600 hover:bg-green-700',
  neutral: 'bg-gray-100 hover:bg-gray-200',
  text: {
    primary: 'text-gray-900',
    secondary: 'text-gray-600',
    muted: 'text-gray-500'
  }
};

// 레이아웃 패턴
const layouts = {
  card: 'bg-white rounded-lg shadow-sm border border-gray-200 p-6',
  button: 'px-4 py-2 rounded-lg font-medium transition-colors',
  input: 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'
};
```

### 상태 관리

현재는 React의 기본 상태 관리를 사용합니다:

```typescript
const [currentView, setCurrentView] = useState<'home' | 'result'>('home');
const [activeTab, setActiveTab] = useState<TabType>('answer');
const [isLoading, setIsLoading] = useState(false);
```

향후 복잡한 상태가 필요하면 Zustand나 Redux Toolkit을 고려할 수 있습니다.

## 🧪 테스트

### 컴포넌트 테스트

```bash
# 테스트 실행 (향후 추가 예정)
npm run test

# 테스트 커버리지
npm run test:coverage
```

### E2E 테스트

```bash
# Playwright E2E 테스트 (향후 추가 예정)
npm run test:e2e
```

## 📱 반응형 디자인

### 브레이크포인트

```css
/* TailwindCSS 기본 브레이크포인트 */
sm: 640px   /* 모바일 가로 */
md: 768px   /* 태블릿 */
lg: 1024px  /* 데스크톱 */
xl: 1280px  /* 대형 데스크톱 */
2xl: 1536px /* 초대형 */
```

### 모바일 최적화

```typescript
// 모바일 친화적 컴포넌트
<div className="px-4 sm:px-6 lg:px-8">
  <div className="max-w-2xl mx-auto">
    {/* 콘텐츠 */}
  </div>
</div>
```

## 🚀 배포

### Vercel (권장)

```bash
# Vercel CLI 설치
npm i -g vercel

# 배포
vercel

# 환경 변수 설정
vercel env add API_BASE_URL
```

### Netlify

```bash
# 빌드
npm run build

# Netlify에 dist 폴더 업로드
```

### Docker

```dockerfile
FROM node:18-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "preview"]
```

## 🔧 환경 설정

### 개발 환경

```bash
# .env.local 파일 생성
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=L.Ai
```

### 프로덕션 환경

```bash
# 환경 변수 설정
VITE_API_BASE_URL=https://api.lai.example.com
VITE_APP_TITLE=L.Ai
```

## 📊 성능 최적화

### 코드 분할

```typescript
// 동적 임포트로 코드 분할
const LazyComponent = React.lazy(() => import('./LazyComponent'));

// Suspense로 로딩 처리
<Suspense fallback={<div>Loading...</div>}>
  <LazyComponent />
</Suspense>
```

### 이미지 최적화

```typescript
// Vite의 이미지 최적화 활용
import logoUrl from '/src/assets/logo.png?url';
```

## 🐛 문제 해결

### 일반적인 문제

1. **API 연결 실패**
   - 백엔드 서버가 실행 중인지 확인
   - CORS 설정 확인
   - API_BASE_URL 설정 확인

2. **빌드 오류**
   - Node.js 버전 확인 (18+ 권장)
   - 의존성 재설치: `rm -rf node_modules && npm install`

3. **타입 오류**
   - TypeScript 설정 확인
   - 타입 정의 업데이트

### 개발자 도구

```bash
# 의존성 분석
npm run analyze

# 번들 크기 확인
npm run build -- --analyze
```

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.
