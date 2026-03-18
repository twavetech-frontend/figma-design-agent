/**
 * Yoga 시뮬레이터 CLI — 독립 실행 (서버 불필요)
 *
 * Usage:
 *   node out/yoga-cli/index.js < blueprint.json
 *   node out/yoga-cli/index.js path/to/blueprint.json
 *
 * stdin 또는 파일 경로로 Blueprint JSON을 받아서
 * Yoga 레이아웃 시뮬레이션 결과를 stdout JSON으로 출력.
 */

import { simulateLayout } from './main/yoga-simulator';
import { readFileSync } from 'fs';

async function main() {
  let input: string;

  if (process.argv[2]) {
    // 파일 경로 인자
    input = readFileSync(process.argv[2], 'utf-8');
  } else {
    // stdin
    const chunks: Buffer[] = [];
    for await (const chunk of process.stdin) {
      chunks.push(chunk);
    }
    input = Buffer.concat(chunks).toString('utf-8');
  }

  const blueprint = JSON.parse(input);
  const result = await simulateLayout(blueprint);

  // stdout에 JSON 출력
  process.stdout.write(JSON.stringify({
    issues_count: result.issues.length,
    issues: result.issues,
    layout: result.layout,
    fixedBlueprint: result.fixedBlueprint,
    elapsed_ms: result.elapsed_ms,
    node_count: result.nodes.length,
  }));
}

main().catch(err => {
  process.stderr.write(`Error: ${err.message}\n`);
  process.exit(1);
});
