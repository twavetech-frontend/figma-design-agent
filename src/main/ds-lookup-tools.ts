/**
 * DS Lookup Tools — Local file-based design system lookups
 *
 * These tools don't need Figma plugin connection.
 * They read from local DS files directly.
 *
 * All lookups are merged into a single batch_ds_lookup tool
 * to avoid multiple Claude API round-trips.
 */

import { getIcons, getVariants, getDesignTokens, getTokenMap, getComponentDocs } from '../shared/ds-data';
import type { ToolDefinition } from '../shared/types';

/**
 * Register DS Lookup tools into the tool registry
 */
export function registerDSLookupTools(tools: Map<string, ToolDefinition>): void {
  tools.set('batch_ds_lookup', {
    name: 'batch_ds_lookup',
    description: `Batch lookup for DS components, icons, tokens, and text styles in a SINGLE call.
⚠️ batch_build_screen already resolves component/icon names automatically — this tool is usually UNNECESSARY.
Only use when you need to explore what components/icons/tokens are available BEFORE building.
Pass multiple queries across all categories at once to avoid repeated calls.`,
    inputSchema: {
      type: 'object',
      properties: {
        components: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              query: { type: 'string', description: 'Component name (e.g. "Button", "Input")' },
              variantFilter: { type: 'string', description: 'Optional variant filter (e.g. "Size=md")' },
            },
            required: ['query'],
          },
          description: 'Component variant lookups',
        },
        icons: {
          type: 'array',
          items: { type: 'string' },
          description: 'Icon name queries (e.g. ["arrow", "check", "bell"])',
        },
        tokens: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              query: { type: 'string', description: 'Token name (e.g. "bg-primary")' },
              category: { type: 'string', enum: ['colors', 'spacing', 'radius', 'typography', 'layout', 'width'] },
            },
            required: ['query'],
          },
          description: 'Design token lookups',
        },
        textStyles: {
          type: 'array',
          items: { type: 'string' },
          description: 'Text/effect style name queries (e.g. ["Text sm", "Heading"])',
        },
      },
    },
    handler: async (params) => {
      const result: Record<string, unknown> = {};

      // Components
      const componentQueries = params.components as Array<{ query: string; variantFilter?: string }> | undefined;
      if (componentQueries?.length) {
        const variants = getVariants();
        result.components = componentQueries.map(({ query, variantFilter }) => {
          const q = query.toLowerCase();
          const matches = variants.filter((v) => v.name.toLowerCase().includes(q)).slice(0, 5);
          return matches.map((m) => {
            let filteredVariants = m.variants;
            if (variantFilter) {
              const fl = variantFilter.toLowerCase();
              const filtered: Record<string, string> = {};
              for (const [key, val] of Object.entries(m.variants)) {
                if (key.toLowerCase().includes(fl)) filtered[key] = val;
              }
              filteredVariants = filtered;
            }
            return {
              name: m.name,
              setKey: m.setKey,
              variantCount: Object.keys(filteredVariants).length,
              variants: filteredVariants,
            };
          });
        });
      }

      // Icons
      const iconQueries = params.icons as string[] | undefined;
      if (iconQueries?.length) {
        const icons = getIcons();
        result.icons = iconQueries.map((query) => {
          const q = query.toLowerCase();
          const matches: Array<{ name: string; componentId: string }> = [];
          for (const [name, componentId] of Object.entries(icons)) {
            if (name.toLowerCase().includes(q)) {
              matches.push({ name, componentId });
              if (matches.length >= 10) break;
            }
          }
          return { query, matches };
        });
      }

      // Tokens (searchable by Figma path or CSS variable name)
      const tokenQueries = params.tokens as Array<{ query: string; category?: string }> | undefined;
      if (tokenQueries?.length) {
        const tokens = getDesignTokens();
        const tokenMap = getTokenMap();
        result.tokens = tokenQueries.map(({ query, category }) => {
          const q = query.toLowerCase();
          const matches: Array<{ token: string; value: string; category: string; cssVar?: string }> = [];

          // Search by CSS variable name in TOKEN_MAP.json
          if (q.startsWith('--') && Object.keys(tokenMap).length > 0) {
            for (const [cssVar, entry] of Object.entries(tokenMap)) {
              if (cssVar.toLowerCase().includes(q)) {
                matches.push({
                  token: entry.figmaPath,
                  value: entry.value,
                  category: entry.type?.toLowerCase() || 'unknown',
                  cssVar,
                });
                if (matches.length >= 20) break;
              }
            }
          }

          // Search by Figma path in DESIGN_TOKENS.md
          const categories = category
            ? { [category]: tokens[category as keyof typeof tokens] }
            : tokens;
          for (const [cat, items] of Object.entries(categories)) {
            if (cat === 'textStyles' || cat === 'effects') continue;
            if (!Array.isArray(items)) continue;
            for (const item of items) {
              if ('token' in item) {
                const t = item as { token: string; value: string; cssVar?: string };
                if (t.token.toLowerCase().includes(q) || (t.cssVar && t.cssVar.toLowerCase().includes(q))) {
                  matches.push({
                    token: t.token,
                    value: t.value,
                    category: cat,
                    cssVar: t.cssVar,
                  });
                  if (matches.length >= 20) break;
                }
              }
            }
            if (matches.length >= 20) break;
          }
          return { query, matches };
        });
      }

      // Text/Effect styles
      const styleQueries = params.textStyles as string[] | undefined;
      if (styleQueries?.length) {
        const tokens = getDesignTokens();
        result.textStyles = styleQueries.map((query) => {
          const q = query.toLowerCase();
          return {
            query,
            textStyles: tokens.textStyles.filter((s) => s.name.toLowerCase().includes(q)),
            effects: tokens.effects.filter((s) => s.name.toLowerCase().includes(q)),
          };
        });
      }

      return result;
    },
  });

  // ─── Component Docs Lookup ────────────────────────────────────────

  tools.set('lookup_component_docs', {
    name: 'lookup_component_docs',
    description: `Look up detailed DS component documentation from design-system-docs.
Returns description, Figma component name, variants, props, and usage guidelines.
Use this when you need to know which variants/props a DS component supports before creating instances.`,
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Component name to search (e.g. "Toggle", "Button", "Badge", "Input")',
        },
        category: {
          type: 'string',
          enum: ['components', 'foundation', 'all'],
          description: 'Category to search in (default: all)',
        },
      },
      required: ['query'],
    },
    handler: async (params) => {
      const docs = getComponentDocs();
      if (!docs) {
        return { error: 'DS_COMPONENT_DOCS.json not found. Run the docs scraping script first.' };
      }

      const query = (params.query as string).toLowerCase();
      const category = (params.category as string) || 'all';

      const searchIn = category === 'all'
        ? [...(docs.components || []), ...(docs.foundation || [])]
        : category === 'components'
          ? (docs.components || [])
          : (docs.foundation || []);

      const matches = searchIn.filter((c) => {
        if (c.name.toLowerCase().includes(query)) return true;
        const fcn: unknown = c.figmaComponentName;
        if (typeof fcn === 'string') return fcn.toLowerCase().includes(query);
        if (Array.isArray(fcn)) return fcn.some((n: string) => typeof n === 'string' && n.toLowerCase().includes(query));
        return false;
      });

      if (matches.length === 0) {
        return {
          query,
          matches: [],
          available: searchIn.map((c) => c.name),
        };
      }

      return {
        query,
        matches: matches.map((c) => ({
          name: c.name,
          category: c.category,
          figmaComponentName: c.figmaComponentName,
          description: c.description,
          variants: c.variants,
          props: c.props,
          figmaVariants: c.figmaVariants,
          usageGuidelines: c.usageGuidelines,
        })),
      };
    },
  });
}
