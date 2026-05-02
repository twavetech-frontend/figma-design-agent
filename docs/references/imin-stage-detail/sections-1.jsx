// Home screen sections for imin app

const KRW = (n) => n.toLocaleString('ko-KR') + '원';
const KRWCompact = (n) => {
  if (n >= 10000000) return Math.floor(n / 10000).toLocaleString('ko-KR') + '원';
  return n.toLocaleString('ko-KR') + '원';
};

// Lucide icon via inline SVG (stroke style matches DS)
const Icon = ({ name, size = 20, color = 'currentColor', strokeWidth = 1.67 }) => {
  const paths = {
    bell: <><path d="M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 003.4 0"/></>,
    'message-square': <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>,
    chevron: <path d="M9 18l6-6-6-6"/>,
    'chevron-left': <path d="M15 18l-6-6 6-6"/>,
    'chevron-down': <path d="M6 9l6 6 6-6"/>,
    eye: <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>,
    'eye-off': <><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></>,
    plus: <><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></>,
    minus: <line x1="5" y1="12" x2="19" y2="12"/>,
    alert: <><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></>,
    check: <polyline points="20 6 9 17 4 12"/>,
    'arrow-down': <><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></>,
    'arrow-up': <><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></>,
    heart: <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>,
    'heart-fill': <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" fill={color}/>,
    calendar: <><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></>,
    refresh: <><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></>,
    gift: <><polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 010-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 000-5C13 2 12 7 12 7z"/></>,
    fire: <path d="M8.5 14.5A2.5 2.5 0 0011 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 11-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 002.5 2.5z"/>,
    home: <><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></>,
    compass: <><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></>,
    layers: <><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></>,
    users: <><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></>,
    grid: <><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></>,
    'credit-card': <><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></>,
    'info': <><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></>,
    'external': <><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></>,
    sparkles: <><path d="M12 2l2.5 6.5L21 11l-6.5 2.5L12 20l-2.5-6.5L3 11l6.5-2.5z"/></>,
    'trending-up': <><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></>,
    megaphone: <><path d="M3 11v2a1 1 0 001 1h2l4 4V6L6 10H4a1 1 0 00-1 1z"/><path d="M14 7s3 2 3 5-3 5-3 5"/></>,
    'shield-check': <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
};

// ===== Header (fixed top) =====
const AppHeader = ({ balanceHidden, onToggleBalance }) => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '8px 20px 12px', background: '#fff',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: 'linear-gradient(135deg, #c084fc 0%, #6938ef 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginRight: 8,
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <circle cx="9" cy="9" r="4" fill="#fff" opacity="0.95"/>
          <circle cx="15" cy="13" r="4" fill="#fff" opacity="0.7"/>
        </svg>
      </div>
      <div style={{ fontSize: 22, fontWeight: 800, color: '#181d27', letterSpacing: '-0.02em' }}>imin</div>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <button onClick={onToggleBalance} style={btn()}>
        <Icon name={balanceHidden ? 'eye-off' : 'eye'} size={22} color="#414651" />
      </button>
      <button style={btn()}>
        <div style={{ position: 'relative' }}>
          <Icon name="bell" size={22} color="#414651" />
          <span style={{
            position: 'absolute', top: -2, right: -2, width: 8, height: 8,
            borderRadius: 99, background: 'var(--error-500)', border: '2px solid #fff',
          }}/>
        </div>
      </button>
      <button style={btn()}>
        <Icon name="message-square" size={22} color="#414651" />
      </button>
    </div>
  </div>
);
const btn = () => ({
  width: 40, height: 40, borderRadius: 8, border: 'none', background: 'transparent',
  display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0,
});

// ===== Tabs =====
const HomeTabs = ({ active, onChange }) => {
  const tabs = [{ id: 'transactions', label: '거래 현황' }, { id: 'cumulative', label: '누적 거래' }];
  return (
    <div style={{ padding: '0 20px', background: '#fff', borderBottom: '1px solid var(--border-secondary)' }}>
      <div style={{ display: 'flex', gap: 24 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => onChange(t.id)} style={{
            background: 'transparent', border: 'none', padding: '12px 0 14px',
            fontFamily: 'inherit', fontSize: 16, fontWeight: 600, cursor: 'pointer',
            color: active === t.id ? 'var(--fg1)' : 'var(--fg4)',
            borderBottom: active === t.id ? '2px solid var(--fg1)' : '2px solid transparent',
            marginBottom: -1,
          }}>{t.label}</button>
        ))}
      </div>
    </div>
  );
};

// ===== Missed payment alert (P0) =====
const MissedAlert = ({ onTap }) => (
  <div onClick={onTap} style={{
    margin: '12px 16px 0', padding: '12px 14px',
    background: 'var(--error-50)', border: '1px solid var(--error-300)',
    borderRadius: 12, display: 'flex', alignItems: 'center', gap: 10,
    cursor: 'pointer',
  }}>
    <div style={{
      width: 32, height: 32, borderRadius: 999, background: 'var(--error-600)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <Icon name="alert" size={18} color="#fff" strokeWidth={2} />
    </div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--error-700)' }}>미납 1건 · 4월 18일</div>
      <div style={{ fontSize: 13, color: 'var(--error-600)', marginTop: 1 }}>지금 납입하지 않으면 연체 이자가 발생해요</div>
    </div>
    <Icon name="chevron" size={18} color="var(--error-600)" strokeWidth={2} />
  </div>
);

// ===== Summary card =====
const SummaryCard = ({ stageCount, earned, owed, hidden }) => {
  const fmt = (n) => hidden ? '•••••••' : n.toLocaleString('ko-KR');
  return (
    <div style={{
      margin: '16px 16px 0', padding: 20,
      background: '#fff', border: '1px solid var(--border-secondary)',
      borderRadius: 16, boxShadow: 'var(--shadow-xs)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}>
          <span style={{
            fontSize: 12, fontWeight: 700, color: 'var(--brand-700)',
            background: 'var(--brand-50)', padding: '3px 9px', borderRadius: 999,
            border: '1px solid var(--brand-200)', flexShrink: 0,
          }}>{stageCount}건 진행 중</span>
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg1)' }}>내 스테이지</span>
        </div>
        <Icon name="chevron" size={18} color="var(--fg4)" strokeWidth={2} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{
          padding: 14, background: 'var(--brand-25)', border: '1px solid var(--brand-100)',
          borderRadius: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6 }}>
            <Icon name="arrow-down" size={12} color="var(--brand-700)" strokeWidth={2.5}/>
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-700)' }}>모은 금액</span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--brand-900)', letterSpacing: '-0.02em' }}>
            {fmt(14420320)}
          </div>
          <div style={{ fontSize: 11, color: 'var(--brand-700)', marginTop: 2 }}>원</div>
        </div>

        <div style={{
          padding: 14, background: 'var(--gray-50)', border: '1px solid var(--border-secondary)',
          borderRadius: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6 }}>
            <Icon name="arrow-up" size={12} color="var(--fg3)" strokeWidth={2.5}/>
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg3)' }}>빌린 금액</span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--fg1)', letterSpacing: '-0.02em' }}>
            −{fmt(5240020)}
          </div>
          <div style={{ fontSize: 11, color: 'var(--fg3)', marginTop: 2 }}>원</div>
        </div>
      </div>
    </div>
  );
};

// ===== Schedule Calendar (swappable styles) =====
// Generate mock schedule for a month centered on "today"
const genSchedule = () => {
  const today = 20;
  const items = [];
  for (let d = 1; d <= 30; d++) {
    const dt = new Date(2026, 3, d);
    const dow = ['일','월','화','수','목','금','토'][dt.getDay()];
    items.push({ day: d, dow });
  }
  // mark events
  const events = {
    8:  { type: 'paid',     amount: 450000, label: '납입' },
    12: { type: 'received', amount: 1300000, label: '지급' },
    18: { type: 'overdue',  amount: 350000, label: '미납' },
    20: { type: 'due',      amount: 500000, label: '오늘' },
    24: { type: 'scheduled',amount: 450000, label: '납입' },
    27: { type: 'scheduled',amount: 350000, label: '납입' },
  };
  return items.map(it => ({ ...it, ...events[it.day], isToday: it.day === today, isPast: it.day < today }));
};

const HorizontalTimeline = ({ items }) => {
  const scrollRef = React.useRef(null);
  React.useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const el = container.querySelector('[data-today="true"]');
    if (el) {
      const left = el.offsetLeft - (container.clientWidth / 2) + (el.clientWidth / 2);
      container.scrollLeft = Math.max(0, left);
    }
  }, []);

  const typeStyle = (type, isToday) => {
    const base = {
      card: '#fff', border: 'var(--border-primary)', label: 'var(--fg4)', amount: 'var(--fg3)', dot: null,
    };
    if (type === 'overdue') return { card: 'var(--error-50)', border: 'var(--error-300)', label: 'var(--error-700)', amount: 'var(--error-700)', dot: 'var(--error-500)' };
    if (type === 'received') return { card: 'var(--brand-25)', border: 'var(--brand-200)', label: 'var(--brand-700)', amount: 'var(--brand-700)', dot: 'var(--brand-500)' };
    if (type === 'paid') return { card: 'var(--gray-50)', border: 'var(--border-secondary)', label: 'var(--fg3)', amount: 'var(--fg2)', dot: 'var(--success-500)' };
    if (type === 'scheduled') return { card: '#fff', border: 'var(--border-primary)', label: 'var(--fg2)', amount: 'var(--fg1)', dot: 'var(--gray-400)' };
    if (type === 'due' && isToday) return { card: 'var(--warning-50)', border: 'var(--warning-300)', label: 'var(--warning-700)', amount: 'var(--warning-700)', dot: 'var(--warning-500)' };
    return base;
  };

  return (
    <div ref={scrollRef} style={{
      overflowX: 'auto', overflowY: 'hidden', scrollSnapType: 'x mandatory',
      padding: '0 16px 4px',
      WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none',
    }}>
      <style>{`.tl-scroll::-webkit-scrollbar{display:none}`}</style>
      <div className="tl-scroll" style={{ display: 'flex', gap: 8 }}>
        {items.map(it => {
          const s = typeStyle(it.type, it.isToday);
          const empty = !it.type;
          const dim = it.isPast && it.type !== 'overdue';
          return (
            <div key={it.day} data-today={it.isToday ? 'true' : undefined} style={{
              flex: '0 0 auto', width: 68, height: 96,
              padding: '10px 8px', scrollSnapAlign: 'center',
              background: empty ? 'var(--gray-50)' : s.card,
              border: `1px solid ${empty ? 'var(--border-tertiary)' : s.border}`,
              borderRadius: 14,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-between',
              opacity: dim ? 0.55 : 1,
              outline: it.isToday ? '2px solid var(--brand-500)' : 'none',
              outlineOffset: it.isToday ? 1 : 0,
              position: 'relative',
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 500, color: empty ? 'var(--fg4)' : s.label }}>
                  {it.dow}
                </span>
                <span style={{
                  fontSize: 18, fontWeight: 700, color: empty ? 'var(--fg3)' : s.amount,
                  letterSpacing: '-0.02em', lineHeight: 1.1,
                }}>{it.day}</span>
              </div>
              {!empty && (
                <>
                  <div style={{ fontSize: 11, fontWeight: 600, color: s.amount, textAlign: 'center' }}>
                    {it.type === 'received' ? '+' : it.type === 'overdue' ? '' : ''}
                    {(it.amount/10000).toFixed(0)}만
                  </div>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 3,
                    padding: '2px 6px', borderRadius: 999,
                    background: s.dot ? `${s.card}` : 'transparent',
                    border: s.dot ? `1px solid ${s.border}` : 'none',
                  }}>
                    <span style={{ width: 4, height: 4, borderRadius: 99, background: s.dot }}/>
                    <span style={{ fontSize: 10, fontWeight: 600, color: s.label }}>{it.label}</span>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ListTimeline = ({ items }) => {
  // Only events, not empty days
  const withEvents = items.filter(i => i.type).sort((a,b) => {
    // overdue first, then today, then upcoming, then past
    const rank = (x) => x.type === 'overdue' ? 0 : x.isToday ? 1 : x.isPast ? 3 : 2;
    return rank(a) - rank(b) || a.day - b.day;
  });
  const typeMap = {
    overdue:   { bg:'var(--error-50)',   fg:'var(--error-700)',   icon:'alert',       iconBg:'var(--error-600)' },
    due:       { bg:'var(--warning-50)', fg:'var(--warning-700)', icon:'alert',       iconBg:'var(--warning-500)' },
    received:  { bg:'var(--brand-25)',   fg:'var(--brand-700)',   icon:'arrow-down',  iconBg:'var(--brand-600)' },
    paid:      { bg:'var(--gray-50)',    fg:'var(--fg2)',         icon:'check',       iconBg:'var(--success-600)' },
    scheduled: { bg:'#fff',              fg:'var(--fg2)',         icon:'arrow-up',    iconBg:'var(--gray-400)' },
  };
  return (
    <div style={{
      margin: '0 16px', border: '1px solid var(--border-secondary)', borderRadius: 14,
      overflow: 'hidden', background: '#fff',
    }}>
      {withEvents.map((it, i) => {
        const m = typeMap[it.type];
        const isPaidSign = it.type === 'received' ? '+' : it.type === 'paid' ? '' : '-';
        return (
          <div key={it.day} style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '14px 14px',
            background: m.bg,
            borderBottom: i < withEvents.length - 1 ? '1px solid var(--border-tertiary)' : 'none',
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10, background: m.iconBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Icon name={m.icon} size={18} color="#fff" strokeWidth={2.2}/>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: m.fg }}>
                {it.label} · 4월 {it.day}일 ({it.dow})
              </div>
              <div style={{ fontSize: 12, color: 'var(--fg3)', marginTop: 1 }}>
                {it.type === 'overdue' ? '연체 · 즉시 납입 필요' :
                 it.isToday ? '오늘 예정' :
                 it.isPast ? '완료' : '예정'}
              </div>
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: m.fg, letterSpacing: '-0.01em' }}>
              {isPaidSign}{(it.amount/10000).toLocaleString('ko-KR')}만원
            </div>
          </div>
        );
      })}
    </div>
  );
};

const ScheduleSection = ({ calendarStyle }) => {
  const items = React.useMemo(() => genSchedule(), []);
  const missed = items.filter(i => i.type === 'overdue').length;
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--fg1)' }}>이번 달 납입·지급</h3>
          {missed > 0 && (
            <span style={{
              fontSize: 11, fontWeight: 700, color: '#fff', background: 'var(--error-600)',
              padding: '2px 7px', borderRadius: 999,
            }}>미납 {missed}</span>
          )}
        </div>
        <button style={{
          background: 'transparent', border: 'none', fontSize: 13, fontWeight: 500,
          color: 'var(--fg3)', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', gap: 2,
        }}>
          전체보기 <Icon name="chevron" size={14} color="var(--fg3)" strokeWidth={2}/>
        </button>
      </div>
      {calendarStyle === 'list' ? <ListTimeline items={items}/> : <HorizontalTimeline items={items}/>}
    </div>
  );
};

// ===== Credit / limit =====
const LimitSection = ({ hidden }) => {
  const total = 52000000, used = 3600000;
  const pct = (used / total) * 100;
  const fmt = (n) => hidden ? '•••••' : (n/10000).toLocaleString('ko-KR');
  return (
    <div style={{ padding: '24px 20px 0' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700, color: 'var(--fg1)' }}>한도 · 신용 현황</h3>
      <div style={{
        padding: 18, background: '#fff', border: '1px solid var(--border-secondary)',
        borderRadius: 16, boxShadow: 'var(--shadow-xs)',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, color: 'var(--fg3)' }}>이용 중</span>
          <span style={{ fontSize: 13, color: 'var(--fg4)' }}>{pct.toFixed(1)}% 사용</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
          <span style={{ fontSize: 24, fontWeight: 700, color: 'var(--fg1)', letterSpacing: '-0.02em' }}>{fmt(used)}</span>
          <span style={{ fontSize: 14, color: 'var(--fg3)' }}>만원</span>
          <span style={{ fontSize: 13, color: 'var(--fg4)', marginLeft: 'auto' }}>총 {fmt(total)}만원</span>
        </div>
        <div style={{
          height: 8, background: 'var(--gray-100)', borderRadius: 999, overflow: 'hidden',
        }}>
          <div style={{
            height: '100%', width: `${pct}%`,
            background: 'linear-gradient(90deg, var(--brand-400), var(--brand-600))',
            borderRadius: 999,
          }}/>
        </div>
        <div style={{
          marginTop: 14, padding: '10px 12px',
          background: 'var(--brand-25)', border: '1px solid var(--brand-100)',
          borderRadius: 10, display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
        }}>
          <Icon name="shield-check" size={18} color="var(--brand-700)" strokeWidth={2}/>
          <div style={{ flex: 1, fontSize: 13, fontWeight: 500, color: 'var(--brand-800)' }}>
            신용점수를 연동하면 한도가 늘어나요
          </div>
          <Icon name="chevron" size={16} color="var(--brand-700)" strokeWidth={2}/>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, {
  Icon, AppHeader, HomeTabs, MissedAlert, SummaryCard,
  ScheduleSection, LimitSection, KRW, KRWCompact,
});
