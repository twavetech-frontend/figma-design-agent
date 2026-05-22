import React, { useState, useEffect } from 'react';
import type { FigmaConnectionState, ClaudeCodeStatus } from '../../shared/types';

interface Props {
  figmaStatus?: FigmaConnectionState;
}

type ClaudeMode = 'loading' | 'code-connected' | 'code-not-auth' | 'code-not-installed' | 'api-connected' | 'api-input';

export function SettingsPanel({ figmaStatus }: Props) {
  const [open, setOpen] = useState(false);

  // Claude state
  const [claudeMode, setClaudeMode] = useState<ClaudeMode>('loading');
  const [claudeCodeStatus, setClaudeCodeStatus] = useState<ClaudeCodeStatus | null>(null);
  const [claudeApiMaskedKey, setClaudeApiMaskedKey] = useState('');
  const [claudeKeyInput, setClaudeKeyInput] = useState('');
  const [claudeError, setClaudeError] = useState('');
  const [claudeLoading, setClaudeLoading] = useState(false);

  useEffect(() => {
    if (!open) return;

    // Check Claude Code status first
    window.electronAPI?.getClaudeCodeStatus().then((status) => {
      setClaudeCodeStatus(status);

      if (status.installed && status.authenticated) {
        setClaudeMode('code-connected');
      } else if (status.installed && !status.authenticated) {
        setClaudeMode('code-not-auth');
      } else {
        // Claude Code not installed — check API key fallback
        window.electronAPI?.getClaudeApiStatus().then((res) => {
          if (res.hasKey) {
            setClaudeMode('api-connected');
            setClaudeApiMaskedKey(res.maskedKey);
          } else {
            setClaudeMode('code-not-installed');
          }
        });
      }
    });
  }, [open]);

  const handleClaudeLogin = async () => {
    setClaudeLoading(true);
    setClaudeError('');
    try {
      const result = await window.electronAPI?.claudeCodeLogin();
      if (result?.success) {
        setClaudeMode('code-connected');
        const status = await window.electronAPI?.getClaudeCodeStatus();
        if (status) setClaudeCodeStatus(status);
      } else {
        setClaudeError(result?.error || 'Login failed');
      }
    } catch (err) {
      setClaudeError(String(err));
    } finally {
      setClaudeLoading(false);
    }
  };

  const handleShowApiKeyInput = () => {
    setClaudeMode('api-input');
    setClaudeError('');
  };

  const handleClaudeKeySubmit = async () => {
    const key = claudeKeyInput.trim();
    if (!key) return;
    setClaudeLoading(true);
    setClaudeError('');

    try {
      const validation = await window.electronAPI?.validateClaudeApiKey(key);
      if (!validation?.valid) {
        setClaudeError(validation?.error || 'Invalid API key');
        setClaudeLoading(false);
        return;
      }

      const result = await window.electronAPI?.setClaudeApiKey(key);
      if (result?.success) {
        setClaudeMode('api-connected');
        setClaudeApiMaskedKey(key.slice(0, 8) + '...' + key.slice(-4));
        setClaudeKeyInput('');
      } else {
        setClaudeError(result?.error || 'Failed to save');
      }
    } catch (err) {
      setClaudeError(String(err));
    } finally {
      setClaudeLoading(false);
    }
  };

  const figmaConnected = figmaStatus?.status === 'connected';
  const figmaConnecting = figmaStatus?.status === 'connecting';

  // Determine Claude card display
  const isClaudeConnected = claudeMode === 'code-connected' || claudeMode === 'api-connected';
  const claudeBorderColor = isClaudeConnected ? '#1a472a' : claudeLoading ? '#3d3520' : '#471a1a';
  const claudeDotColor = isClaudeConnected ? '#22c55e' : claudeLoading ? '#fbbf24' : '#ef4444';
  const claudeIconColor = isClaudeConnected ? '#d4a574' : '#666';

  let claudeStatusText = '';
  switch (claudeMode) {
    case 'loading': claudeStatusText = 'Checking...'; break;
    case 'code-connected': claudeStatusText = `Claude Code: Connected${claudeCodeStatus?.plan ? ` (${claudeCodeStatus.plan})` : ''}`; break;
    case 'code-not-auth': claudeStatusText = 'Claude Code: Not logged in'; break;
    case 'code-not-installed': claudeStatusText = 'Claude Code not installed'; break;
    case 'api-connected': claudeStatusText = `API key: ${claudeApiMaskedKey}`; break;
    case 'api-input': claudeStatusText = 'Enter API key below'; break;
  }

  return (
    <div style={styles.container}>
      <button
        style={styles.gearButton}
        onClick={() => setOpen(!open)}
        title="Settings"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path
            d="M6.5 1L6.1 2.8C5.7 3 5.3 3.2 5 3.4L3.2 2.8L1.7 5.4L3.1 6.7C3 7 3 7.2 3 7.5C3 7.8 3 8 3.1 8.3L1.7 9.6L3.2 12.2L5 11.6C5.3 11.8 5.7 12 6.1 12.2L6.5 14H9.5L9.9 12.2C10.3 12 10.7 11.8 11 11.6L12.8 12.2L14.3 9.6L12.9 8.3C13 8 13 7.8 13 7.5C13 7.2 13 7 12.9 6.7L14.3 5.4L12.8 2.8L11 3.4C10.7 3.2 10.3 3 9.9 2.8L9.5 1H6.5ZM8 5.5C9.1 5.5 10 6.4 10 7.5C10 8.6 9.1 9.5 8 9.5C6.9 9.5 6 8.6 6 7.5C6 6.4 6.9 5.5 8 5.5Z"
            fill="#999"
          />
        </svg>
      </button>

      {open && (
        <>
          <div style={styles.backdrop} onClick={() => setOpen(false)} />

          <div style={styles.panel}>
            {/* Header */}
            <div style={styles.panelHeader}>
              <span style={styles.panelTitle}>Setup Agents & API</span>
              <button style={styles.closeButton} onClick={() => setOpen(false)}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 3L11 11M11 3L3 11" stroke="#999" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>

            {/* Section: AI Agents */}
            <div style={styles.sectionLabel}>AI Agents</div>

            {/* Claude Card */}
            <div
              style={{
                ...styles.card,
                borderColor: claudeBorderColor,
              }}
            >
              <div style={styles.cardIcon}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" fill={claudeIconColor} />
                  <path d="M2 17L12 22L22 17" stroke={claudeIconColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 12L12 17L22 12" stroke={claudeIconColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div style={styles.cardContent}>
                <div style={styles.cardName}>Anthropic Claude</div>
                <div style={styles.cardStatus}>
                  <span style={{
                    ...styles.statusDot,
                    background: claudeDotColor,
                  }} />
                  {claudeStatusText}
                </div>
              </div>
            </div>

            {/* Claude Code: Not logged in */}
            {claudeMode === 'code-not-auth' && (
              <div style={styles.inputSection}>
                <button
                  style={{ ...styles.saveButton, width: '100%', padding: '8px 14px' }}
                  onClick={handleClaudeLogin}
                  disabled={claudeLoading}
                >
                  {claudeLoading ? 'Logging in...' : 'Login with Claude'}
                </button>
                {claudeError && (
                  <div style={{ fontSize: '11px', marginTop: '4px', color: '#ef4444' }}>
                    {claudeError}
                  </div>
                )}
              </div>
            )}

            {/* Claude Code: Not installed */}
            {claudeMode === 'code-not-installed' && (
              <div style={styles.inputSection}>
                <div style={{ fontSize: '11px', color: '#888', marginBottom: '8px' }}>
                  Claude Code를 설치하면 구독 인증으로 사용할 수 있습니다:
                </div>
                <div style={{
                  fontSize: '11px', color: '#d4a574', background: '#1a1a1a',
                  padding: '6px 8px', borderRadius: '4px', fontFamily: 'monospace',
                  marginBottom: '8px',
                }}>
                  npm i -g @anthropic-ai/claude-code
                </div>
                <button
                  style={{ ...styles.saveButton, width: '100%', padding: '6px 14px', background: '#333', fontSize: '11px' }}
                  onClick={handleShowApiKeyInput}
                >
                  Or use API key instead
                </button>
              </div>
            )}

            {/* API key input mode */}
            {claudeMode === 'api-input' && (
              <div style={styles.inputSection}>
                <div style={{ fontSize: '11px', color: '#888', marginBottom: '6px' }}>
                  Get your key from console.anthropic.com
                </div>
                <div style={styles.inputRow}>
                  <input
                    style={styles.input}
                    type="password"
                    value={claudeKeyInput}
                    onChange={(e) => setClaudeKeyInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleClaudeKeySubmit()}
                    placeholder="sk-ant-..."
                    autoFocus
                    disabled={claudeLoading}
                  />
                  <button
                    style={styles.saveButton}
                    onClick={handleClaudeKeySubmit}
                    disabled={!claudeKeyInput.trim() || claudeLoading}
                  >
                    {claudeLoading ? '...' : 'Connect'}
                  </button>
                </div>
                {claudeError && (
                  <div style={{ fontSize: '11px', marginTop: '4px', color: '#ef4444' }}>
                    {claudeError}
                  </div>
                )}
              </div>
            )}

            {/* Section: Connections */}
            <div style={{ ...styles.sectionLabel, marginTop: '16px' }}>Connections</div>

            {/* Figma Card */}
            <div style={{
              ...styles.card,
              borderColor: figmaConnected ? '#1a472a' : figmaConnecting ? '#3d3520' : '#333',
            }}>
              <div style={styles.cardIcon}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M5 5.5A3.5 3.5 0 0 1 8.5 2H12v7H8.5A3.5 3.5 0 0 1 5 5.5z" fill={figmaConnected ? '#F24E1E' : '#666'}/>
                  <path d="M12 2h3.5a3.5 3.5 0 1 1 0 7H12V2z" fill={figmaConnected ? '#FF7262' : '#666'}/>
                  <path d="M12 12.5a3.5 3.5 0 1 1 7 0 3.5 3.5 0 1 1-7 0z" fill={figmaConnected ? '#1ABCFE' : '#666'}/>
                  <path d="M5 19.5A3.5 3.5 0 0 1 8.5 16H12v3.5a3.5 3.5 0 1 1-7 0z" fill={figmaConnected ? '#0ACF83' : '#666'}/>
                  <path d="M5 12.5A3.5 3.5 0 0 1 8.5 9H12v7H8.5A3.5 3.5 0 0 1 5 12.5z" fill={figmaConnected ? '#A259FF' : '#666'}/>
                </svg>
              </div>
              <div style={styles.cardContent}>
                <div style={styles.cardName}>Figma Plugin</div>
                <div style={styles.cardStatus}>
                  <span style={{
                    ...styles.statusDot,
                    background: figmaConnected ? '#22c55e' : figmaConnecting ? '#fbbf24' : '#ef4444',
                  }} />
                  {figmaConnected
                    ? `Connected — ${figmaStatus?.documentName || figmaStatus?.channel || 'active'}`
                    : figmaConnecting
                      ? 'Connecting...'
                      : 'Disconnected — run plugin in Figma'}
                </div>
              </div>
            </div>

            <div style={styles.hint}>
              WS server running on port 8767
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: 'relative' as const,
  },
  gearButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '28px',
    height: '28px',
    borderRadius: '6px',
    border: '1px solid #333',
    background: '#1e1e1e',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  backdrop: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 99,
  },
  panel: {
    position: 'absolute' as const,
    top: '100%',
    right: 0,
    marginTop: '4px',
    padding: '16px',
    borderRadius: '12px',
    border: '1px solid #333',
    background: '#1a1a1a',
    boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
    zIndex: 100,
    width: '340px',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '16px',
  },
  panelTitle: {
    fontSize: '14px',
    fontWeight: 700,
    color: '#fff',
  },
  closeButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '24px',
    height: '24px',
    borderRadius: '6px',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
  },
  sectionLabel: {
    fontSize: '11px',
    fontWeight: 600,
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
    marginBottom: '8px',
  },
  card: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 12px',
    borderRadius: '8px',
    border: '1px solid #333',
    background: '#222',
    marginBottom: '6px',
    transition: 'border-color 0.15s, background 0.15s',
  },
  cardIcon: {
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '32px',
    height: '32px',
    borderRadius: '8px',
    background: '#2a2a2a',
  },
  cardContent: {
    flex: 1,
    minWidth: 0,
  },
  cardName: {
    fontSize: '13px',
    fontWeight: 600,
    color: '#e0e0e0',
    marginBottom: '2px',
  },
  cardStatus: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '11px',
    color: '#999',
  },
  statusDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  inputSection: {
    marginTop: '4px',
    marginBottom: '4px',
  },
  inputLabel: {
    fontSize: '11px',
    color: '#666',
    display: 'block',
    marginBottom: '4px',
  },
  inputRow: {
    display: 'flex',
    gap: '4px',
  },
  input: {
    flex: 1,
    padding: '5px 8px',
    borderRadius: '6px',
    border: '1px solid #444',
    background: '#111',
    color: '#e0e0e0',
    fontSize: '12px',
    outline: 'none',
  },
  saveButton: {
    padding: '5px 14px',
    borderRadius: '6px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    fontSize: '12px',
    cursor: 'pointer',
    fontWeight: 500,
  },
  hint: {
    fontSize: '10px',
    color: '#555',
    marginTop: '8px',
    textAlign: 'center' as const,
  },
};
