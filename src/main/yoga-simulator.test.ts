import { describe, it, expect } from 'vitest';
import { simulateLayout, type BlueprintNode } from './yoga-simulator';

describe('simulateLayout', () => {
  it('VERTICAL 레이아웃: FILL 자식의 width = 부모width - padding*2', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', paddingTop: 20, paddingBottom: 20, paddingLeft: 16, paddingRight: 16, itemSpacing: 12 },
      children: [
        { name: 'Section1', type: 'frame', height: 100, layoutSizingHorizontal: 'FILL' },
        { name: 'Section2', type: 'frame', height: 200, layoutSizingHorizontal: 'FILL' },
      ],
    };
    const result = await simulateLayout(bp);
    expect(result.layout.rootWidth).toBe(393);
    const s1 = result.nodes.find(n => n.name === 'Section1')!;
    expect(s1.width).toBe(361);
    expect(s1.height).toBe(100);
    const s2 = result.nodes.find(n => n.name === 'Section2')!;
    expect(s2.y).toBe(20 + 100 + 12);
    expect(result.issues).toHaveLength(0);
  });

  it('FILL 누락 FRAME → FILL_REQUIRED 이슈 탐지', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL' },
      children: [{ name: 'BadSection', type: 'frame', height: 100 }],
    };
    const result = await simulateLayout(bp);
    const fillIssues = result.issues.filter(i => i.type === 'FILL_REQUIRED');
    expect(fillIssues.length).toBeGreaterThan(0);
    expect(fillIssues[0].fix?.to).toBe('FILL');
  });

  it('자동 수정된 fixedBlueprint 반환', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL' },
      children: [{ name: 'Section', type: 'frame', height: 100 }],
    };
    const result = await simulateLayout(bp);
    expect(result.fixedBlueprint).not.toBeNull();
    expect(result.fixedBlueprint!.children![0].layoutSizingHorizontal).toBe('FILL');
  });

  it('이슈 없으면 fixedBlueprint는 null', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL' },
      children: [{ name: 'Section', type: 'frame', height: 100, layoutSizingHorizontal: 'FILL' }],
    };
    const result = await simulateLayout(bp);
    expect(result.fixedBlueprint).toBeNull();
  });

  it('Tab Bar/FAB 위치 사전 계산', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', itemSpacing: 0 },
      children: [
        { name: 'Content', type: 'frame', height: 800, layoutSizingHorizontal: 'FILL' },
        { name: 'FAB', type: 'frame', width: 120, height: 44, layoutPositioning: 'ABSOLUTE' },
        { name: 'Tab Bar', type: 'frame', width: 393, height: 73, layoutPositioning: 'ABSOLUTE' },
      ],
    };
    const result = await simulateLayout(bp);
    expect(result.layout.contentBottom).toBe(800);
    expect(result.layout.suggestedFabY).toBe(824);
    expect(result.layout.suggestedTabBarY).toBe(884);
    expect(result.layout.suggestedRootHeight).toBe(957);
  });

  it('HORIZONTAL 캐로셀 레이아웃', async () => {
    const bp: BlueprintNode = {
      name: 'Carousel', type: 'frame', width: 393, height: 162,
      autoLayout: { layoutMode: 'HORIZONTAL', itemSpacing: 12, paddingLeft: 20, clipsContent: true },
      children: [
        { name: 'Banner1', type: 'frame', width: 353, height: 162 },
        { name: 'Banner2', type: 'frame', width: 353, height: 162 },
      ],
    };
    const result = await simulateLayout(bp);
    const b1 = result.nodes.find(n => n.name === 'Banner1')!;
    const b2 = result.nodes.find(n => n.name === 'Banner2')!;
    expect(b1.x).toBe(20);
    expect(b2.x).toBe(20 + 353 + 12);
  });

  it('SPACE_BETWEEN 마지막 HUG 자식은 FILL_REQUIRED 미탐지', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', primaryAxisAlignItems: 'SPACE_BETWEEN' },
      children: [
        { name: 'Main', type: 'frame', height: 100 },
        { name: 'Trailing', type: 'frame', height: 40 },
      ],
    };
    const result = await simulateLayout(bp);
    const trailingIssue = result.issues.find(i => i.name === 'Trailing');
    expect(trailingIssue).toBeUndefined();
  });

  it('50 노드 레이아웃: 50ms 이내', async () => {
    const children = Array.from({ length: 50 }, (_, i) => ({
      name: `Item${i}`, type: 'frame' as const, height: 56, layoutSizingHorizontal: 'FILL' as const,
    }));
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', itemSpacing: 0 },
      children,
    };
    const result = await simulateLayout(bp);
    expect(result.elapsed_ms).toBeLessThan(50);
  });
});
