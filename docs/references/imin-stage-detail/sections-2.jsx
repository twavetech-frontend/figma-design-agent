// Stage Detail — 참여자 타임라인 뷰

const STAGE_INFO = {
  title: '스테이지 제목',
  startLabel: '모두 참여시 내일 오전 10시 시작',
  totalRounds: 13,
  amount: 10000000,
  joined: 5,
  max: 5,
};

const PARTICIPANTS = [
  { id: 1, idx: 1, type: 'invite', name: '스위스뱅크', lv: 1412, desc: '스테이지를 함께 1회 했던 사용자', action: '팔로우', actionState: 'default' },
  { id: 2, idx: 2, type: 'invite', name: '가나다라마바사', lv: 1435, desc: null, action: '팔로우 중', actionState: 'muted' },
  { id: 3, idx: 3, type: 'plan', title: '월 100,000원 * 13개월 납입', desc: '3회차 납입 후 10,000,000원 수령 (+0원)' },
  { id: 4, idx: 4, type: 'plan', title: '월 100,000원 * 13개월 납입', desc: '4회차 납입 후 약정금 수령 (+100,000원)', emphasize: true },
  { id: 5, idx: 5, type: 'invite', name: '스위스은행', lv: 38, desc: null, action: '나가기', actionState: 'exit' },
];

// 상세 탭
const StageDetailTabs = ({ active, onChange, style = 'pill' }) => {
  const tabs = [
    { id: 'participants', label: '참여자' },
    { id: 'rate', label: '이율 내역' },
    { id: 'progress', label: '진행 내역' },
    { id: 'chat', label: '채팅' },
  ];
  if (style === 'underline') {
    return (
      <div style={{ display: 'flex', padding: '0 20px', background: '#fff',
        borderBottom: '1px solid var(--gray-100)' }}>
        {tabs.map(t => {
          const on = active === t.id;
          return (
            <button key={t.id} onClick={() => onChange(t.id)} style={{
              flex: 1, padding: '14px 0', border: 'none', background: 'transparent',
              fontSize: 13, fontWeight: on ? 700 : 500,
              color: on ? 'var(--brand-600)' : 'var(--fg3)',
              fontFamily: 'inherit', cursor: 'pointer', letterSpacing: '-0.01em',
              borderBottom: on ? '2px solid var(--brand-600)' : '2px solid transparent',
              marginBottom: -1,
            }}>{t.label}</button>
          );
        })}
      </div>
    );
  }
  return (
    <div style={{ padding: '12px 20px 12px', background: '#fff' }}>
      <div style={{
        display: 'flex', background: 'var(--gray-100)',
        borderRadius: 10, padding: 3,
      }}>
        {tabs.map(t => {
          const on = active === t.id;
          return (
            <button key={t.id} onClick={() => onChange(t.id)} style={{
              flex: 1, padding: '8px 4px', borderRadius: 7, border: 'none',
              background: on ? '#fff' : 'transparent',
              color: on ? 'var(--fg1)' : 'var(--fg3)',
              fontSize: 12, fontWeight: on ? 700 : 500,
              fontFamily: 'inherit', cursor: 'pointer',
              letterSpacing: '-0.02em', whiteSpace: 'nowrap',
              boxShadow: on ? '0 1px 3px rgba(0,0,0,0.08), 0 1px 1px rgba(0,0,0,0.04)' : 'none',
              transition: 'all 0.15s ease-in-out',
            }}>{t.label}</button>
          );
        })}
      </div>
    </div>
  );
};

// 요약 카드
const StageSummaryCard = () => (
  <div style={{
    margin: '8px 20px 0', padding: '18px 20px',
    background: '#fff', borderRadius: 14,
    border: '1px solid var(--border-secondary)',
    boxShadow: '0 1px 2px rgba(10,13,18,0.04)',
  }}>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
      <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--fg1)', letterSpacing: '-0.02em' }}>
        {STAGE_INFO.title}
      </div>
      <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--fg3)', letterSpacing: '-0.01em' }}>
        {STAGE_INFO.startLabel}
      </div>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr 1fr', gap: 12 }}>
      <SummaryItem label="총 납입수" value={`${STAGE_INFO.totalRounds}회`}/>
      <SummaryItem label="약정금" value={STAGE_INFO.amount.toLocaleString('ko-KR') + '원'}/>
      <SummaryItem label="인원" value={`${STAGE_INFO.joined} / ${STAGE_INFO.max}명`}/>
    </div>
  </div>
);
const SummaryItem = ({ label, value }) => (
  <div>
    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg3)',
      letterSpacing: '-0.01em', marginBottom: 4 }}>{label}</div>
    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--fg1)',
      letterSpacing: '-0.02em' }}>{value}</div>
  </div>
);

// 타임라인 노드 (비주얼 스타일 분기)
const TimelineNode = ({ p, visual, emphasize }) => {
  const size = 36;
  const baseStyle = {
    width: size, height: size, borderRadius: 999,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0, position: 'relative', zIndex: 2,
    fontSize: 13, fontWeight: 700,
    background: '#fff', color: 'var(--fg2)',
    border: '1.5px solid var(--border-primary)',
    letterSpacing: '-0.02em',
  };
  if (visual === 'number') {
    return (
      <div style={{
        ...baseStyle,
        background: emphasize ? 'var(--brand-600)' : '#fff',
        color: emphasize ? '#fff' : 'var(--fg2)',
        border: emphasize ? '1.5px solid var(--brand-600)' : '1.5px solid var(--border-primary)',
      }}>{p.idx}</div>
    );
  }
  if (visual === 'avatar') {
    // plan 행은 아이콘, invite 행은 이니셜/이모지
    if (p.type === 'plan') {
      return (
        <div style={{
          ...baseStyle, background: emphasize ? 'var(--brand-600)' : 'var(--brand-100)',
          border: 'none', color: emphasize ? '#fff' : 'var(--brand-700)',
        }}>
          <Icon name="credit-card" size={18} color={emphasize ? '#fff' : 'var(--brand-700)'}/>
        </div>
      );
    }
    const palettes = ['#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6'];
    const color = palettes[p.id % palettes.length];
    const initial = p.name ? p.name[0] : '•';
    return (
      <div style={{
        ...baseStyle,
        background: `linear-gradient(135deg, ${color} 0%, ${color}cc 100%)`,
        border: 'none', color: '#fff',
      }}>{initial}</div>
    );
  }
  // stage (단계 목표) — 진행 도트
  return (
    <div style={{
      ...baseStyle,
      background: emphasize ? 'var(--brand-600)' : '#fff',
      border: emphasize ? '1.5px solid var(--brand-600)' : '1.5px solid var(--border-primary)',
    }}>
      <div style={{
        width: 10, height: 10, borderRadius: 999,
        background: emphasize ? '#fff' : 'var(--brand-600)',
      }}/>
    </div>
  );
};

// 타임라인 행
const TimelineRow = ({ p, isLast, visual, density, onTap }) => {
  const padY = density === 'tight' ? 6 : 10;
  const emphasize = p.emphasize;
  const tappable = p.type === 'plan';
  const actionMap = {
    default: { bg: 'var(--brand-600)', fg: '#fff', border: 'none' },
    muted:   { bg: 'transparent', fg: 'var(--fg4)', border: 'none' },
    exit:    { bg: '#fff', fg: 'var(--fg2)', border: '1px solid var(--border-primary)' },
  };
  return (
    <div onClick={tappable ? () => onTap && onTap(p) : undefined} style={{
      display: 'flex', gap: 14, paddingBottom: padY, paddingTop: padY,
      position: 'relative', alignItems: 'stretch',
      cursor: tappable ? 'pointer' : 'default',
    }}>
      {/* left rail */}
      <div style={{ position: 'relative', width: 36, flexShrink: 0, display: 'flex', justifyContent: 'center' }}>
        {!isLast && (
          <div style={{
            position: 'absolute', top: 0, bottom: -padY * 2, left: '50%',
            width: 2, background: 'var(--gray-200)', transform: 'translateX(-50%)', zIndex: 1,
          }}/>
        )}
        <div style={{ paddingTop: density === 'tight' ? 2 : 6 }}>
          <TimelineNode p={p} visual={visual} emphasize={emphasize}/>
        </div>
      </div>
      {/* card */}
      <div style={{
        flex: 1, minWidth: 0,
        padding: density === 'tight' ? '10px 14px' : '14px 16px',
        background: emphasize ? 'var(--brand-600)' : '#fff',
        borderRadius: 12,
        border: emphasize ? 'none' : '1px solid var(--border-secondary)',
        boxShadow: emphasize ? '0 4px 12px rgba(105,56,239,0.25)' : '0 1px 2px rgba(10,13,18,0.03)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {p.type === 'invite' ? (
            <>
              <div style={{
                fontSize: 14, fontWeight: 700,
                color: emphasize ? '#fff' : 'var(--fg1)',
                letterSpacing: '-0.02em',
              }}>
                {p.name} <span style={{ fontWeight: 500, color: emphasize ? 'rgba(255,255,255,0.7)' : 'var(--fg4)', fontSize: 12 }}>(lv.{p.lv.toLocaleString()})</span>
              </div>
              {p.desc && (
                <div style={{
                  fontSize: 12, fontWeight: 500, marginTop: 2,
                  color: emphasize ? 'rgba(255,255,255,0.85)' : 'var(--fg3)',
                  letterSpacing: '-0.01em',
                }}>{p.desc}</div>
              )}
            </>
          ) : (
            <>
              <div style={{
                fontSize: 14, fontWeight: 700,
                color: emphasize ? '#fff' : 'var(--fg1)',
                letterSpacing: '-0.02em',
              }}>{p.title}</div>
              <div style={{
                fontSize: 12, fontWeight: 500, marginTop: 2,
                color: emphasize ? 'rgba(255,255,255,0.85)' : 'var(--fg3)',
                letterSpacing: '-0.01em',
              }}>{p.desc}</div>
            </>
          )}
        </div>
        {p.action && (
          <button style={{
            padding: '6px 14px', borderRadius: 999,
            background: p.actionState === 'muted' && emphasize ? 'rgba(255,255,255,0.2)' : actionMap[p.actionState].bg,
            color: p.actionState === 'muted' && emphasize ? '#fff' : actionMap[p.actionState].fg,
            border: actionMap[p.actionState].border,
            fontSize: 12, fontWeight: 600, cursor: 'pointer',
            fontFamily: 'inherit', flexShrink: 0, whiteSpace: 'nowrap',
            letterSpacing: '-0.01em',
          }}>{p.action}</button>
        )}
      </div>
    </div>
  );
};

// 참여자 탭 콘텐츠
const ParticipantsTab = ({ visual, density, onTapPlan }) => (
  <div style={{ padding: '10px 20px 24px' }}>
    {PARTICIPANTS.map((p, i) => (
      <TimelineRow key={p.id} p={p} isLast={i === PARTICIPANTS.length - 1}
        visual={visual} density={density} onTap={onTapPlan}/>
    ))}
  </div>
);

// placeholder
const EmptyTabContent = ({ label }) => (
  <div style={{
    padding: '80px 24px', textAlign: 'center',
  }}>
    <div style={{
      width: 64, height: 64, borderRadius: 999, margin: '0 auto 18px',
      background: 'var(--gray-100)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Icon name="sparkles" size={28} color="var(--fg4)" strokeWidth={1.6}/>
    </div>
    <div style={{
      fontSize: 15, fontWeight: 700, color: 'var(--fg2)',
      letterSpacing: '-0.02em', marginBottom: 4,
    }}>{label}</div>
    <div style={{ fontSize: 12, color: 'var(--fg4)' }}>
      이후 디자인에서 내용이 추가됩니다
    </div>
  </div>
);

// ========== 참여 시뮬레이션 바텀시트 ==========
// 선택된 회차(1~totalRounds)에 대한 실시간 금액 계산 후 "참여하기"
const JoinSimSheet = ({ open, onClose, totalRounds = 13, monthly = 105120, initialRound = 4 }) => {
  const [round, setRound] = React.useState(initialRound);
  React.useEffect(() => { if (open) setRound(initialRound); }, [open, initialRound]);
  if (!open) return null;

  const payout = monthly * totalRounds;
  // 심플 이자 계산: 이자는 수령 시점이 빠를수록 많이 (대출) / 늦을수록 절감 (예금)
  const midpoint = (totalRounds + 1) / 2;
  const interestRate = 0.006; // 월
  const interest = Math.round(monthly * totalRounds * interestRate * (midpoint - round));
  const gift = round === 1 ? 500 : 0;
  const fee = 0;

  return (
    <div onClick={onClose} style={{
      position: 'absolute', inset: 0, zIndex: 90,
      background: 'rgba(0,0,0,0.45)',
      display: 'flex', alignItems: 'flex-end',
      animation: 'fadeIn 0.2s ease-out',
    }}>
      <style>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes slideUp { from { transform: translateY(100%) } to { transform: translateY(0) } }
      `}</style>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: '100%', background: '#fff',
        borderTopLeftRadius: 20, borderTopRightRadius: 20,
        paddingBottom: 0, overflow: 'hidden',
        animation: 'slideUp 0.25s ease-out',
      }}>
        {/* grabber */}
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 10 }}>
          <div style={{ width: 40, height: 4, borderRadius: 2, background: 'var(--gray-200)' }}/>
        </div>

        {/* 상단: 닫기 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '4px 12px 0' }}>
          <button onClick={onClose} style={{
            width: 36, height: 36, border: 'none', background: 'transparent',
            cursor: 'pointer', padding: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--fg2)"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {/* 헤더 */}
        <div style={{ padding: '0 20px 14px', textAlign: 'center' }}>
          <div style={{
            fontSize: 13, fontWeight: 600, color: 'var(--fg2)',
            letterSpacing: '-0.02em',
          }}>
            <span style={{ color: 'var(--brand-600)' }}>→</span> 월 <span style={{ color: 'var(--fg1)', fontWeight: 700 }}>{monthly.toLocaleString('ko-KR')}원</span> 씩 <span style={{ color: 'var(--fg1)', fontWeight: 700 }}>{totalRounds}개월</span> 모으기
          </div>
        </div>

        {/* 회차 셀렉터 — 가로 바 */}
        <div style={{ padding: '0 20px 6px' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: `repeat(${totalRounds}, 1fr)`, gap: 3,
            position: 'relative',
          }}>
            {Array.from({ length: totalRounds }, (_, i) => i + 1).map(n => {
              const on = n === round;
              return (
                <button key={n} onClick={() => setRound(n)} style={{
                  height: 26, padding: 0, borderRadius: 4,
                  border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                  background: on ? 'var(--brand-600)' : 'var(--brand-100)',
                  color: on ? '#fff' : 'var(--brand-700)',
                  fontSize: 11, fontWeight: 700,
                  transition: 'background 0.12s ease',
                  letterSpacing: '-0.01em',
                }}>{n}</button>
              );
            })}
          </div>
          {/* indicator under selected */}
          <div style={{
            position: 'relative', height: 14, marginTop: 2,
          }}>
            <div style={{
              position: 'absolute',
              left: `calc(${((round - 0.5) / totalRounds) * 100}% - 5px)`,
              top: 0, width: 0, height: 0,
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderBottom: '6px solid var(--brand-600)',
              transform: 'rotate(180deg)',
              transition: 'left 0.15s ease',
            }}/>
          </div>
        </div>

        <div style={{
          padding: '2px 20px 18px', textAlign: 'center',
          fontSize: 13, fontWeight: 600, color: 'var(--fg2)',
          letterSpacing: '-0.01em',
        }}>
          <span style={{ color: 'var(--brand-600)', fontWeight: 700 }}>{round}회차</span> 납입 후 목돈 수령
        </div>

        {/* 금액 상세 */}
        <div style={{
          margin: '0 20px 14px', padding: '16px 0',
          borderTop: '1px solid var(--gray-100)',
        }}>
          <Row label={`목돈 (${round}회차 납입 후 수령)`} value={`${payout.toLocaleString('ko-KR')}원`} bold/>
          <Row label="총 이자"
            value={`${interest >= 0 ? '+' : ''}${interest.toLocaleString('ko-KR')}원`}
            valueColor={interest < 0 ? 'var(--error-600)' : 'var(--success-600)'} bold/>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '6px 0 0',
          }}>
            <div style={{
              fontSize: 11, fontWeight: 500, color: 'var(--fg4)',
              letterSpacing: '-0.01em',
            }}>선물 (스테이지 시작시 지급)</div>
            <div style={{ display: 'flex', gap: 6 }}>
              <span style={giftBadge('#7a5af8', 'var(--brand-50)')}>
                <span style={{ fontSize: 9, opacity: 0.7 }}>◆</span> {gift}P
              </span>
              <span style={giftBadge('var(--fg3)', '#fff', '1px solid var(--border-primary)')}>
                {fee}원
              </span>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div style={{
          padding: '10px 20px 24px', borderTop: '1px solid var(--gray-100)',
          background: '#fff',
        }}>
          <button style={{
            width: '100%', padding: '15px', borderRadius: 10, border: 'none',
            background: 'var(--brand-600)', color: '#fff',
            fontSize: 15, fontWeight: 700, cursor: 'pointer',
            fontFamily: 'inherit', letterSpacing: '-0.01em',
            boxShadow: '0 2px 8px rgba(105,56,239,0.25)',
          }}>참여하기</button>
        </div>
      </div>
    </div>
  );
};

const Row = ({ label, value, valueColor, bold }) => (
  <div style={{
    display: 'flex', justifyContent: 'space-between', padding: '4px 0',
  }}>
    <span style={{
      fontSize: 13, fontWeight: 500, color: 'var(--fg3)',
      letterSpacing: '-0.01em',
    }}>{label}</span>
    <span style={{
      fontSize: 14, fontWeight: bold ? 700 : 500,
      color: valueColor || 'var(--fg1)',
      letterSpacing: '-0.01em',
    }}>{value}</span>
  </div>
);

const giftBadge = (color, bg, border) => ({
  display: 'inline-flex', alignItems: 'center', gap: 3,
  padding: '3px 8px', borderRadius: 999,
  background: bg, color, border: border || 'none',
  fontSize: 11, fontWeight: 700, letterSpacing: '-0.01em',
  whiteSpace: 'nowrap',
});

Object.assign(window, {
  StageSummaryCard, StageDetailTabs, ParticipantsTab, EmptyTabContent,
  JoinSimSheet,
  STAGE_INFO, PARTICIPANTS,
});
