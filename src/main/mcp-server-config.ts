/**
 * MCP Server Configuration for Agent SDK
 *
 * Returns HTTP URL config for the embedded Hono MCP server.
 * No subprocess spawn needed — Agent SDK connects via HTTP directly.
 */

const MCP_PORT = 8769;
const MCP_ENDPOINT = '/mcp';

/**
 * Build the mcpServers config for Agent SDK's query() options
 */
export function getMcpServersConfig(): Record<string, { type: 'http'; url: string }> {
  return {
    'figma-tools': {
      type: 'http',
      url: `http://127.0.0.1:${MCP_PORT}${MCP_ENDPOINT}`,
    },
  };
}
