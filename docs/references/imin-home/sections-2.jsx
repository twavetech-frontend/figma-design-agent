// Bottom half of home screen

// ===== Recommendation slider (realtime calc) =====
const StageRecommender = () => {
  const [turn, setTurn] = React.useState(3);
  const [monthly, setMonthly] = React.useState(100000);  // 월 10만원
  const [months, setMonths] = React.useState(13);
  const [showHow, setShowHow] = React.useState(false);

  // Simple calc: receive at turn => monthly * months - fees. For earlier turn, smaller.
  const basePayout = monthly * months;
  const discount = (turn - 1) / (months - 1); // 0 for first, 1 for last
  const payout = Math.round(basePayout * (1 - 0.04 * (1 - discount))); // earlier = slight discount

  const Stepper = ({ value, onDec, onInc, min, max }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      background: '#fff', border: '1px solid var(--border-primary)',
      borderRadius: 999, padding: 4, boxShadow: 'var(--shadow-xs)',
    }}>
      <button onClick={onDec} disabled={value <= min} style={stepBtn(value <= min)}>
        <Icon name="minus" size={16} color={value <= min ? 'var(--fg4)' : 'var(--fg2)'} strokeWidth={2.2}/>
      </button>
      <div style={{ minWidth: 32, textAlign: 'center', fontSize: 15, fontWeight: 600, color: 'var(--fg1)' }}>
        {value}
      </div>
      <button onClick={onInc} disabled={value >= max} style={stepBtn(value >= max)}>
        <Icon name="plus" size={16} color={value >= max ? 'var(--fg4)' : 'var(--fg2)'} strokeWidth={2.2}/>
      </button>
    </div>
  );

  return (
    <div style={{ padding: '32px 20px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <Icon name="sparkles" size={16} color="var(--brand-600)"/>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--brand-700)' }}>지민님을 위한 추천</span>
      </div>
      <h2 style={{ margin: '0 0 16px', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--fg1)' }}>
        1,300만원 모으기 도전
      </h2>

      <div style={{
        background: 'linear-gradient(180deg, var(--brand-600) 0%, var(--brand-700) 100%)',
        borderRadius: 20, padding: 20, color: '#fff',
        boxShadow: '0 8px 24px -4px rgba(105, 56, 239, 0.35)',
      }}>
        <div style={{ fontSize: 13, fontWeight: 500, opacity: 0.8 }}>{turn}번째 회차 예상 수령액</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 6 }}>
          <span style={{ fontSize: 36, fontWeight: 800, letterSpacing: '-0.03em' }}>
            {(payout/10000).toLocaleString('ko-KR', { maximumFractionDigits: 0 })}
          </span>
          <span style={{ fontSize: 18, fontWeight: 600, opacity: 0.9 }}>만원</span>
        </div>
        <div style={{
          marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: '4px 10px', background: 'rgba(255,255,255,0.15)', borderRadius: 999,
          fontSize: 12, fontWeight: 500,
        }}>
          <Icon name="trending-up" size={12} color="#fff" strokeWidth={2.5}/>
          월 {(monthly/10000).toFixed(0)}만원 × {months}개월
        </div>

        {/* controls */}
        <div style={{
          marginTop: 18, padding: 14, background: 'rgba(255,255,255,0.12)',
          borderRadius: 14, display: 'flex', flexDirection: 'column', gap: 14,
          backdropFilter: 'blur(8px)',
        }}>
          {/* turn slider */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 500, opacity: 0.85 }}>몇 번째로 받을래요?</span>
              <span style={{ fontSize: 12, fontWeight: 700 }}>{turn} / {months}회차</span>
            </div>
            <input type="range" min="1" max={months} value={turn}
              onChange={e => setTurn(Number(e.target.value))}
              style={rangeStyle}
            />
          </div>

          {/* row of steppers */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 500, opacity: 0.85 }}>월 납입</div>
            <Stepper
              value={monthly/10000}
              onDec={() => setMonthly(Math.max(50000, monthly - 50000))}
              onInc={() => setMonthly(Math.min(1000000, monthly + 50000))}
              min={5} max={100}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 500, opacity: 0.85 }}>기간 (개월)</div>
            <Stepper
              value={months}
              onDec={() => { const v = Math.max(6, months - 1); setMonths(v); if (turn > v) setTurn(v); }}
              onInc={() => setMonths(Math.min(24, months + 1))}
              min={6} max={24}
            />
          </div>
        </div>

        <button style={{
          marginTop: 14, width: '100%', padding: '14px 16px',
          background: '#fff', color: 'var(--brand-700)',
          border: 'none', borderRadius: 12,
          fontSize: 15, fontWeight: 700, cursor: 'pointer',
          fontFamily: 'inherit', letterSpacing: '-0.01em',
        }}>
          맞는 스테이지 찾기
        </button>

        <button onClick={() => setShowHow(!showHow)} style={{
          marginTop: 10, background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.85)',
          fontSize: 12, fontWeight: 500, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
          padding: 0, fontFamily: 'inherit',
        }}>
          <Icon name="info" size={12} color="rgba(255,255,255,0.85)" strokeWidth={2}/>
          어떻게 계산되나요?
          <Icon name="chevron-down" size={12} color="rgba(255,255,255,0.85)" strokeWidth={2}
            style={{ transform: showHow ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}/>
        </button>
        {showHow && (
          <div style={{ marginTop: 8, fontSize: 11.5, lineHeight: 1.5, color: 'rgba(255,255,255,0.85)' }}>
            회차가 빠를수록 선수령 이자가 적용되어 수령액이 다소 줄어들어요. 참가자 전원이 매달 납입하면 해당 회차 순서대로 모인 금액을 받습니다. 수수료는 연 3%로 계산되었어요.
          </div>
        )}
      </div>
    </div>
  );
};

const stepBtn = (disabled) => ({
  width: 28, height: 28, borderRadius: 999, border: 'none',
  background: disabled ? 'var(--gray-100)' : 'var(--gray-50)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: disabled ? 'default' : 'pointer', padding: 0,
});

const rangeStyle = {
  width: '100%', appearance: 'none', height: 6, borderRadius: 999,
  background: 'rgba(255,255,255,0.3)', outline: 'none',
};

// ===== Current stages =====
const CurrentStages = () => {
  const stages = [
    { rate: 3.2, amount: 3000000, label: '13개월 · 5번째 수령', status: '진행 중', statusColor: 'brand', fav: true },
    { rate: 2.8, amount: 5000000, label: '12개월 · 8번째 수령', status: '지급 예정', statusColor: 'warning', fav: false },
    { rate: 4.1, amount: 2000000, label: '10개월 · 3번째 수령', status: '미납', statusColor: 'error', fav: true },
  ];
  const statusBg = {
    brand:   { bg: 'var(--brand-50)',   fg: 'var(--brand-700)' },
    warning: { bg: 'var(--warning-50)', fg: 'var(--warning-700)' },
    error:   { bg: 'var(--error-50)',   fg: 'var(--error-700)' },
  };
  return (
    <div style={{ marginTop: 32 }}>
      <div style={{ padding: '0 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--fg1)' }}>참여 중인 스테이지</h3>
        <button style={linkBtn}>
          전체보기 <Icon name="chevron" size={14} color="var(--fg3)" strokeWidth={2}/>
        </button>
      </div>
      <div style={{
        display: 'flex', gap: 10, overflowX: 'auto', padding: '0 16px 4px',
        WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none',
      }}>
        <style>{`.stg-scroll::-webkit-scrollbar{display:none}`}</style>
        <div className="stg-scroll" style={{ display: 'flex', gap: 10 }}>
          {stages.map((s, i) => {
            const sc = statusBg[s.statusColor];
            return (
              <div key={i} style={{
                flex: '0 0 auto', width: 220, padding: 16,
                background: '#fff', border: '1px solid var(--border-secondary)',
                borderRadius: 14, boxShadow: 'var(--shadow-xs)',
                position: 'relative',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{
                    padding: '3px 8px', background: sc.bg, borderRadius: 999,
                    fontSize: 11, fontWeight: 700, color: sc.fg,
                  }}>{s.status}</div>
                  <button style={{
                    background: 'transparent', border: 'none', cursor: 'pointer', padding: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon name={s.fav ? 'heart-fill' : 'heart'} size={18}
                      color={s.fav ? 'var(--error-500)' : 'var(--fg4)'}/>
                  </button>
                </div>
                <div style={{ marginTop: 10, display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--brand-700)' }}>이율</span>
                  <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--brand-700)', letterSpacing: '-0.02em' }}>
                    {s.rate}%
                  </span>
                </div>
                <div style={{ marginTop: 6, fontSize: 20, fontWeight: 700, color: 'var(--fg1)', letterSpacing: '-0.02em' }}>
                  {(s.amount/10000).toLocaleString('ko-KR')}만원
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: 'var(--fg3)' }}>{s.label}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ===== Attendance + event banner =====
const AttendanceStrip = () => {
  const streak = 12;
  const today = 3; // 0-indexed "today" in the 7-day strip
  const days = ['월','화','수','목','금','토','일'];
  const checked = [true, true, true, true, false, false, false];
  return (
    <div style={{ padding: '32px 20px 0' }}>
      <div style={{
        padding: 18, background: '#fff', border: '1px solid var(--border-secondary)',
        borderRadius: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="fire" size={18} color="var(--warning-500)"/>
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--fg1)' }}>
                연속 {streak}일 출석 중
              </span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg3)', marginTop: 2 }}>
              오늘 출석 시 100P 적립
            </div>
          </div>
          <button style={{
            padding: '8px 14px', background: 'var(--brand-600)', color: '#fff',
            border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600,
            cursor: 'pointer', fontFamily: 'inherit',
          }}>
            출석
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 4 }}>
          {days.map((d, i) => (
            <div key={i} style={{
              flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
            }}>
              <div style={{
                width: 32, height: 32, borderRadius: 999,
                background: checked[i]
                  ? (i === today ? 'var(--warning-500)' : 'var(--brand-100)')
                  : 'var(--gray-100)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: i === today ? '2px solid var(--warning-600)' : 'none',
              }}>
                {checked[i]
                  ? <Icon name={i === today ? 'fire' : 'check'} size={16}
                      color={i === today ? '#fff' : 'var(--brand-700)'} strokeWidth={2.5}/>
                  : <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg4)' }}>{d}</span>
                }
              </div>
              <span style={{
                fontSize: 10, fontWeight: 500,
                color: i === today ? 'var(--warning-700)' : 'var(--fg4)',
              }}>{i === today ? '오늘' : d}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const EventBanner = () => {
  const [idx, setIdx] = React.useState(0);
  const banners = [
    { tag: '이벤트', title: '친구 초대하고 1만 포인트 받기', sub: '친구가 첫 스테이지 참여 시', bg: 'linear-gradient(135deg, #7a5af8, #6938ef)' },
    { tag: '공지', title: '4월 25일 서비스 점검 안내', sub: '02:00 ~ 04:00 (2시간)', bg: 'linear-gradient(135deg, #414651, #181d27)' },
    { tag: '프로모션', title: '신규 가입 · 첫 달 납입 캐시백', sub: '최대 5만원까지', bg: 'linear-gradient(135deg, #dc6803, #b54708)' },
  ];
  return (
    <div style={{ padding: '16px 16px 0' }}>
      <div style={{
        borderRadius: 14, padding: 18, color: '#fff', minHeight: 88,
        background: banners[idx].bg, position: 'relative', overflow: 'hidden', cursor: 'pointer',
      }}>
        <div style={{
          display: 'inline-block', padding: '2px 8px', background: 'rgba(255,255,255,0.2)',
          borderRadius: 999, fontSize: 10, fontWeight: 700, marginBottom: 6, letterSpacing: '0.02em',
        }}>{banners[idx].tag}</div>
        <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.01em' }}>{banners[idx].title}</div>
        <div style={{ fontSize: 12, opacity: 0.9, marginTop: 2 }}>{banners[idx].sub}</div>
        <div style={{
          position: 'absolute', bottom: 10, right: 14,
          display: 'flex', gap: 4,
        }}>
          {banners.map((_, i) => (
            <span key={i} onClick={(e) => { e.stopPropagation(); setIdx(i); }}
              style={{
                width: i === idx ? 16 : 6, height: 6, borderRadius: 999,
                background: i === idx ? '#fff' : 'rgba(255,255,255,0.45)',
                transition: 'all 0.2s', cursor: 'pointer',
              }}/>
          ))}
        </div>
      </div>
    </div>
  );
};

// ===== Lounge =====
const LoungeSection = () => {
  const items = [
    { title: '캠핑 감성 티셔츠', discount: 42, price: 19800, tag: '핫딜' },
    { title: '프리미엄 원두 500g', discount: 28, price: 14900 },
    { title: '무선 이어폰', discount: 35, price: 49000, tag: 'BEST' },
  ];
  return (
    <div style={{ marginTop: 32 }}>
      <div style={{ padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--fg1)' }}>라운지</h3>
        <button style={linkBtn}>
          전체보기 <Icon name="chevron" size={14} color="var(--fg3)" strokeWidth={2}/>
        </button>
      </div>
      <div style={{ padding: '0 20px 14px', fontSize: 12, color: 'var(--fg3)' }}>
        사용 가능 <span style={{ color: 'var(--brand-700)', fontWeight: 700 }}>8,420P</span>
      </div>
      <div style={{
        display: 'flex', gap: 10, overflowX: 'auto', padding: '0 16px',
        WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none',
      }}>
        <style>{`.lng-scroll::-webkit-scrollbar{display:none}`}</style>
        <div className="lng-scroll" style={{ display: 'flex', gap: 10 }}>
          {items.map((it, i) => (
            <div key={i} style={{
              flex: '0 0 auto', width: 150,
              background: '#fff', border: '1px solid var(--border-secondary)',
              borderRadius: 14, overflow: 'hidden',
            }}>
              <div style={{
                aspectRatio: '1/1', background: ['var(--brand-100)','var(--warning-100)','var(--gray-100)'][i],
                position: 'relative',
              }}>
                {it.tag && (
                  <div style={{
                    position: 'absolute', top: 8, left: 8,
                    padding: '2px 8px', background: 'var(--error-600)', color: '#fff',
                    borderRadius: 4, fontSize: 10, fontWeight: 700, letterSpacing: '0.02em',
                  }}>{it.tag}</div>
                )}
              </div>
              <div style={{ padding: 12 }}>
                <div style={{ fontSize: 12, color: 'var(--fg2)', marginBottom: 4,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {it.title}
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--error-600)' }}>{it.discount}%</span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--fg1)' }}>
                    {it.price.toLocaleString('ko-KR')}원
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ===== Cumulative tab content =====
const CumulativeView = ({ hidden }) => {
  const fmt = (n) => hidden ? '•••••' : (n/10000).toLocaleString('ko-KR');
  return (
    <div style={{ padding: '20px 16px 0' }}>
      <div style={{
        background: 'linear-gradient(135deg, var(--brand-25), var(--brand-50))',
        border: '1px solid var(--brand-100)', borderRadius: 16, padding: 20,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--brand-700)', marginBottom: 4 }}>나의 누적 실적</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 14 }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--fg3)', marginBottom: 4 }}>누적 수령액</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--brand-900)', letterSpacing: '-0.02em' }}>
              {fmt(38200000)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--fg3)' }}>만원</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--fg3)', marginBottom: 4 }}>누적 납입액</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg1)', letterSpacing: '-0.02em' }}>
              {fmt(36800000)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--fg3)' }}>만원</div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 16, padding: 18, background: '#fff', border: '1px solid var(--border-secondary)', borderRadius: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg1)', marginBottom: 10 }}>플랫폼 현황</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <StatRow label="전체 누적 거래액" value="2조 1,430억" icon="layers"/>
          <StatRow label="이번 달 수령자 수" value="8,421명" icon="users"/>
          <StatRow label="평균 수령 금액" value="1,280만원" icon="trending-up"/>
        </div>
      </div>

      <div style={{ marginTop: 16, padding: 18, background: 'var(--brand-950)', borderRadius: 16, color: '#fff' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <Icon name="megaphone" size={14} color="#fff"/>
          <span style={{ fontSize: 12, fontWeight: 600, opacity: 0.85 }}>이번 달 헤비 유저</span>
        </div>
        <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.3 }}>
          127명이 이번 달에<br/>1,000만원 이상 받아갔어요
        </div>
        <button style={{
          marginTop: 12, padding: '8px 14px', background: 'rgba(255,255,255,0.15)',
          border: '1px solid rgba(255,255,255,0.2)', color: '#fff',
          borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          display: 'flex', alignItems: 'center', gap: 4,
        }}>
          사례 보기 <Icon name="external" size={12} color="#fff" strokeWidth={2}/>
        </button>
      </div>
    </div>
  );
};

const StatRow = ({ label, value, icon }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
    <div style={{
      width: 32, height: 32, borderRadius: 8, background: 'var(--brand-50)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Icon name={icon} size={16} color="var(--brand-700)"/>
    </div>
    <div style={{ flex: 1, fontSize: 13, color: 'var(--fg2)' }}>{label}</div>
    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--fg1)' }}>{value}</div>
  </div>
);

// ===== Onboarding banner (P2) =====
const OnboardingNudge = () => (
  <div style={{ padding: '32px 16px 0' }}>
    <div style={{
      padding: 16, background: 'var(--warning-50)', border: '1px solid var(--warning-300)',
      borderRadius: 14, display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10, background: 'var(--warning-500)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon name="credit-card" size={20} color="#fff" strokeWidth={2}/>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning-700)' }}>지급 계좌 연결이 필요해요</div>
        <div style={{ fontSize: 12, color: 'var(--warning-700)', opacity: 0.85, marginTop: 1 }}>
          수령액을 받으려면 계좌를 연결해주세요
        </div>
      </div>
      <button style={{
        padding: '8px 12px', background: 'var(--warning-700)', color: '#fff',
        border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 700,
        cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0,
      }}>
        연결
      </button>
    </div>
  </div>
);

// ===== Bottom nav =====
const BottomNav = () => {
  const items = [
    { id: 'home', label: '홈', icon: 'home', active: true, badge: 1 },
    { id: 'lounge', label: '라운지', icon: 'gift' },
    { id: 'stages', label: '스테이지', icon: 'layers' },
    { id: 'community', label: '커뮤니티', icon: 'users' },
    { id: 'all', label: '전체', icon: 'grid' },
  ];
  return (
    <div style={{
      padding: '8px 8px 6px', background: '#fff',
      borderTop: '1px solid var(--border-secondary)',
      display: 'flex', justifyContent: 'space-around',
    }}>
      {items.map(it => (
        <button key={it.id} style={{
          flex: 1, padding: '6px 4px', background: 'transparent', border: 'none',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
          cursor: 'pointer', fontFamily: 'inherit', position: 'relative',
        }}>
          <div style={{ position: 'relative' }}>
            <Icon name={it.icon} size={22} color={it.active ? 'var(--brand-600)' : 'var(--fg4)'}
              strokeWidth={it.active ? 2 : 1.8}/>
            {it.badge && (
              <span style={{
                position: 'absolute', top: -2, right: -4, minWidth: 14, height: 14,
                padding: '0 3px', borderRadius: 999, background: 'var(--error-500)',
                color: '#fff', fontSize: 9, fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: '1.5px solid #fff',
              }}>{it.badge}</span>
            )}
          </div>
          <span style={{
            fontSize: 10, fontWeight: it.active ? 600 : 500,
            color: it.active ? 'var(--brand-600)' : 'var(--fg4)',
          }}>{it.label}</span>
        </button>
      ))}
    </div>
  );
};

const linkBtn = {
  background: 'transparent', border: 'none', fontSize: 13, fontWeight: 500,
  color: 'var(--fg3)', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', gap: 2,
  fontFamily: 'inherit',
};

Object.assign(window, {
  StageRecommender, CurrentStages, AttendanceStrip, EventBanner,
  LoungeSection, CumulativeView, OnboardingNudge, BottomNav,
});
