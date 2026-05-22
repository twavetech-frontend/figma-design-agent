/**
 * Settings Store — JSON file-based persistence
 *
 * Works in both Electron and standalone Node.js environments.
 * - Electron: uses app.getPath('userData')
 * - Standalone: uses ~/.config/figma-bridge/
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { execSync } from 'child_process';
import { join, dirname } from 'path';
import { homedir } from 'os';

interface SettingsData {
  anthropicApiKey?: string;
}

function getSettingsDir(): string {
  try {
    const { app } = require('electron');
    return app.getPath('userData');
  } catch {
    return join(homedir(), '.config', 'figma-bridge');
  }
}

const settingsPath = join(getSettingsDir(), 'settings.json');

function readSettings(): SettingsData {
  try {
    return JSON.parse(readFileSync(settingsPath, 'utf-8'));
  } catch {
    return {};
  }
}

function writeSettings(data: SettingsData): void {
  mkdirSync(dirname(settingsPath), { recursive: true });
  writeFileSync(settingsPath, JSON.stringify(data, null, 2), 'utf-8');
}

export function getAnthropicApiKey(): string {
  // Prefer saved key, fall back to env var, then try OAuth token from Claude Code
  return readSettings().anthropicApiKey || process.env.ANTHROPIC_API_KEY || getClaudeOAuthToken() || '';
}

/** 직접 API 호출 가능한 키만 반환 (OAuth 토큰 제외) */
export function getDirectApiKey(): string {
  return readSettings().anthropicApiKey || process.env.ANTHROPIC_API_KEY || '';
}

// ============================================================
// Claude Code OAuth Token (macOS Keychain)
// ============================================================

let cachedOAuthToken: string | null = null;
let cachedOAuthExpiresAt: number = 0;

/**
 * Read Claude Code's OAuth access token from macOS Keychain.
 * The token can be used directly as an Anthropic API key.
 * Returns empty string if not available or expired.
 */
export function getClaudeOAuthToken(): string {
  // Return cached token if still valid (with 5 min buffer)
  if (cachedOAuthToken && cachedOAuthExpiresAt > Date.now() + 5 * 60 * 1000) {
    return cachedOAuthToken;
  }

  try {
    const raw = execSync(
      'security find-generic-password -s "Claude Code-credentials" -a "$USER" -w',
      { encoding: 'utf-8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();

    const data = JSON.parse(raw);
    const oauth = data.claudeAiOauth;

    if (!oauth?.accessToken || !oauth?.expiresAt) {
      return '';
    }

    // Check if token is expired
    if (oauth.expiresAt <= Date.now()) {
      console.log('[OAuth] Token expired, Claude Code will refresh it on next CLI use');
      return '';
    }

    cachedOAuthToken = oauth.accessToken;
    cachedOAuthExpiresAt = oauth.expiresAt;

    return oauth.accessToken;
  } catch {
    return '';
  }
}

export function setAnthropicApiKey(key: string): void {
  const data = readSettings();
  data.anthropicApiKey = key;
  writeSettings(data);
  // Also set env so orchestrator picks it up
  process.env.ANTHROPIC_API_KEY = key;
}
