// Stages tab — 추천 스테이지 피드

const KRW = (n) => n.toLocaleString('ko-KR') + '원';
const KRWMan = (n) => Math.round(n / 10000).toLocaleString('ko-KR') + '만원';

// ========== 카테고리 칩 ==========
const CategoryChips = ({ active, onChange }) => {
  const cats = [
    { id: 'recommend', label: '추천' },
    { id: 'direct', label: '직접' },
    { id: 'new', label: '신규' },
    { id: 'popular', label: '인기' },
    { id: 'ending', label: '마감임박' },
  ];
  return (
    <div style={{
      display: 'flex', gap: 6, padding: '12px 20px 6px',
      overflowX: 'auto', background: '#fff',
      scrollbarWidth: 'none',
    }}>
      {cats.map(c => (
        <button key={c.id} onClick={() => onChange(c.id)} style={{
          padding: '8px 16px', borderRadius: 999, flexShrink: 0,
          border: active === c.id ? '1px solid var(--brand-600)' : '1px solid var(--border-primary)',
          background: active === c.id ? 'var(--brand-50)' : '#fff',
          color: active === c.id ? 'var(--brand-700)' : 'var(--fg3)',
          fontSize: 13, fontWeight: active === c.id ? 700 : 500,
          fontFamily: 'inherit', cursor: 'pointer',
          letterSpacing: '-0.01em', whiteSpace: 'nowrap',
        }}>{c.label}</button>
      ))}
    </div>
  );
};

// ========== 필터 카드 (± 스텝퍼) ==========
const StepperRow = ({ label, value, onDec, onInc, unit }) => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '10px 0', borderBottom: '1px solid var(--gray-100)',
  }}>
    <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--fg2)' }}>{label}</div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <button onClick={onDec} style={stepBtn}>
        <Icon name="minus" size={16} color="var(--fg2)" strokeWidth={2.2}/>
      </button>
      <div style={{
        fontSize: 14, fontWeight: 700, color: 'var(--fg1)',
        letterSpacing: '-0.01em', minWidth: 90, textAlign: 'center',
      }}>{value}{unit && <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg3)', marginLeft: 2 }}>{unit}</span>}</div>
      <button onClick={onInc} style={stepBtn}>
        <Icon name="plus" size={16} color="var(--fg2)" strokeWidth={2.2}/>
      </button>
    </div>
  </div>
);
const stepBtn = {
  width: 26, height: 26, borderRadius: 999,
  border: '1px solid var(--border-primary)', background: '#fff',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', padding: 0,
};

const FilterCard = ({ filters, setFilters }) => {
  const step = (key, delta, min, max) => () =>
    setFilters(f => ({ ...f, [key]: Math.max(min, Math.min(max, f[key] + delta)) }));
  return (
    <div style={{
      margin: '8px 20px 16px', padding: '6px 16px',
      background: 'var(--gray-50)', borderRadius: 14,
    }}>
      <StepperRow label="월 납입 금액" value={filters.monthly} unit="만원"
        onDec={step('monthly', -10, 10, 130)} onInc={step('monthly', 10, 10, 130)}/>
      <StepperRow label="목돈 필요 시점" value={filters.when} unit="개월 뒤"
        onDec={step('when', -1, 5, 13)} onInc={step('when', 1, 5, 13)}/>
      <div style={{ ...stepperRowLast }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--fg2)' }}>납입 기간</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button onClick={step('duration', -1, 5, 13)} style={stepBtn}>
            <Icon name="minus" size={16} color="var(--fg2)" strokeWidth={2.2}/>
          </button>
          <div style={{
            fontSize: 14, fontWeight: 700, color: 'var(--fg1)',
            letterSpacing: '-0.01em', minWidth: 90, textAlign: 'center',
          }}>{filters.duration}<span style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg3)', marginLeft: 2 }}>개월 내</span></div>
          <button onClick={step('duration', 1, 5, 13)} style={stepBtn}>
            <Icon name="plus" size={16} color="var(--fg2)" strokeWidth={2.2}/>
          </button>
        </div>
      </div>
    </div>
  );
};
const stepperRowLast = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '10px 0',
};

// ========== 친구 메이커 아바타 행 ==========
const MakerAvatars = () => {
  const makers = [
    { name: '비비빔밥파괴자', lv: 2202, color: '#8b5cf6' },
    { name: '비비빔밥파괴자', lv: 35, color: '#ec4899' },
    { name: '비비빔밥파괴자', lv: 492, color: '#f59e0b' },
    { name: '비비빔밥파괴자', lv: 77, color: '#10b981' },
  ];
  return (
    <div style={{
      display: 'flex', gap: 16, padding: '4px 20px 18px',
      overflowX: 'auto', background: '#fff',
      scrollbarWidth: 'none',
    }}>
      {/* + 추가 버튼 */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        <div style={{
          width: 52, height: 52, borderRadius: 999,
          border: '1.5px dashed var(--border-primary)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: '#fff',
        }}>
          <Icon name="plus" size={22} color="var(--fg4)" strokeWidth={1.8}/>
        </div>
        <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--fg4)' }}>추가</div>
      </div>
      {/* makers */}
      {makers.map((m, i) => (
        <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <div style={{ position: 'relative' }}>
            <div style={{
              width: 52, height: 52, borderRadius: 999,
              background: `linear-gradient(135deg, ${m.color} 0%, ${m.color}cc 100%)`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: 20, fontWeight: 700,
              boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
            }}>
              {i === 0 && '🥗'}
              {i === 1 && '🌸'}
              {i === 2 && '🎯'}
              {i === 3 && '🔥'}
            </div>
            {i === 1 && (
              <div style={{
                position: 'absolute', bottom: -2, right: -2,
                width: 18, height: 18, borderRadius: 999,
                background: 'var(--brand-600)', border: '2px solid #fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 9, color: '#fff', fontWeight: 700,
              }}>👑</div>
            )}
          </div>
          <div style={{ textAlign: 'center', maxWidth: 60 }}>
            <div style={{
              fontSize: 10, fontWeight: 600, color: 'var(--fg2)',
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              letterSpacing: '-0.02em',
            }}>{m.name}</div>
            <div style={{ fontSize: 9, fontWeight: 500, color: 'var(--fg4)' }}>(lv.{m.lv})</div>
          </div>
        </div>
      ))}
    </div>
  );
};

// ========== 스테이지 카드 ==========
// 타임라인 바 레이아웃
const TimelineBarLayout = ({ stage }) => {
  const cells = Array.from({ length: stage.months }, (_, i) => i + 1);
  const payoutAt = stage.payoutAt; // 어느 회차에 목돈 수령
  return (
    <>
      <div style={{
        fontSize: 13, fontWeight: 600, color: 'var(--fg2)',
        letterSpacing: '-0.02em', marginBottom: 10, textAlign: 'center',
      }}>
        <span style={{ color: 'var(--brand-600)' }}>→</span> 월 <span style={{ color: 'var(--fg1)', fontWeight: 700 }}>{KRW(stage.monthly)}</span> 씩 <span style={{ color: 'var(--fg1)', fontWeight: 700 }}>{stage.months}개월</span> 모으기
      </div>
      <div style={{ position: 'relative', padding: '4px 2px 2px' }}>
        <div style={{
          display: 'grid', gridTemplateColumns: `repeat(${stage.months}, 1fr)`, gap: 2,
        }}>
          {cells.map(n => (
            <div key={n} style={{
              height: 22, borderRadius: 4,
              background: n === payoutAt ? 'var(--brand-600)' : 'var(--brand-100)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 9, fontWeight: 700,
              color: n === payoutAt ? '#fff' : 'var(--brand-700)',
            }}>{n}</div>
          ))}
        </div>
        {/* 수령 화살표 */}
        <div style={{
          position: 'absolute', left: `${((payoutAt - 0.5) / stage.months) * 100}%`,
          top: -2, transform: 'translateX(-50%)',
          fontSize: 10, color: 'var(--brand-600)',
        }}>↓</div>
      </div>
      <div style={{
        fontSize: 12, fontWeight: 600, color: 'var(--fg2)', marginTop: 6,
        textAlign: 'center', letterSpacing: '-0.01em',
      }}>
        <span style={{ color: 'var(--brand-600)', fontWeight: 700 }}>{stage.payoutAt}차</span> 납입 후 목돈 수령
      </div>
    </>
  );
};

// 링 게이지 레이아웃
const RingGaugeLayout = ({ stage }) => {
  const pct = (stage.payoutAt / stage.months) * 100;
  const r = 36, c = 2 * Math.PI * r;
  return (
    <>
      <div style={{
        fontSize: 13, fontWeight: 600, color: 'var(--fg2)',
        letterSpacing: '-0.02em', marginBottom: 12, textAlign: 'center',
      }}>
        <span style={{ color: 'var(--brand-600)' }}>→</span> 월 {KRW(stage.monthly)} 씩 {stage.months}개월 모으기
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, justifyContent: 'center' }}>
        <svg width="90" height="90" viewBox="0 0 90 90">
          <circle cx="45" cy="45" r={r} fill="none" stroke="var(--brand-100)" strokeWidth="8"/>
          <circle cx="45" cy="45" r={r} fill="none" stroke="var(--brand-600)" strokeWidth="8"
            strokeDasharray={c} strokeDashoffset={c - (c * pct / 100)}
            transform="rotate(-90 45 45)" strokeLinecap="round"/>
          <text x="45" y="42" textAnchor="middle" fontSize="18" fontWeight="700" fill="var(--fg1)"
            fontFamily="Pretendard">{stage.payoutAt}</text>
          <text x="45" y="56" textAnchor="middle" fontSize="9" fontWeight="500" fill="var(--fg4)"
            fontFamily="Pretendard">/ {stage.months}회차</text>
        </svg>
        <div style={{ fontSize: 12, color: 'var(--fg2)', lineHeight: 1.6 }}>
          <div><span style={{ color: 'var(--brand-600)', fontWeight: 700 }}>{stage.payoutAt}차</span> 납입 후</div>
          <div style={{ fontWeight: 700, color: 'var(--fg1)', fontSize: 14 }}>목돈 수령</div>
        </div>
      </div>
    </>
  );
};

// 숫자 중심 레이아웃
const NumberHeroLayout = ({ stage }) => (
  <>
    <div style={{
      fontSize: 11, fontWeight: 600, color: 'var(--brand-600)',
      letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: 4,
    }}>{stage.payoutAt}차 납입 후 목돈 수령</div>
    <div style={{
      fontSize: 22, fontWeight: 800, color: 'var(--fg1)',
      letterSpacing: '-0.03em', lineHeight: 1.1,
    }}>
      월 {KRW(stage.monthly)}
    </div>
    <div style={{
      fontSize: 13, fontWeight: 500, color: 'var(--fg3)',
      letterSpacing: '-0.01em', marginTop: 2,
    }}>
      {stage.months}개월 모으기 플랜
    </div>
    {/* 얇은 프로그레스 */}
    <div style={{
      marginTop: 10, height: 4, borderRadius: 99,
      background: 'var(--brand-100)', position: 'relative', overflow: 'hidden',
    }}>
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0,
        width: `${(stage.payoutAt / stage.months) * 100}%`,
        background: 'var(--brand-600)', borderRadius: 99,
      }}/>
    </div>
  </>
);

const StageCard = ({ stage, layout, onTap }) => {
  return (
    <div onClick={onTap} style={{
      margin: '0 20px 10px', padding: '16px 16px 14px',
      background: '#fff', borderRadius: 14,
      border: '1px solid var(--border-secondary)',
      boxShadow: '0 1px 2px rgba(10,13,18,0.04)',
      cursor: 'pointer',
    }}>
      {layout === 'timeline' && <TimelineBarLayout stage={stage}/>}
      {layout === 'ring' && <RingGaugeLayout stage={stage}/>}
      {layout === 'number' && <NumberHeroLayout stage={stage}/>}

      {/* 금액 요약 */}
      <div style={{
        marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--gray-100)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg3)' }}>
            목돈 <span style={{ fontSize: 11, color: 'var(--fg4)' }}>({stage.payoutAt}회차 납입 후 수령)</span>
          </span>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--fg1)', letterSpacing: '-0.01em' }}>
            {KRW(stage.payout)}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg3)' }}>총 이자</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--error-600)', letterSpacing: '-0.01em' }}>
            {KRW(stage.interest)}
          </span>
        </div>
      </div>

      {/* 추가 혜택 */}
      <div style={{
        marginTop: 10, padding: '8px 10px', borderRadius: 8,
        background: 'var(--gray-50)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--fg3)' }}>
          추가 혜택 (스테이지 시작자 지급)
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={benefitBadge('#7a5af8', 'var(--brand-50)')}>
            <span style={{ fontSize: 9, opacity: 0.7 }}>◆</span> {stage.points}P
          </span>
          <span style={benefitBadge('var(--fg3)', '#fff', '1px solid var(--border-primary)')}>
            {stage.fee}원
          </span>
        </div>
      </div>
    </div>
  );
};
const benefitBadge = (color, bg, border) => ({
  display: 'inline-flex', alignItems: 'center', gap: 3,
  padding: '3px 8px', borderRadius: 999,
  background: bg, color, border: border || 'none',
  fontSize: 11, fontWeight: 700, letterSpacing: '-0.01em',
  whiteSpace: 'nowrap',
});

// ========== FAB ==========
const CreateStageFAB = () => (
  <button style={{
    position: 'absolute', bottom: 88, right: 18, zIndex: 40,
    width: 52, height: 52, borderRadius: 999,
    background: 'var(--brand-600)',
    border: '3px solid #fff',
    boxShadow: '0 6px 16px rgba(105, 56, 239, 0.35), 0 2px 4px rgba(0,0,0,0.08)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', padding: 0,
  }}>
    <Icon name="plus" size={24} color="#fff" strokeWidth={2.4}/>
  </button>
);

// ========== 푸터 ==========
const StagesFooter = () => (
  <div style={{
    margin: '10px 20px 8px', padding: '18px 0 16px',
    borderTop: '1px solid var(--gray-100)',
    fontSize: 10, color: 'var(--fg4)', lineHeight: 1.7, letterSpacing: '-0.01em',
  }}>
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px 12px',
      marginBottom: 14, fontSize: 11, fontWeight: 500, color: 'var(--fg3)',
    }}>
      <span>이용약관</span>
      <span>스테이지이용약관</span>
      <span>서비스운영정책</span>
      <span>개인정보처리방침</span>
      <span>쇼핑이용약관</span>
      <span></span>
    </div>
    <div style={{ color: 'var(--fg4)', marginBottom: 6 }}>
      (주)티웨이브 역삼3점 <span style={{ marginLeft: 10 }}>사업자등록번호 : 291-85-01499</span>
    </div>
    <div style={{ color: 'var(--fg4)', marginBottom: 6 }}>
      대표 : 서재준 <span style={{ marginLeft: 10 }}>통신판매업신고 : 2021-서울강남-05837</span>
    </div>
    <div style={{ color: 'var(--fg4)', marginBottom: 12 }}>
      (주)티웨이브 역삼지점은 통신판매중개자로 거래 당사자가 아니므로 판매자가 등록한 상품정보 및 거래 등에 대해 책임을 지지 않습니다. 단, (주)티웨이브 역삼지점이 판매자로 등록 판매한 상품은 판매자로서 책임을 부담합니다.
    </div>
    <div style={{ color: 'var(--fg4)' }}>
      Copyright © TWAVE. All Rights Reserved.
    </div>
  </div>
);

// 샘플 데이터
const STAGE_POOL = [
  { id: 1, monthly: 105120, months: 13, payoutAt: 1, payout: 1092200, interest: -129100, points: 500, fee: 0 },
  { id: 2, monthly: 200000, months: 12, payoutAt: 3, payout: 2400000, interest: -168500, points: 1200, fee: 0 },
  { id: 3, monthly: 83000, months: 10, payoutAt: 2, payout: 830000, interest: -64200, points: 300, fee: 0 },
  { id: 4, monthly: 150000, months: 13, payoutAt: 6, payout: 1950000, interest: -210000, points: 2000, fee: 0 },
  { id: 5, monthly: 50000, months: 6, payoutAt: 1, payout: 300000, interest: -28400, points: 150, fee: 0 },
  { id: 6, monthly: 300000, months: 12, payoutAt: 4, payout: 3600000, interest: -320000, points: 1500, fee: 0 },
];

Object.assign(window, {
  CategoryChips, FilterCard, MakerAvatars,
  StageCard, CreateStageFAB, StagesFooter, STAGE_POOL,
});
