import { describe, it, expect } from 'vitest';
import { getIconSvgFromPackage, resolvePackageIcon, pascalToKebab } from './untitled-icons';

// 2026-09-04 회귀: gift-01/info-circle 이 GitHub 캐시 미존재로 회색 placeholder 가 됐다.
// 번들 npm 패키지에서 네트워크 없이 해석돼야 한다.
describe('untitled-icons offline package resolution', () => {
  it('builds SVG for common icons without network', () => {
    for (const n of ['gift-01', 'info-circle', 'chevron-right', 'x-close', 'bell-01']) {
      const svg = getIconSvgFromPackage(n, 24, '#000000');
      expect(svg, n).toBeTruthy();
      expect(svg).toContain('<path');
      expect(svg).toContain('viewBox="0 0 24 24"');
      expect(svg).toContain('stroke="#000000"');
    }
  });
  it('resolves suffix / snake / alias names', () => {
    expect(resolvePackageIcon('gift')).toBe('gift-01');
    expect(resolvePackageIcon('info_circle')).toBe('info-circle');
    expect(resolvePackageIcon('bell')).toBe('bell-01');
    expect(resolvePackageIcon('definitely-not-an-icon')).toBeNull();
  });
  it('maps Pascal file names to kebab', () => {
    expect(pascalToKebab('Gift01')).toBe('gift-01');
    expect(pascalToKebab('InfoCircle')).toBe('info-circle');
    expect(pascalToKebab('XClose')).toBe('x-close');
    expect(pascalToKebab('ArrowNarrowUp')).toBe('arrow-narrow-up');
  });
});
