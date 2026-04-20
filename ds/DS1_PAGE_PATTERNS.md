# DS v1 Page Patterns — Informational Pages 01

> **Source**: DS-v7 `2NMKkf5U1AKDCkkUWqelFl` / Page `1686:419020` (❖ Informational pages 01)
> **총 78 프레임**: 19 페이지 유형 × Light/Dark × Mobile(375)/Desktop(1440)
> **생성일**: 2026-02-26

---

## 공통 레이아웃 구조 (Mobile 375px)

모든 페이지가 동일한 루트 구조를 따름:

```
Root Frame (375 × auto)
├── 🧩 Sidebar navigation (375×64)     ← 상단 네비게이션 바
└── 📁 Main (375 × auto)                ← 메인 콘텐츠 영역
    ├── 📁/🧩 Header section            ← 페이지 헤더 (타이틀 + 액션)
    ├── 📁 Section                       ← 콘텐츠 섹션 (1개 이상)
    └── 📁 Section                       ← 추가 섹션 (선택)
```

### 공통 컴포넌트
| 컴포넌트 | 역할 | 사용처 |
|----------|------|--------|
| Sidebar navigation | 상단 네비바 (로고 + 햄버거) | 전체 페이지 |
| Page header | 페이지 제목 + 설명 + 버튼 | 대부분 페이지 |
| Section header | 섹션 제목 + 부제목 | 복합 페이지 |
| Pagination | 페이지네이션 (← Page X of Y →) | 테이블 페이지 |
| Content divider | 수평 구분선 (1px) | 섹션 구분 |

---

## 카테고리 A: 테이블/데이터 페이지 (7개)

### A1. Trade History — 탭 + 카드 테이블
| 항목 | 값 |
|------|------|
| **ID** | `1781:509321` |
| **크기** | 375×1117 |
| **Header** | Page header (Back + Title + Description) |
| **Actions** | Export 버튼 + Add trade (Primary) |
| **탭** | Horizontal tabs (All trades / Buy / Sell) |
| **필터** | Search + Date picker + Sort 아이콘 |
| **테이블** | Card header + Table (Trade, Order amount) + Checkbox |
| **하단** | Pagination |

**레이아웃 패턴**:
```
Header section (375×200)
  ├── Page header (← Back / Trade history)
  ├── Actions: [Export] [+ Add trade]
  └── Horizontal tabs
Section (375×741)
  ├── Search bar (⌘K)
  ├── Date picker (Jan 10 – Jan 16)  +  Filter icon
  ├── Card header (All trades · 58 trades · ⋮)
  ├── Table header (☐ Trade | Order amount)
  ├── Table rows × N (☐ TSLA BUY / Tesla · $30,021.23)
  └── Pagination
```

### A2. Trade History — 버튼그룹 변형
| 항목 | 값 |
|------|------|
| **ID** | `1781:509811` |
| **크기** | 375×1092 |
| **차이점** | Export → "Download CSV", Button group 사용, 카드 헤더 없음 |

### A3. Files & Assets — 파일 업로드 + 테이블
| 항목 | 값 |
|------|------|
| **ID** | `1781:510625` |
| **크기** | 375×1224 |
| **특징** | File upload 드래그앤드롭 영역, 파일 타입 아이콘 (PDF/JPG/MP4/FIG/DOCX/AEP/MP3) |

**레이아웃 패턴**:
```
Header section (375×136)
  ├── Page header (Files and assets)
  └── Actions: [Share] [Invite team]
Section (375×912)
  ├── File upload zone (Click to upload or drag and drop)
  ├── Section header (Attached files)
  ├── Search + Filter
  ├── Button group (View all / Your files / Shared files)
  ├── Table header (☐ File name)
  └── Table rows (icon + filename + size)
```

### A4. Orders — 인보이스 테이블
| 항목 | 값 |
|------|------|
| **ID** | `1716:451412` |
| **크기** | 375×1042 |
| **특징** | 심플한 3컬럼 테이블 (Invoice, Date, Status), Status Badge (Paid/Refunded/Cancelled) |

**레이아웃 패턴**:
```
Header section (375×122)
  ├── Page header (← Back / Orders)
  └── Actions: [PDF] [CSV]
Section (375×744)
  ├── Search bar
  ├── Filters 버튼
  ├── Table header (☐ Invoice↓ | Date | Status)
  ├── Table rows × N (INV-3066 | Jan 6, 2025 | ✓Paid)
  └── Pagination
```

### A5. Orders + Billing — 복합 테이블
| 항목 | 값 |
|------|------|
| **ID** | `1716:451844` |
| **크기** | 375×2121 |
| **특징** | 2개 섹션 (Subscription orders + Billing/invoicing), Section header/label 사용 |

**레이아웃 패턴**:
```
Header section (375×129)
  └── Page header (Orders)
Section 1 (375×1026) — Subscription orders
  ├── Section header + Description
  ├── Section label (Order details)
  ├── Search bar
  ├── Table header (☐ Order↓ | Date | Customer)
  ├── Table rows × N (Avatar + #3066 | Jan 6)
  └── Pagination
Section 2 (375×758) — Billing and invoicing
  ├── Section header + Description + Link
  ├── Section label (Billing history)
  ├── Table header (☐ Invoice↓ | Date | Status)
  └── Table rows × N
```

### A6. Customers — 메트릭 카드 + 테이블
| 항목 | 값 |
|------|------|
| **ID** | `1716:453480` |
| **크기** | 375×1582 |
| **특징** | Metric 카드 3개 (Total/Members/Active) + 필터바 + 테이블 |

**레이아웃 패턴 (핵심 참고용)**:
```
Header section (375×86)
  ├── Page header (Customers)
  └── Horizontal tabs (Overview | Table | List view | Segment)
Section 1 — Metrics (375×550)
  ├── Metric item (Total customers: 2,420  ↗20%)
  ├── Metric item (Members: 1,210  ↗15%)
  └── Metric item (Active now: 316 + Avatar group)
Section 2 — Table (375×738)
  ├── Section header (Customers · ⋮)
  ├── Description text
  ├── Search bar
  ├── Filters 버튼
  ├── Table header (☐ Company↓ | Status)
  └── Table rows × N (Logo + Company + URL | ●Status Badge)
```

### A7. Customers — 필터 적용 + 메트릭
| 항목 | 값 |
|------|------|
| **ID** | `1716:454614` |
| **크기** | 375×1480 |
| **차이점** | Metric 카드가 컴팩트, "More filters" + Filters applied 뱃지 (All time × / US, AU, +4 ×) |
| **테이블 추가 컬럼** | Company + About |

---

## 카테고리 B: 캘린더 (3개)

### B1–B3. Calendar 뷰
| 항목 | B1 (`8044:116651`) | B2 (`8044:127066`) | B3 (`8044:129175`) |
|------|------|------|------|
| **크기** | 375×1266 | 375×1266 | 375×1266 |
| **공통 구조** | 동일 | 동일 | 동일 |
| **변형** | 이벤트 표시 차이 | 날짜 선택 차이 | 뷰 옵션 차이 |

**공통 레이아웃 패턴**:
```
Header section (375×178)
  ├── Page header (← Back / Calendar)
  ├── Search bar
  └── Horizontal tabs (All events | Shared | Public | Archived)
Section (375×912)
  ├── Month/Week label (January 2025 · Week 1)
  ├── Date range (Jan 1 – Jan 31, 2025)
  ├── Actions: [Month view ▾] [+ Add event] [🔍]
  ├── Calendar nav: [←] Today [→]
  ├── Calendar grid (7×5, colored dots per event)
  ├── Selected day header (Friday Jan 10, 2025)
  └── Event list (name + time)
```

---

## 카테고리 C: 메시징 (2개)

### C1. Messaging — 채팅 리스트
| 항목 | 값 |
|------|------|
| **ID** | `1706:438996` |
| **크기** | 375×1440 |
| **특징** | 대화 목록 + 프로필 헤더 + 메시지 버블 |

### C2. Messaging — 1:1 대화 상세
| 항목 | 값 |
|------|------|
| **ID** | `1706:440594` |
| **크기** | 375×1440 |

**레이아웃 패턴**:
```
Section (375×1376)
  ├── Header (커버 이미지 + 아바타 + 이름 + 온라인 표시)
  ├── Actions (✉ 📞 📹 + ⋮ Dropdown)
  ├── Content divider
  ├── Message bubbles (반복):
  │   ├── 상대방: Avatar + 이름 + 시간 + 말풍선(왼쪽)
  │   ├── 나: 말풍선(오른쪽) + 시간 + ✓✓
  │   ├── 이미지 메시지 (썸네일 + URL)
  │   ├── 파일 메시지 (PDF icon + 파일명 + 크기)
  │   ├── 음성 메시지 (▶ 파형 + 시간)
  │   └── 리액션 (❤️ 👌 카운트)
  ├── 날짜 구분 (Today)
  └── Message input (📎 😊 | Message | 🎤 Send)
```

---

## 카테고리 D: 프로젝트/콘텐츠 상세 (4개)

### D1. Project Overview — 버티컬 탭
| 항목 | 값 |
|------|------|
| **ID** | `1716:455171` |
| **크기** | 375×2946 |
| **특징** | Vertical tabs (사이드) + Section header + 긴 텍스트 콘텐츠 + 이미지 |

**레이아웃 패턴**:
```
Header section (375×122)
  └── Page header (← Back / Marketing site redesign)
Vertical tabs section (375×44)
  └── Tab bar (Messages 548 | Overview | Project | ...)
Content section (375×2572)
  ├── Horizontal tabs (Project brief | Goals | Timeline | ...)
  ├── Section: About the company (제목 + 단락 + 이미지)
  ├── Section: Target audience (제목 + 단락 + 이미지)
  ├── Section: What does success look like? (제목 + 단락)
  └── Read more 버튼
```

### D2. Project Overview — 수평 탭
| 항목 | 값 |
|------|------|
| **ID** | `1716:455519` |
| **크기** | 375×2847 |
| **차이점** | Vertical tabs 대신 Horizontal tabs만 사용, 레이아웃 유사 |

### D3. Sources — API/코드 뷰어
| 항목 | 값 |
|------|------|
| **ID** | `1716:455917` |
| **크기** | 375×1941 |
| **특징** | Table + Code snippet (구문 강조), Horizontal tabs (Overview/Visual tagger/Debugger) |

**레이아웃 패턴**:
```
Header section (375×174)
  ├── Page header (← Back / Sources)
  ├── Actions: [Import] [Share]
  └── Horizontal tabs (Overview | Visual tagger | Debugger)
Section 1 — Sources table (375×788)
  ├── Section header (Sources)
  ├── Search bar
  ├── Sub-tabs (Live | Pause)
  ├── Table header (Action | Status | Date)
  ├── Table rows (Signup complete · ●Track · Jan 6)
  └── Pagination
Section 2 — Code (375×771)
  ├── Section header (Source deleted)
  ├── Tab bar (Pretty | Raw | Violations)
  └── Code snippet (줄번호 + 구문 강조 코드 블록)
```

### D4. Content Detail — 텍스트 에디터
| 항목 | 값 |
|------|------|
| **ID** | `9313:552229` |
| **크기** | 375×3164 |
| **특징** | 텍스트 에디터 + 파일 첨부 + 사이드 패널 (작가 프로필 + 통계) |

**레이아웃 패턴**:
```
Header section (375×148)
  ├── Page header (← Back / The Outermost House)
  └── Meta: Author · Status (Save as draft | Publish changes)
Section 1 — Featured excerpt (375×1174)
  ├── Section header (Featured excerpt)
  ├── Text editor (리치 텍스트 편집 영역)
  └── Attach files (파일 업로드 + 파일 목록)
Section 2 — Side panel (375×462)
  ├── Author card (아바타 + 이름 + 통계)
  ├── Statistics (👁 806 · ❤️ 12,067)
  ├── Actions: [Copy link] [Author page]
  └── About (작가 소개 텍스트)
Section 3 — Notable works (375×1140)
  ├── Section header (Notable works)
  └── Book cards × N (표지 + 제목 + 저자 + 연도)
```

---

## 카테고리 E: 지도 검색 (1개)

### E1. Map Search — 지도 + 리스팅
| 항목 | 값 |
|------|------|
| **ID** | `1716:456532` |
| **크기** | 375×2657 |

**레이아웃 패턴**:
```
Header section (375×129)
  ├── Page header (232 stays in Melbourne)
  └── Actions: [Share] [Save search]
Map section (375×360)
  └── Google maps mockup + Location markers
Filter section (375×96)
  ├── Search bar
  ├── Filter badges (2 filters applied)
  └── Sort tabs (Sort by date | Sort by price) + Grid/List 토글
Results section (375×1832)
  ├── Listing card × N:
  │   ├── Image (숙소 사진 + "Rare find" 뱃지)
  │   ├── Price ($540 AUD total)
  │   ├── Type + Title
  │   ├── Rating (★★★★★ 4.9 · 202 reviews)
  │   └── Location (📍 Collingwood VIC)
  └── Pagination
```

---

## 카테고리 F: 유저 프로필 (2개)

### F1. User Profile A — 포트폴리오
| 항목 | 값 |
|------|------|
| **ID** | `1716:458324` |
| **크기** | 375×3192 |

**레이아웃 패턴**:
```
Page header (375×336)
  ├── 커버 이미지 (그라데이션)
  ├── Avatar (큰 원형)
  └── 이름 + Bio + [View portfolio] [Follow]
Section 1 — Details (375×1586)
  ├── Location / Website / Portfolio / Email (Label + Link)
  ├── Divider
  ├── About me (긴 텍스트 + Read more)
  ├── Divider
  └── Experience (반복):
      ├── 회사 로고 (원형)
      ├── 직책 + 회사명
      ├── 기간
      └── [View project] 링크
Section 2 — Projects (375×1094)
  ├── Section header (Projects · View all)
  └── 프로젝트 카드 그리드 (이미지 + 제목)
```

### F2. User Profile B — 이력 상세
| 항목 | 값 |
|------|------|
| **ID** | `1716:457249` |
| **크기** | 375×3156 |
| **차이점** | Experience 섹션 + 스킬 태그, Job card mobile 컴포넌트 사용 |

---

## 디자인 생성 시 적용 가이드

### 레이아웃 규칙 요약

| 규칙 | 값 |
|------|------|
| **Mobile 너비** | 375px |
| **Sidebar nav 높이** | 64px |
| **Header section 높이** | 86~200px (콘텐츠에 따라) |
| **섹션 간 구분** | Content divider (1px) 또는 여백 |
| **테이블 행 높이** | ~56–64px (체크박스 포함) |
| **Metric 카드** | Metric item 컴포넌트, 세로 스택 |
| **Pagination** | 하단 고정, ← Page X of Y → |

### 페이지 유형별 컴포넌트 조합

```
데이터 테이블 =  Page header
              + [Horizontal tabs]
              + [Metric items]
              + Search + [Filters] + [Date picker]
              + Table (header + rows)
              + Pagination

캘린더       =  Page header
              + Search
              + Horizontal tabs
              + Calendar 컴포넌트

메시징       =  Card header (대화 상대)
              + Content divider
              + Message bubbles (반복)
              + Message input

콘텐츠 상세  =  Page header (← Back + Title)
              + [Horizontal/Vertical tabs]
              + Section (제목 + 텍스트 + 이미지)
              + [Code snippet]
              + [File upload]

지도 검색    =  Page header
              + Map (Google maps mockup)
              + Search + Filters + Sort
              + Listing cards (반복)
              + Pagination

유저 프로필  =  Page header (커버 + 아바타 + Bio)
              + Details (Label+Value 반복)
              + About (텍스트)
              + Experience (타임라인)
              + Projects (카드 그리드)
```

### Desktop 변형 규칙 (1440px)
- Mobile과 1:1 대응 (같은 x 위치에 Desktop 프레임 존재)
- Desktop은 Sidebar navigation이 좌측 패널로 변경
- 콘텐츠 영역은 중앙 정렬 또는 Side panel 추가
- 테이블은 더 많은 컬럼 표시
