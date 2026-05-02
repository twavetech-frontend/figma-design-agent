const { useState, useEffect } = React;

function PhoneShell({ children }) {
  const W = 390, H = 844;
  return (
    <div style={{
      width: W, height: H, borderRadius: 48, overflow: 'hidden',
      position: 'relative', background: '#F2F2F7',
      boxShadow: '0 40px 80px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.12)',
      fontFamily: 'Pretendard, -apple-system, system-ui, sans-serif',
    }}>
      <div style={{
        position: 'absolute', top: 11, left: '50%', transform: 'translateX(-50%)',
        width: 126, height: 37, borderRadius: 24, background: '#000', zIndex: 50,
      }} />
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
        padding: '18px 32px 0', display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', color: '#000',
      }}>
        <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.01em' }}>10:34</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginRight: -6 }}>
          <svg width="17" height="11" viewBox="0 0 17 11"><rect x="0" y="7" width="3" height="4" rx="0.6" fill="#000"/><rect x="4.5" y="5" width="3" height="6" rx="0.6" fill="#000"/><rect x="9" y="2.5" width="3" height="8.5" rx="0.6" fill="#000"/><rect x="13.5" y="0" width="3" height="11" rx="0.6" fill="#000"/></svg>
          <svg width="15" height="11" viewBox="0 0 15 11"><path d="M7.5 3c2 0 3.8.8 5.1 2.1l1-1c-1.6-1.6-3.8-2.6-6.1-2.6S2.9 2.5 1.3 4.1l1 1C3.7 3.8 5.5 3 7.5 3zM7.5 6.1c1.2 0 2.3.5 3.1 1.3l1-1c-1.1-1.1-2.5-1.7-4.1-1.7s-3 .6-4.1 1.7l1 1c.8-.8 1.9-1.3 3.1-1.3zM7.5 9.4c.7 0 1.3.6 1.3 1.3 0 .1 0 .2-.1.3L7.5 13l-1.2-2c0-.1-.1-.2-.1-.3 0-.7.6-1.3 1.3-1.3z" fill="#000"/></svg>
          <svg width="24" height="11" viewBox="0 0 24 11"><rect x="0.5" y="0.5" width="20" height="10" rx="3" stroke="#000" strokeOpacity="0.35" fill="none"/><rect x="2" y="2" width="17" height="7" rx="1.5" fill="#000"/><path d="M22 4v3c.6-.2 1-.8 1-1.5S22.6 4.2 22 4z" fill="#000" fillOpacity="0.4"/></svg>
        </div>
      </div>
      <div style={{
        position: 'absolute', bottom: 8, left: 0, right: 0, zIndex: 60,
        display: 'flex', justifyContent: 'center', pointerEvents: 'none',
      }}>
        <div style={{ width: 139, height: 5, borderRadius: 100, background: 'rgba(0,0,0,0.3)' }}/>
      </div>
      <div style={{ height: '100%', paddingTop: 54, display: 'flex', flexDirection: 'column' }}>
        {children}
      </div>
    </div>
  );
}

function StageDetailScreen() {
  const [tab, setTab] = useState('participants');
  const [tabStyle, setTabStyle] = useState(window.__TWEAKS.tabStyle);
  const [visual, setVisual] = useState(window.__TWEAKS.timelineVisual);
  const [density, setDensity] = useState(window.__TWEAKS.rowDensity);
  const [sheetRound, setSheetRound] = useState(null);

  useEffect(() => {
    const handler = (e) => {
      const d = e.detail || {};
      if (d.tabStyle !== undefined) setTabStyle(d.tabStyle);
      if (d.timelineVisual !== undefined) setVisual(d.timelineVisual);
      if (d.rowDensity !== undefined) setDensity(d.rowDensity);
    };
    window.addEventListener('tweaks-change', handler);
    return () => window.removeEventListener('tweaks-change', handler);
  }, []);

  return (
    <PhoneShell>
      {/* 헤더 — 뒤로가기만 */}
      <div style={{ flexShrink: 0, background: '#fff',
        padding: '4px 8px 8px', display: 'flex', alignItems: 'center' }}>
        <button style={{
          width: 40, height: 40, borderRadius: 8, border: 'none',
          background: 'transparent', display: 'flex', alignItems: 'center',
          justifyContent: 'center', cursor: 'pointer', padding: 0,
        }}>
          <Icon name="chevron-left" size={24} color="var(--fg1)" strokeWidth={2}/>
        </button>
      </div>
      {/* 스크롤 본문 */}
      <div style={{ flex: 1, overflowY: 'auto', background: 'var(--gray-50)' }}>
        <div style={{ background: '#fff', paddingBottom: 4 }}>
          <StageSummaryCard/>
        </div>
        <StageDetailTabs active={tab} onChange={setTab} style={tabStyle}/>
        {tab === 'participants' && <ParticipantsTab visual={visual} density={density}
          onTapPlan={(p) => setSheetRound(p.idx)}/>}
        {tab === 'rate' && <EmptyTabContent label="이율 내역"/>}
        {tab === 'progress' && <EmptyTabContent label="진행 내역"/>}
        {tab === 'chat' && <EmptyTabContent label="채팅"/>}
      </div>
      <JoinSimSheet open={sheetRound !== null} onClose={() => setSheetRound(null)}
        totalRounds={13} monthly={105120} initialRound={sheetRound || 4}/>
    </PhoneShell>
  );
}

function App() {
  return (
    <div className="stage">
      <div className="phone-wrap">
        <StageDetailScreen/>
        <div className="phone-label">아임인 · 스테이지 상세 (참여자 탭)</div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);