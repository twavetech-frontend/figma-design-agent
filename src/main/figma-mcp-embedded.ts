/**
 * Embedded MCP Tools — Direct function calls, no stdio transport
 *
 * Converts existing 58+ MCP tools into a tool registry that the
 * AgentOrchestrator can call directly. Each tool calls FigmaWSServer.sendCommand()
 * instead of going through MCP protocol.
 */

import { z, ZodObject, ZodRawShape } from 'zod';
import { FigmaWSServer } from './figma-ws-server';
import type { ToolDefinition } from '../shared/types';
import { getIcons, getVariants, syncTokensIfNeeded, type VariantEntry } from '../shared/ds-data';
import { convertPenToFigma, type PenNode } from './pen-to-figma';
import { getIconSvg, getIconSvgAsync, resolveIconFile } from './untitled-icons';
import { simulateLayout } from './yoga-simulator';

// Re-export for convenience
export type { ToolDefinition };

/**
 * Build the complete tool registry from FigmaWSServer
 */
// Track the last agent-built root frame for cleanup on next build
let lastBuiltRootId: string | null = null;

export function buildToolRegistry(figmaWS: FigmaWSServer): Map<string, ToolDefinition> {
  const tools = new Map<string, ToolDefinition>();

  // Helper to register a tool
  function reg(name: string, description: string, schema: Record<string, unknown>, handler: (params: Record<string, unknown>) => Promise<unknown>, options?: { timeoutMs?: number }) {
    tools.set(name, { name, description, inputSchema: schema, handler, timeoutMs: options?.timeoutMs });
  }

  // Helper: send command to Figma plugin
  async function cmd(command: string, params: Record<string, unknown> = {}, timeoutMs?: number) {
    return figmaWS.sendCommand(command, params, timeoutMs);
  }


  // ============================================================
  // Document Tools
  // ============================================================

  reg('join_channel', 'Join a Figma document channel for communication', {
    type: 'object',
    properties: {
      channel: { type: 'string', description: 'Channel name to join' }
    },
    required: ['channel']
  }, async (params) => {
    await figmaWS.joinChannel(params.channel as string);
    return { success: true, channel: params.channel };
  });

  reg('get_document_info', 'Get information about the current Figma document', {
    type: 'object', properties: {}
  }, async () => cmd('get_document_info'));

  reg('get_selection', 'Get the current selection in Figma', {
    type: 'object', properties: {}
  }, async () => cmd('get_selection'));

  reg('get_node_info', 'Get detailed information about a specific node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Node ID to inspect' }
    },
    required: ['nodeId']
  }, async (params) => cmd('get_node_info', params));

  reg('get_nodes_info', 'Get information about multiple nodes', {
    type: 'object',
    properties: {
      nodeIds: { type: 'array', items: { type: 'string' }, description: 'Array of node IDs' }
    },
    required: ['nodeIds']
  }, async (params) => cmd('get_nodes_info', params));

  reg('get_styles', 'Get all styles in the document', {
    type: 'object', properties: {}
  }, async () => cmd('get_styles'));

  reg('get_local_components', 'Get all local components', {
    type: 'object', properties: {}
  }, async () => cmd('get_local_components'));

  reg('get_local_component_sets', 'Get all local component sets (variants)', {
    type: 'object',
    properties: {},
  }, async () => cmd('get_local_component_sets'));

  reg('get_remote_components', 'Get remote/library components', {
    type: 'object', properties: {}
  }, async () => cmd('get_remote_components'));

  reg('get_pages', 'Get all pages in the document', {
    type: 'object', properties: {}
  }, async () => cmd('get_pages'));

  reg('manage_pages', 'Create, rename, or delete pages', {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['create', 'rename', 'delete'] },
      name: { type: 'string' },
      newName: { type: 'string' },
      pageId: { type: 'string' }
    },
    required: ['action']
  }, async (params) => cmd('manage_pages', params));

  reg('scan_text_nodes', 'Scan text nodes in a subtree', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Root node to scan' }
    },
    required: ['nodeId']
  }, async (params) => cmd('scan_text_nodes', params));

  reg('export_node_as_image', 'Export a node as an image', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      format: { type: 'string', enum: ['PNG', 'JPG', 'SVG', 'PDF'] },
      scale: { type: 'number' }
    },
    required: ['nodeId']
  }, async (params) => cmd('export_node_as_image', params));

  // ============================================================
  // Creation Tools
  // ============================================================

  reg('create_rectangle', 'Create a rectangle', {
    type: 'object',
    properties: {
      x: { type: 'number' }, y: { type: 'number' },
      width: { type: 'number' }, height: { type: 'number' },
      name: { type: 'string' }, parentId: { type: 'string' }
    },
    required: ['x', 'y', 'width', 'height']
  }, async (params) => cmd('create_rectangle', params));

  reg('create_frame', 'Create a frame', {
    type: 'object',
    properties: {
      x: { type: 'number' }, y: { type: 'number' },
      width: { type: 'number' }, height: { type: 'number' },
      name: { type: 'string' }, parentId: { type: 'string' }
    },
    required: ['x', 'y', 'width', 'height']
  }, async (params) => cmd('create_frame', params));

  reg('create_text', 'Create a text node', {
    type: 'object',
    properties: {
      x: { type: 'number' }, y: { type: 'number' },
      text: { type: 'string' }, fontSize: { type: 'number' },
      fontWeight: { type: 'number' }, fontColor: { type: 'object' },
      fontName: { type: 'string' }, name: { type: 'string' },
      parentId: { type: 'string' }, width: { type: 'number' },
      textAlignHorizontal: { type: 'string' },
      textAlignVertical: { type: 'string' },
      letterSpacing: { type: 'number' },
      lineHeight: { type: 'number' },
      textAutoResize: { type: 'string' },
      maxLines: { type: 'number' }
    },
    required: ['x', 'y', 'text']
  }, async (params) => {
    // Replace <br> with Unicode Line Separator
    if (typeof params.text === 'string') {
      params = { ...params, text: (params.text as string).replace(/<br>/g, '\u2028') };
    }
    return cmd('create_text', params);
  });

  reg('create_shape', 'Create a polygon or star shape', {
    type: 'object',
    properties: {
      type: { type: 'string', enum: ['POLYGON', 'STAR'] },
      x: { type: 'number' }, y: { type: 'number' },
      width: { type: 'number' }, height: { type: 'number' },
      pointCount: { type: 'number' }, name: { type: 'string' },
      parentId: { type: 'string' }
    },
    required: ['type', 'x', 'y', 'width', 'height']
  }, async (params) => cmd('create_shape', params));

  // ============================================================
  // Modification Tools
  // ============================================================

  reg('move_node', 'Move a node to new coordinates', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, x: { type: 'number' }, y: { type: 'number' }
    },
    required: ['nodeId', 'x', 'y']
  }, async (params) => cmd('move_node', params));

  reg('resize_node', 'Resize a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, width: { type: 'number' }, height: { type: 'number' }
    },
    required: ['nodeId', 'width', 'height']
  }, async (params) => cmd('resize_node', params));

  reg('delete_node', 'Delete a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('delete_node', params));

  reg('set_fill_color', 'Set fill color of a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      r: { type: 'number' }, g: { type: 'number' },
      b: { type: 'number' }, a: { type: 'number' }
    },
    required: ['nodeId', 'r', 'g', 'b']
  }, async (params) => {
    const { nodeId, r, g, b, a, ...rest } = params as Record<string, number | string>;
    return cmd('set_fill_color', { nodeId, color: { r, g, b, a: a ?? 1 }, ...rest });
  });

  reg('set_stroke_color', 'Set stroke color of a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      r: { type: 'number' }, g: { type: 'number' },
      b: { type: 'number' }, a: { type: 'number' },
      strokeWeight: { type: 'number' },
      strokeTopWeight: { type: 'number', description: 'Individual top stroke weight' },
      strokeBottomWeight: { type: 'number', description: 'Individual bottom stroke weight' },
      strokeLeftWeight: { type: 'number', description: 'Individual left stroke weight' },
      strokeRightWeight: { type: 'number', description: 'Individual right stroke weight' }
    },
    required: ['nodeId', 'r', 'g', 'b']
  }, async (params) => {
    const { nodeId, r, g, b, a, strokeWeight, ...rest } = params as Record<string, number | string>;
    return cmd('set_stroke_color', { nodeId, color: { r, g, b, a: a ?? 1 }, strokeWeight: strokeWeight ?? 1, ...rest });
  });

  reg('set_corner_radius', 'Set corner radius', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      radius: { type: 'number' },
      topLeftRadius: { type: 'number' },
      topRightRadius: { type: 'number' },
      bottomLeftRadius: { type: 'number' },
      bottomRightRadius: { type: 'number' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_corner_radius', params));

  reg('set_auto_layout', 'Set auto layout on a frame', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      layoutMode: { type: 'string', enum: ['HORIZONTAL', 'VERTICAL', 'NONE'] },
      itemSpacing: { type: 'number' },
      paddingTop: { type: 'number' }, paddingBottom: { type: 'number' },
      paddingLeft: { type: 'number' }, paddingRight: { type: 'number' },
      primaryAxisAlignItems: { type: 'string' },
      counterAxisAlignItems: { type: 'string' },
      layoutWrap: { type: 'string' },
      clipsContent: { type: 'boolean', description: 'Clip content that overflows the frame' }
    },
    required: ['nodeId', 'layoutMode']
  }, async (params) => cmd('set_auto_layout', params));

  reg('set_effects', 'Set effects (shadow, blur) on a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      effects: { type: 'array' }
    },
    required: ['nodeId', 'effects']
  }, async (params) => cmd('set_effects', params));

  reg('set_effect_style_id', 'Set effect style ID on a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      styleId: { type: 'string' }
    },
    required: ['nodeId', 'styleId']
  }, async (params) => cmd('set_effect_style_id', params));

  reg('set_layout_sizing', 'Set layout sizing mode', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      horizontal: { type: 'string', enum: ['FIXED', 'HUG', 'FILL'] },
      vertical: { type: 'string', enum: ['FIXED', 'HUG', 'FILL'] }
    },
    required: ['nodeId']
  }, async (params) => {
    const normalized = { ...params } as Record<string, unknown>;
    if (params.horizontal) normalized.layoutSizingHorizontal = params.horizontal;
    if (params.vertical) normalized.layoutSizingVertical = params.vertical;
    return cmd('set_layout_sizing', normalized);
  });

  reg('set_layout_positioning', 'Set layout positioning (AUTO or ABSOLUTE) on a node within an auto-layout parent', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Node ID' },
      layoutPositioning: { type: 'string', enum: ['AUTO', 'ABSOLUTE'], description: 'Positioning mode' },
      constraints: {
        type: 'object',
        properties: {
          horizontal: { type: 'string', enum: ['MIN', 'CENTER', 'MAX', 'STRETCH', 'SCALE'] },
          vertical: { type: 'string', enum: ['MIN', 'CENTER', 'MAX', 'STRETCH', 'SCALE'] }
        },
        description: 'Constraints for absolute positioning'
      }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_layout_positioning', params));

  reg('rename_node', 'Rename a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, name: { type: 'string' }
    },
    required: ['nodeId', 'name']
  }, async (params) => cmd('rename_node', params));

  reg('set_selection_colors', 'Set colors on selection or node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      fillColor: { type: 'object' },
      strokeColor: { type: 'object' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_selection_colors', params));

  // ============================================================
  // Text Tools
  // ============================================================

  reg('set_text_content', 'Set text content of a text node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, text: { type: 'string' }
    },
    required: ['nodeId', 'text']
  }, async (params) => {
    if (typeof params.text === 'string') {
      params = { ...params, text: (params.text as string).replace(/<br>/g, '\u2028') };
    }
    return cmd('set_text_content', params);
  });

  reg('set_text_properties', 'Set text properties', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      fontSize: { type: 'number' },
      fontWeight: { type: 'number' },
      fontName: { type: 'string' },
      letterSpacing: { type: 'number' },
      lineHeight: { type: 'number' },
      textAlignHorizontal: { type: 'string' },
      textAlignVertical: { type: 'string' },
      textAutoResize: { type: 'string' },
      maxLines: { type: 'number' },
      fontColor: { type: 'object' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_text_properties', params));

  reg('set_font_size', 'Set font size', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, fontSize: { type: 'number' } },
    required: ['nodeId', 'fontSize']
  }, async (params) => cmd('set_font_size', params));

  reg('set_font_weight', 'Set font weight', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, fontWeight: { type: 'number' } },
    required: ['nodeId', 'fontWeight']
  }, async (params) => cmd('set_font_weight', params));

  reg('set_font_name', 'Set font family', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, fontName: { type: 'string' } },
    required: ['nodeId', 'fontName']
  }, async (params) => cmd('set_font_name', params));

  reg('set_letter_spacing', 'Set letter spacing', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, letterSpacing: { type: 'number' } },
    required: ['nodeId', 'letterSpacing']
  }, async (params) => cmd('set_letter_spacing', params));

  reg('set_line_height', 'Set line height', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, lineHeight: { type: 'number' } },
    required: ['nodeId', 'lineHeight']
  }, async (params) => cmd('set_line_height', params));

  reg('set_paragraph_spacing', 'Set paragraph spacing', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, paragraphSpacing: { type: 'number' } },
    required: ['nodeId', 'paragraphSpacing']
  }, async (params) => cmd('set_paragraph_spacing', params));

  reg('set_text_case', 'Set text case', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, textCase: { type: 'string' } },
    required: ['nodeId', 'textCase']
  }, async (params) => cmd('set_text_case', params));

  reg('set_text_decoration', 'Set text decoration', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, textDecoration: { type: 'string' } },
    required: ['nodeId', 'textDecoration']
  }, async (params) => cmd('set_text_decoration', params));

  reg('set_text_align', 'Set text alignment', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      textAlignHorizontal: { type: 'string' },
      textAlignVertical: { type: 'string' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_text_align', params));

  reg('set_text_style_id', 'Apply a text style by ID', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, styleId: { type: 'string' } },
    required: ['nodeId', 'styleId']
  }, async (params) => cmd('set_text_style_id', params));

  reg('get_styled_text_segments', 'Get styled text segments', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('get_styled_text_segments', params));

  reg('load_font_async', 'Preload a font for use', {
    type: 'object',
    properties: { family: { type: 'string' }, style: { type: 'string' } },
    required: ['family']
  }, async (params) => cmd('load_font_async', params));

  reg('set_multiple_text_contents', 'Set text content on multiple nodes', {
    type: 'object',
    properties: {
      entries: { type: 'array', items: { type: 'object' } }
    },
    required: ['entries']
  }, async (params) => cmd('set_multiple_text_contents', params));

  // ============================================================
  // Component Tools
  // ============================================================

  reg('clone_node', 'Clone a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('clone_node', params));

  reg('group_nodes', 'Group nodes together', {
    type: 'object',
    properties: {
      nodeIds: { type: 'array', items: { type: 'string' } },
      name: { type: 'string' }
    },
    required: ['nodeIds']
  }, async (params) => cmd('group_nodes', params));

  reg('ungroup_nodes', 'Ungroup a group node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('ungroup_nodes', params));

  reg('flatten_node', 'Flatten a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('flatten_node', params));

  reg('insert_child', 'Insert a node as child of another', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, parentId: { type: 'string' },
      index: { type: 'number' }
    },
    required: ['nodeId', 'parentId']
  }, async (params) => cmd('insert_child', params));

  reg('create_component_instance', 'Create an instance of a component', {
    type: 'object',
    properties: {
      componentKey: { type: 'string' }, x: { type: 'number' }, y: { type: 'number' },
      parentId: { type: 'string' }
    },
    required: ['componentKey', 'x', 'y']
  }, async (params) => cmd('create_component_instance', params));

  reg('get_instance_properties', 'Get properties of a component instance', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('get_instance_properties', params));

  reg('set_instance_properties', 'Set properties on a component instance', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      properties: { type: 'object' }
    },
    required: ['nodeId', 'properties']
  }, async (params) => cmd('set_instance_properties', params));

  reg('create_component_from_node', 'Convert a node to a component', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('create_component_from_node', params));

  reg('scan_instances_for_swap', 'Scan component instances for swap targets', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('scan_instances_for_swap', params));

  // ============================================================
  // Variable & Binding Tools
  // ============================================================

  reg('get_local_variables', 'Get local variables from document', {
    type: 'object',
    properties: { includeLibrary: { type: 'boolean' } },
  }, async (params) => cmd('get_local_variables', params));

  reg('get_bound_variables', 'Get bound variables on a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('get_bound_variables', params));

  reg('set_bound_variables', 'Bind variables to a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      bindings: { type: 'object' }
    },
    required: ['nodeId', 'bindings']
  }, async (params) => cmd('set_bound_variables', params));

  reg('set_image_fill', 'Set image fill on a node. imageData must be base64-encoded PNG/JPEG. URL is NOT supported.', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Target node ID' },
      imageData: { type: 'string', description: 'Base64-encoded image data (PNG or JPEG). Required.' },
      scaleMode: { type: 'string', description: 'FILL, FIT, CROP, or TILE' }
    },
    required: ['nodeId', 'imageData']
  }, async (params) => cmd('set_image_fill', params));

  // ============================================================
  // Batch Tools
  // ============================================================

  reg('batch_execute', 'Execute multiple Figma commands in one call', {
    type: 'object',
    properties: {
      operations: { type: 'array', items: { type: 'object' } }
    },
    required: ['operations']
  }, async (params) => {
    // Same logic as existing batch_execute
    const operations = params.operations as Array<{
      op: string; id?: string; parentRef?: string; params: Record<string, unknown>;
    }>;
    const refMap: Record<string, string> = {};
    const results: unknown[] = [];

    for (const operation of operations) {
      try {
        const resolvedParams = { ...operation.params };

        if (operation.parentRef) {
          const resolved = refMap[operation.parentRef];
          if (!resolved) throw new Error(`Unresolved parentRef: ${operation.parentRef}`);
          resolvedParams.parentId = resolved;
        }

        for (const [key, value] of Object.entries(resolvedParams)) {
          if (typeof value === 'string' && value.startsWith('$') && refMap[value]) {
            resolvedParams[key] = refMap[value];
          }
        }

        const normalized = normalizeParams(operation.op, resolvedParams as Record<string, unknown>);
        const result = await cmd(operation.op, normalized);
        const figmaId = extractId(result);

        if (operation.id && figmaId) {
          refMap[operation.id] = figmaId;
        }

        results.push({ op: operation.op, success: true, id: operation.id, figmaId });
      } catch (error) {
        results.push({
          op: operation.op, success: false,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }
    return { results, refMap };
  });

  reg('simulate_layout',
    'Simulate Blueprint layout using Yoga WASM. Returns detected issues, pre-computed Tab Bar/FAB positions, and auto-fixed Blueprint. Call BEFORE batch_build_screen.',
    {
      type: 'object',
      properties: {
        blueprint: { type: 'object', description: 'Blueprint JSON (same format as batch_build_screen)' },
      },
      required: ['blueprint'],
    },
    async (params) => {
      const result = await simulateLayout(params.blueprint as any);
      return {
        issues_count: result.issues.length,
        issues: result.issues,
        layout: result.layout,
        fixedBlueprint: result.fixedBlueprint,
        elapsed_ms: result.elapsed_ms,
        node_count: result.nodes.length,
      };
    }
  );

  reg('batch_build_screen', `Build a complete Figma screen from a single JSON tree. Creates all nodes recursively in one call.

Node types and their properties:
- frame: x, y, width, height, name, fill({r,g,b,a}), stroke({r,g,b,a,weight}), cornerRadius, autoLayout({layoutMode,paddingTop,paddingBottom,paddingLeft,paddingRight,paddingHorizontal,paddingVertical,padding,itemSpacing,primaryAxisAlignItems,counterAxisAlignItems,layoutWrap}), layoutSizingHorizontal(FILL|HUG|FIXED), layoutSizingVertical(FILL|HUG|FIXED), effects([{type,color,offset,radius,spread}]), imageFill({url,scaleMode}), clipsContent, children[]
- text: x, y, name, text, fontSize, fontWeight(100-900), fontFamily("Pretendard"), fontColor({r,g,b,a}), textAlignHorizontal(LEFT|CENTER|RIGHT), textAutoResize(WIDTH_AND_HEIGHT|HEIGHT|TRUNCATE), lineHeight, letterSpacing, layoutSizingHorizontal, layoutSizingVertical
- rectangle: x, y, width, height, name, fill, stroke, strokeWeight, cornerRadius, layoutSizingHorizontal, layoutSizingVertical, imageFill
- ellipse: x, y, width, height, name, fill, stroke, layoutSizingHorizontal, layoutSizingVertical
- instance: x, y, name, componentKey (REQUIRED — from lookup_variant or pre-loaded keys), width, height, layoutSizingHorizontal, layoutSizingVertical, textOverrides({suffix: text})
- clone: name, sourceNodeId (REQUIRED), width, height, layoutSizingHorizontal, layoutSizingVertical
- icon: name (icon name — Lucide or DS-1 names accepted), size (default 24), iconColor({r,g,b,a})
- svg_icon: (auto-generated from type:"icon", do not use directly) SVG-based icon from Untitled UI GitHub.

textOverrides (instance only): { "suffix": "new text" } — Sets text on instance children using Suffix Map.
imageFill: { url: "https://...", scaleMode?: "FILL"|"FIT" } — Downloads and applies image as fill.
layoutSizingHorizontal/Vertical: FILL to stretch to parent, HUG to fit content, FIXED for explicit size.
Colors: { r: 0-1, g: 0-1, b: 0-1, a?: 0-1 }
Root frame supports: autoLayout, cornerRadius, fill.`, {
    type: 'object',
    properties: {
      blueprint: { type: 'object', description: 'Root node blueprint with children tree. Include name, width, height, fill, and children array.' },
      parentId: { type: 'string', description: 'Optional parent node ID. When set, builds inside the existing parent (section build) and skips auto-deletion of previous root frame.' }
    },
    required: ['blueprint']
  }, async (params) => {
    // Pre-flight: ensure Figma plugin is connected before long operation
    if (!figmaWS.isConnected) {
      throw new Error('Figma plugin is not connected. Please check the plugin is running.');
    }

    const hasParentId = !!(params as Record<string, unknown>).parentId;

    // Auto-check for DS token updates before building
    await syncTokensIfNeeded();

    // Auto-cleanup DISABLED: multiple screens need to coexist on the same page.
    // Previously this deleted the last built root frame on each new build.
    // if (lastBuiltRootId && !hasParentId) { ... }
    lastBuiltRootId = null;

    // ★ Step 1: Enhance blueprint (code-level auto-correction)
    const blueprint = params.blueprint as Record<string, unknown>;
    const enhanced = enhanceBlueprint(blueprint);
    // ★ Step 2: Smart Resolution: resolve semantic names → actual keys
    const resolved = await resolveBlueprint(enhanced);
    const resolvedParams = { ...params, blueprint: resolved };

    // Pre-fetch images in the blueprint tree
    const nodes = resolved.children ? [resolved] : [resolved];
    await prefetchImages(nodes as unknown[]);

    const result = await cmd('batch_build_screen', resolvedParams, 300000) as Record<string, unknown>; // 5 min timeout
    // Track the root frame ID for cleanup on next build (only for full screen builds)
    if (result?.rootId && !hasParentId) {
      lastBuiltRootId = result.rootId as string;
      console.log(`[batch_build_screen] Tracking rootId: ${lastBuiltRootId}`);
    }
    console.log(`[batch_build_screen] Build complete:`, JSON.stringify(result).slice(0, 200));

    // ★ Auto-screenshot: capture immediately after build
    if (result?.rootId) {
      try {
        const screenshot = await cmd('export_node_as_image', {
          nodeId: result.rootId, format: 'PNG', scale: 1
        }, 30000) as Record<string, unknown>;
        if (screenshot?.imageData) {
          result.screenshot = screenshot;
          console.log(`[batch_build_screen] Auto-screenshot captured for ${result.rootId}`);
        }
      } catch (e) {
        console.warn('[batch_build_screen] Auto-screenshot failed:', e);
      }

      // ★ Post-build QA: programmatic dimension check
      try {
        const rootInfo = await cmd('get_node_info', { nodeId: result.rootId }, 10000) as Record<string, unknown>;
        const rootW = rootInfo?.width as number;
        const issues: string[] = [];
        const children = rootInfo?.children as Array<Record<string, unknown>> || [];
        for (const child of children) {
          const cw = child.width as number;
          const ch = child.height as number;
          const cName = child.name as string;
          const cLayout = child.layoutPositioning as string;
          // Skip absolute-positioned children (Tab Bar, FAB)
          if (cLayout === 'ABSOLUTE') continue;
          // Check: full-width sections should match root width
          if (cw < rootW * 0.9 && cw > 0) {
            issues.push(`[QA] "${cName}" width=${cw} (expected ~${rootW}) — may need FILL or explicit width`);
          }
          // Check: zero-dimension nodes
          if (cw === 0 || ch === 0) {
            issues.push(`[QA] "${cName}" has zero dimension: ${cw}x${ch}`);
          }
        }
        if (issues.length > 0) {
          console.warn(`[batch_build_screen] Post-build QA found ${issues.length} issues:`);
          issues.forEach(i => console.warn(i));
          (result as Record<string, unknown>).qaIssues = issues;
        } else {
          console.log('[batch_build_screen] Post-build QA: all checks passed');
        }
      } catch (e) {
        console.warn('[batch_build_screen] Post-build QA failed:', e);
      }
    }

    return result;
  }, { timeoutMs: 310_000 }); // 5min WS + 10s margin

  reg('batch_bind_variables', 'Bind variables to multiple nodes at once', {
    type: 'object',
    properties: {
      bindings: { type: 'array', items: { type: 'object' } }
    },
    required: ['bindings']
  }, async (params) => cmd('batch_bind_variables', params, 300000),
  { timeoutMs: 310_000 });

  reg('batch_set_text_style_id', 'Apply text styles to multiple nodes', {
    type: 'object',
    properties: {
      entries: { type: 'array', items: { type: 'object' } }
    },
    required: ['entries']
  }, async (params) => cmd('batch_set_text_style_id', params, 300000),
  { timeoutMs: 310_000 });

  reg('set_layout_sizing_batch', 'Set layout sizing on multiple nodes', {
    type: 'object',
    properties: {
      entries: { type: 'array', items: { type: 'object' } }
    },
    required: ['entries']
  }, async (params) => cmd('set_layout_sizing_batch', params));

  // ★ Pre-cache ALL DS components on connect (internal tool, not exposed to LLM)
  reg('pre_cache_components', 'Pre-cache DS component keys in Figma plugin for instant lookups', {
    type: 'object',
    properties: {
      keys: {
        type: 'array',
        items: { type: 'string' },
        description: 'Array of componentKey strings to pre-import'
      }
    },
    required: ['keys']
  }, async (params) => cmd('pre_cache_components', params, 600000),
  { timeoutMs: 620_000 }); // 10min WS + 20s margin

  // ============================================================
  // Pencil → Figma Converter
  // ============================================================

  reg('convert_pen_to_figma', 'Convert a Pencil (.pen) node tree to Figma. Takes PenNode JSON from Pencil batch_get and creates the design in Figma via batch_build_screen. Accepts single node or array of nodes.', {
    type: 'object',
    properties: {
      penNodes: { description: 'Root PenNode tree from Pencil batch_get. Can be a single node object or an array of nodes.' },
      screenName: { type: 'string', description: 'Name for the Figma screen frame' },
      preserveFonts: { type: 'boolean', description: 'Keep original fonts (true) or use Pretendard (false). Default: true' },
    },
    required: ['penNodes'],
  }, async (params) => {
    // ★ Handle array input: batch_get returns arrays
    let penRoot: PenNode;
    const rawNodes = params.penNodes;
    if (Array.isArray(rawNodes)) {
      if (rawNodes.length === 0) {
        return { error: 'penNodes array is empty' };
      }
      if (rawNodes.length === 1) {
        penRoot = rawNodes[0] as PenNode;
      } else {
        // Multiple nodes — wrap in a root frame
        penRoot = {
          type: 'frame',
          name: 'Pen Import',
          layout: 'v',
          width: 393,
          height: 852,
          children: rawNodes as PenNode[],
        };
        console.log(`[convert_pen_to_figma] Wrapped ${rawNodes.length} root nodes into container frame`);
      }
    } else {
      penRoot = rawNodes as PenNode;
    }

    // Validate penRoot has required structure
    if (!penRoot || typeof penRoot !== 'object') {
      return { error: 'penNodes must be a PenNode object or array of PenNode objects' };
    }
    if (!penRoot.type) {
      // Try to infer type from children
      if (penRoot.children) {
        penRoot.type = 'frame';
      } else if (penRoot.content) {
        penRoot.type = 'text';
      } else {
        penRoot.type = 'frame';
      }
      console.warn(`[convert_pen_to_figma] Root node missing type, inferred as "${penRoot.type}"`);
    }

    const screenName = params.screenName as string | undefined;
    const preserveFonts = params.preserveFonts as boolean | undefined;

    // Step 1: Convert PenNode tree → Figma Blueprint
    let blueprint: Record<string, unknown>;
    let stats: { totalNodes: number; frames: number; texts: number; icons: number; shapes: number; warnings: number };
    let warnings: string[];
    try {
      const result = convertPenToFigma(penRoot, { preserveFonts });
      blueprint = result.blueprint;
      stats = result.stats;
      warnings = result.warnings;
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e);
      console.error(`[convert_pen_to_figma] Conversion failed:`, errMsg);
      return { error: `PenNode → Blueprint conversion failed: ${errMsg}`, inputType: penRoot.type, inputKeys: Object.keys(penRoot) };
    }
    if (screenName) blueprint.name = screenName;

    console.log(`[convert_pen_to_figma] Converted: ${stats.totalNodes} nodes (${stats.frames} frames, ${stats.texts} texts, ${stats.icons} icons, ${stats.shapes} shapes), ${warnings.length} warnings`);

    // Step 2: Run through the same pipeline as batch_build_screen
    // (enhanceBlueprint → resolveBlueprint → prefetchImages → Figma build)
    if (lastBuiltRootId) {
      try {
        await cmd('delete_node', { nodeId: lastBuiltRootId });
        console.log(`[convert_pen_to_figma] Deleted previous build: ${lastBuiltRootId}`);
      } catch (e) {
        console.warn(`[convert_pen_to_figma] Failed to delete previous build:`, e);
      }
      lastBuiltRootId = null;
    }

    const enhanced = enhanceBlueprint(blueprint);
    const resolved = await resolveBlueprint(enhanced);
    await prefetchImages([resolved]);

    const result = await cmd('batch_build_screen', { blueprint: resolved }, 300000) as Record<string, unknown>;

    if (result?.rootId) {
      lastBuiltRootId = result.rootId as string;
      console.log(`[convert_pen_to_figma] Tracking rootId: ${lastBuiltRootId}`);

      // Auto-screenshot
      try {
        const screenshot = await cmd('export_node_as_image', {
          nodeId: result.rootId, format: 'PNG', scale: 1
        }, 30000) as Record<string, unknown>;
        if (screenshot?.imageData) {
          result.screenshot = screenshot;
        }
      } catch (e) {
        console.warn('[convert_pen_to_figma] Auto-screenshot failed:', e);
      }
    }

    return {
      ...result,
      conversionStats: stats,
      conversionWarnings: warnings,
    };
  });

  return tools;
}

// ============================================================
// Helper functions (ported from existing batch-tools.ts)
// ============================================================

function extractId(result: unknown): string | undefined {
  const r = result as Record<string, unknown>;
  return (r?.id || r?.nodeId) as string | undefined;
}

function normalizeParams(op: string, params: Record<string, unknown>): Record<string, unknown> {
  switch (op) {
    case 'set_fill_color': {
      if (params.r !== undefined && !params.color) {
        const { nodeId, r, g, b, a, ...rest } = params;
        return { nodeId, color: { r, g, b, a: a ?? 1 }, ...rest };
      }
      return params;
    }
    case 'set_stroke_color': {
      if (params.r !== undefined && !params.color) {
        const { nodeId, r, g, b, a, strokeWeight, ...rest } = params;
        return { nodeId, color: { r, g, b, a: a ?? 1 }, strokeWeight: strokeWeight ?? 1, ...rest };
      }
      return params;
    }
    case 'set_layout_sizing': {
      const n = { ...params };
      if (params.horizontal && !params.layoutSizingHorizontal) n.layoutSizingHorizontal = params.horizontal;
      if (params.vertical && !params.layoutSizingVertical) n.layoutSizingVertical = params.vertical;
      return n;
    }
    case 'set_text_content': {
      if (typeof params.text === 'string') {
        return { ...params, text: (params.text as string).replace(/<br>/g, '\u2028') };
      }
      return params;
    }
    default:
      return params;
  }
}

async function fetchImageAsBase64(url: string): Promise<string | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    return Buffer.from(buffer).toString('base64');
  } catch (error) {
    console.error(`Image fetch failed for ${url}:`, error);
    return null;
  }
}

// ============================================================
// Smart Resolution — semantic names → actual Figma keys
// ============================================================

export async function resolveBlueprint(node: Record<string, unknown>): Promise<Record<string, unknown>> {
  // Deep copy to prevent shared references — shallow copy caused SVG icons
  // to be moved to wrong parents when the same object was mutated in multiple places
  const resolved = JSON.parse(JSON.stringify(node)) as Record<string, unknown>;

  // 1. statusBar: true → pass through to code.js for name-based search across all pages
  //    code.js will find "Status Bar" component/instance and createInstance/clone it.
  //    Previously this injected a clone node with a hardcoded sourceNodeId that could be stale.

  // 2. type: "instance" + component/variant → componentKey resolution
  if (resolved.type === 'instance' && resolved.component && !resolved.componentKey) {
    const key = resolveVariantKey(resolved.component as string, resolved.variant as string | undefined);
    if (key) {
      resolved.componentKey = key;
      console.log(`[resolve] ${resolved.component}${resolved.variant ? ` (${resolved.variant})` : ''} → ${key.slice(0, 12)}...`);
    } else {
      console.warn(`[resolve] Component not found: ${resolved.component} (${resolved.variant || 'default'})`);
    }
    delete resolved.component;
    delete resolved.variant;
  }

  // 3. type: "icon" → type: "svg_icon" (local @untitledui/icons SVG)
  if (resolved.type === 'icon' && (resolved.iconName || resolved.name)) {
    const iconName = (resolved.iconName || resolved.name) as string;
    const iconSize = (resolved.size as number) || 24;
    const iconColor = resolved.iconColor as { r: number; g: number; b: number; a?: number } | undefined;
    // Convert {r,g,b} 0-1 to hex for SVG stroke attribute
    const hexColor = iconColor
      ? '#' + [iconColor.r, iconColor.g, iconColor.b].map(c => Math.round(c * 255).toString(16).padStart(2, '0')).join('')
      : '#000000';
    const svgData = await getIconSvgAsync(iconName, iconSize, hexColor) || getIconSvg(iconName, iconSize, hexColor);
    if (svgData) {
      resolved.type = 'svg_icon';
      resolved.svgData = svgData;
      resolved.ds1Name = resolveIconFile(iconName) || iconName;
      resolved.width = iconSize;
      resolved.height = iconSize;
      if (!resolved.iconColor) resolved.iconColor = { r: 0, g: 0, b: 0, a: 1 };
      delete resolved.size;
      console.log(`[resolve] icon "${iconName}" → svg_icon (local, ${iconSize}px)`);
    } else {
      // Fallback: 회색 원형 placeholder
      console.warn(`[resolve] Icon not found: ${iconName}, creating placeholder`);
      resolved.type = 'frame';
      resolved.width = iconSize;
      resolved.height = iconSize;
      resolved.cornerRadius = iconSize / 2;
      resolved.fill = { r: 0.85, g: 0.85, b: 0.88, a: 1 };
      delete resolved.size;
    }
  }

  // 4. Flat layout properties → autoLayout object (code.js expects spec.autoLayout)
  if (resolved.layoutMode && !resolved.autoLayout) {
    const autoLayoutKeys = ['layoutMode', 'itemSpacing', 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight',
      'paddingHorizontal', 'paddingVertical', 'padding', 'primaryAxisAlignItems', 'counterAxisAlignItems', 'layoutWrap'];
    const al: Record<string, unknown> = {};
    for (const key of autoLayoutKeys) {
      if (resolved[key] !== undefined) {
        al[key] = resolved[key];
        delete resolved[key];
      }
    }
    resolved.autoLayout = al;
  }

  // 5. fills array → fill single object (code.js expects spec.fill, not spec.fills)
  if (Array.isArray(resolved.fills) && !resolved.fill) {
    const fills = resolved.fills as Array<Record<string, unknown>>;
    const solidFill = fills.find(f => f.type === 'SOLID' && f.visible !== false);
    if (solidFill) {
      const color = solidFill.color as Record<string, number>;
      if (color) {
        resolved.fill = { r: color.r, g: color.g, b: color.b, a: (solidFill.opacity as number) ?? 1 };
      }
    }
    delete resolved.fills;
  }

  // 6. TEXT type normalization (code.js expects lowercase "text")
  if (typeof resolved.type === 'string' && resolved.type.toUpperCase() === 'TEXT') {
    resolved.type = 'text';
    // Map fontFamily/fontWeight/fontSize to code.js expected format
    if (resolved.fontFamily && !resolved.fontName) {
      resolved.fontName = resolved.fontFamily;
      delete resolved.fontFamily;
    }
  }

  // 7. effects array: ensure blendMode and visible for DROP_SHADOW
  if (Array.isArray(resolved.effects)) {
    resolved.effects = (resolved.effects as Array<Record<string, unknown>>).map(e => {
      if (e.type === 'DROP_SHADOW') {
        return { blendMode: 'NORMAL', visible: true, ...e };
      }
      return e;
    });
  }

  // Recurse: process children
  if (Array.isArray(resolved.children)) {
    resolved.children = await Promise.all(
      (resolved.children as Record<string, unknown>[]).map(child =>
        resolveBlueprint(child as Record<string, unknown>)
      )
    );
  }

  return resolved;
}

export function resolveVariantKey(componentName: string, variantStr?: string): string | null {
  try {
    const variants = getVariants();
    const nameLower = componentName.toLowerCase();

    // Smart component name matching (priority order):
    // 1. Exact match (case-insensitive)
    // 2. Suffix match: "Button" → "Buttons/Button"
    // 3. Starts-with match: "Input" → "Input field"
    // 4. Contains match: "Social" → "Social button"
    let entry = variants.find(v => v.name.toLowerCase() === nameLower);
    if (!entry) {
      entry = variants.find(v => {
        const vLower = v.name.toLowerCase();
        // Suffix: "Buttons/Button" ends with "/button"
        return vLower.endsWith('/' + nameLower);
      });
    }
    if (!entry) {
      entry = variants.find(v => v.name.toLowerCase().startsWith(nameLower));
    }
    if (!entry) {
      entry = variants.find(v => v.name.toLowerCase().includes(nameLower));
    }
    if (!entry) {
      console.warn(`[resolve] Component "${componentName}" not found in ${variants.length} components`);
      return null;
    }

    console.log(`[resolve] "${componentName}" → matched "${entry.name}" (${Object.keys(entry.variants).length} variants)`);

    if (!variantStr) {
      return Object.values(entry.variants)[0] || null;
    }

    // Try exact variant match first
    if (entry.variants[variantStr]) {
      return entry.variants[variantStr];
    }

    // Partial matching: all parts of variantStr must be present in the key
    // Collect ALL matches, then pick the best one
    const parts = variantStr.split(',').map(p => p.trim().toLowerCase());
    const userSpecifiedProps = new Set(parts.map(p => p.split('=')[0].trim()));
    const matches: Array<{ key: string; value: string; score: number }> = [];

    for (const [key, value] of Object.entries(entry.variants)) {
      const keyLower = key.toLowerCase();
      if (parts.every(part => keyLower.includes(part))) {
        // Score: prefer default-like values for unspecified properties
        let score = 0;
        if (!userSpecifiedProps.has('state') && keyLower.includes('state=default')) score += 10;
        if (!userSpecifiedProps.has('icon only') && keyLower.includes('icon only=false')) score += 5;
        if (!userSpecifiedProps.has('supporting text') && keyLower.includes('supporting text=false')) score += 5;
        if (!userSpecifiedProps.has('destructive') && keyLower.includes('destructive=false')) score += 3;
        matches.push({ key, value, score });
      }
    }

    if (matches.length > 0) {
      // Sort by score descending, pick best
      matches.sort((a, b) => b.score - a.score);
      console.log(`[resolve] "${variantStr}" → ${matches.length} matches, best: "${matches[0].key}" (score=${matches[0].score})`);
      return matches[0].value;
    }

    // Fallback: return first variant
    console.warn(`[resolve] Variant "${variantStr}" not found for ${entry.name}, using first variant`);
    return Object.values(entry.variants)[0] || null;
  } catch (e) {
    console.error('[resolve] resolveVariantKey error:', e);
    return null;
  }
}

export function resolveIconNodeId(iconName: string): string | null {
  try {
    const icons = getIcons();
    const nameLower = iconName.toLowerCase().trim();

    // 1. Exact match
    if (icons[iconName]) return icons[iconName];
    if (icons[nameLower]) return icons[nameLower];

    const allNames = Object.keys(icons);

    // 2. Case-insensitive exact match
    const exact = allNames.find(n => n.toLowerCase() === nameLower);
    if (exact) return icons[exact];

    // 2.5 Lucide → DS-1 name mapping (before fuzzy matching)
    const lucideMapped = LUCIDE_TO_DS1_MAP[nameLower];
    if (lucideMapped) {
      const mappedId = icons[lucideMapped] || icons[lucideMapped.toLowerCase()];
      if (mappedId) {
        console.log(`[resolve] icon lucide: "${iconName}" → "${lucideMapped}"`);
        return mappedId;
      }
      const mappedExact = allNames.find(n => n.toLowerCase() === lucideMapped.toLowerCase());
      if (mappedExact) {
        console.log(`[resolve] icon lucide: "${iconName}" → "${mappedExact}"`);
        return icons[mappedExact];
      }
    }

    // 3. Suffix match: "bell" → "bell-01" (most common pattern — icons have -01/-02 suffixes)
    const suffixed = allNames.find(n => n.toLowerCase() === nameLower + '-01');
    if (suffixed) {
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${suffixed}" (added -01 suffix)`);
      return icons[suffixed];
    }

    // 4. Prefix match: "shopping-bag" → "shopping-bag-01"
    const prefixed = allNames.filter(n => n.toLowerCase().startsWith(nameLower));
    if (prefixed.length > 0) {
      // Prefer shortest match (most specific)
      prefixed.sort((a, b) => a.length - b.length);
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${prefixed[0]}" (prefix match, ${prefixed.length} candidates)`);
      return icons[prefixed[0]];
    }

    // 5. Contains match: "cart" → "shopping-cart-01"
    const contains = allNames.filter(n => n.toLowerCase().includes(nameLower));
    if (contains.length > 0) {
      contains.sort((a, b) => a.length - b.length);
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${contains[0]}" (contains match, ${contains.length} candidates)`);
      return icons[contains[0]];
    }

    // 6. Word match: "close" → "x-close", "search" → "search-lg"
    const words = nameLower.split('-');
    const wordMatch = allNames.filter(n => {
      const nLower = n.toLowerCase();
      return words.every(w => nLower.includes(w));
    });
    if (wordMatch.length > 0) {
      wordMatch.sort((a, b) => a.length - b.length);
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${wordMatch[0]}" (word match)`);
      return icons[wordMatch[0]];
    }

    // 7. Fallback: use a visually appealing icon instead of nothing
    const FALLBACK_ICON = 'star-01';
    const fallback = allNames.find(n => n.toLowerCase() === FALLBACK_ICON);
    if (fallback) {
      console.warn(`[resolve] icon "${iconName}" not found in DS — using fallback "${fallback}" (requested: "${iconName}")`);
      return icons[fallback];
    }

    console.warn(`[resolve] Icon not found (no fallback available): "${iconName}"`);
    return null;
  } catch (e) {
    console.error('[resolve] resolveIconNodeId error:', e);
    return null;
  }
}

/**
 * Resolve icon name to DS-1 icon name (not node ID).
 * Reuses the same 7-step fuzzy matching + Lucide mapping from resolveIconNodeId.
 */
export function resolveIconDs1Name(iconName: string): string | null {
  try {
    const icons = getIcons();
    const nameLower = iconName.toLowerCase().trim();
    const allNames = Object.keys(icons);

    // 1. Exact match
    if (icons[iconName]) return iconName;
    if (icons[nameLower]) return nameLower;
    const exact = allNames.find(n => n.toLowerCase() === nameLower);
    if (exact) return exact;

    // 2. Lucide mapping
    const lucideMapped = LUCIDE_TO_DS1_MAP[nameLower];
    if (lucideMapped) {
      const mapped = allNames.find(n => n.toLowerCase() === lucideMapped.toLowerCase());
      if (mapped) return mapped;
    }

    // 3. Suffix match: "bell" → "bell-01"
    const suffixed = allNames.find(n => n.toLowerCase() === nameLower + '-01');
    if (suffixed) return suffixed;

    // 4. Prefix match
    const prefixed = allNames.filter(n => n.toLowerCase().startsWith(nameLower));
    if (prefixed.length > 0) {
      prefixed.sort((a, b) => a.length - b.length);
      return prefixed[0];
    }

    // 5. Contains match
    const contains = allNames.filter(n => n.toLowerCase().includes(nameLower));
    if (contains.length > 0) {
      contains.sort((a, b) => a.length - b.length);
      return contains[0];
    }

    // 6. Word match
    const words = nameLower.split('-');
    const wordMatch = allNames.filter(n => words.every(w => n.toLowerCase().includes(w)));
    if (wordMatch.length > 0) {
      wordMatch.sort((a, b) => a.length - b.length);
      return wordMatch[0];
    }

    // 7. Fallback
    return 'star-01';
  } catch {
    return null;
  }
}

/** Lucide 아이콘명 → DS-1 아이콘명 매핑 (이름이 다른 것만, 퍼지 매칭이 처리하는 이름은 제외) */
const LUCIDE_TO_DS1_MAP: Record<string, string> = {
  // 완전 MISS되는 이름 (DS-1에 다른 이름으로 존재)
  'house': 'home-01',
  'more-horizontal': 'dots-horizontal',
  'more-vertical': 'dots-vertical',
  'map-pin': 'marker-pin-01',
  'coins': 'currency-dollar-circle',
  'flag': 'announcement-01',
  'file-text': 'file-06',
  'trending-up': 'trend-up-01',
  'trending-down': 'trend-down-01',
  'rotate-cw': 'refresh-cw-01',
  'volume-2': 'volume-max',
  'scan-line': 'scan',
  'footprints': 'route',
  'ellipsis': 'dots-horizontal',
  'dollar-sign': 'currency-dollar',
  'undo': 'reverse-left',
  'redo': 'reverse-right',
  'smartphone': 'phone-01',
  'loader': 'loading-01',
  'timer': 'clock-stopwatch',
  'calendar-days': 'calendar-date',
  'megaphone': 'announcement-01',
  'sparkle': 'star-06',
  'sparkles': 'stars-01',
  'crown': 'award-01',
  'shield-check': 'shield-tick',
  'bell-ring': 'bell-ringing-01',
  'bell-off': 'bell-off-01',
  'panel-left': 'layout-left',
  'panel-right': 'layout-right',
  'calendar-check': 'calendar-check-01',
  'history': 'clock-refresh',
  'signal': 'signal-01',
  'battery-full': 'battery-full',
  // 퍼지 매칭이 틀린 결과를 주는 이름
  'share': 'share-05',
  'share-2': 'share-05',
  'filter': 'filter-funnel-01',
  'download': 'download-04',
  'upload': 'upload-04',
  'credit-card': 'credit-card-plus',
  'phone': 'phone-call-01',
  // 안전한 명시적 매핑 (빠른 해결 + 정확도 보장)
  'x': 'x-close',
  'trash-2': 'trash-01',
  'edit-2': 'edit-01',
  'edit-3': 'edit-01',
  'log-out': 'log-out-01',
  'log-in': 'log-in-01',
  'layers': 'layers-two-01',
  'smile': 'face-smile',
  'moon': 'moon-01',
  'cloud': 'cloud-01',
  'qr-code': 'qr-code-01',
  'unlock': 'lock-unlocked-01',
  'circle-check': 'check-circle',
  'circle-x': 'x-circle',
  'circle-alert': 'alert-circle',
  'triangle-alert': 'alert-triangle',
  'external-link': 'link-external-01',
};

// ============================================================
// Blueprint Enhancer — 코드 레벨 자동 변환 (LLM 의존 없음)
// ============================================================

/** 텍스트 키워드 → DS 아이콘 이름 매핑 */
const ICON_KEYWORD_MAP: Record<string, string> = {
  '출석': 'calendar',
  '체크인': 'check-circle',
  '초대': 'user-plus-01',
  '친구': 'users-01',
  '구매': 'shopping-bag-01',
  '쇼핑': 'shopping-cart-01',
  '포인트': 'currency-dollar-circle',
  '적립': 'star-01',
  '보상': 'gift-01',
  '리워드': 'gift-01',
  '이벤트': 'announcement-01',
  '알림': 'bell-01',
  '설정': 'settings-01',
  '홈': 'home-01',
  '검색': 'search-lg',
  '마이': 'user-01',
  '프로필': 'user-circle',
  '결제': 'credit-card-plus',
  '지갑': 'wallet-01',
  '공유': 'share-05',
  '메시지': 'message-circle-01',
  '채팅': 'message-circle-01',
  '전화': 'phone-call-01',
  '메일': 'mail-01',
  '카메라': 'camera-01',
  '사진': 'image-01',
  '좋아요': 'heart',
  '북마크': 'bookmark',
  '잠금': 'lock-01',
  '보안': 'lock-01',
  '시간': 'clock',
  '위치': 'globe-01',
  '링크': 'link-01',
  '태그': 'tag-01',
  '다운로드': 'download-04',
  '삭제': 'trash-01',
  '수정': 'edit-01',
  '복사': 'copy-01',
  '필터': 'filter-funnel-01',
  'qr': 'qr-code-01',
  '주문': 'receipt',
  '영수증': 'receipt',
  '쿠폰': 'tag-01',
  '할인': 'tag-01',
  '배송': 'shopping-bag-01',
  '정보': 'info-circle',
  '도움': 'help-circle',
  '안내': 'info-circle',
  '공지': 'bell-01',
  // 챌린지/스테이지 관련
  '운동': 'activity',
  '챌린지': 'flag-01',
  '독서': 'book-open-01',
  '마라톤': 'activity',
  '미술': 'palette',
  '작품': 'palette',
  '스테이지': 'layers-three-01',
  '참가': 'users-01',
  '모집': 'users-01',
  '완성': 'check-circle',
  '달성': 'target-01',
  '목표': 'target-01',
  '건강': 'heart-hand',
  '피트니스': 'activity',
  '요리': 'coffee',
  '학습': 'graduation-hat-01',
  '영어': 'book-open-01',
  '코딩': 'code-01',
  '음악': 'music-note-01',
};

/** 아이콘 배경 tint 색상 (회전 사용) */
const ICON_TINT_COLORS = [
  { r: 1, g: 0.94, b: 0.92 },      // warm peach
  { r: 0.92, g: 0.97, b: 1 },      // soft blue
  { r: 0.93, g: 1, b: 0.95 },      // mint green
  { r: 0.98, g: 0.95, b: 1 },      // lavender
  { r: 1, g: 0.97, b: 0.88 },      // warm yellow
  { r: 0.95, g: 0.93, b: 1 },      // soft purple
];

/** 탭바 기본 아이콘 매핑 */
const TAB_ICON_MAP: Record<string, string> = {
  '홈': 'home-01', 'home': 'home-01',
  '포인트': 'currency-dollar-circle', 'point': 'currency-dollar-circle', 'points': 'currency-dollar-circle',
  '쇼핑': 'shopping-bag-01', 'shop': 'shopping-bag-01', 'store': 'shopping-bag-01',
  '마이': 'user-01', 'my': 'user-01', '마이페이지': 'user-01', 'profile': 'user-01', '나': 'user-01',
  '검색': 'search-lg', 'search': 'search-lg',
  '장바구니': 'shopping-cart-01', 'cart': 'shopping-cart-01',
  '메시지': 'message-circle-01', 'chat': 'message-circle-01',
  '알림': 'bell-01', 'notification': 'bell-01',
  '설정': 'settings-01', 'settings': 'settings-01',
  '즐겨찾기': 'heart', 'favorite': 'heart',
  '카테고리': 'menu-01', 'category': 'menu-01',
  '챌린지뷰': 'flag-01', '챌린지': 'flag-01', 'challenge': 'flag-01',
  '스테이지': 'layers-three-01', 'stage': 'layers-three-01',
  '다이어리': 'book-open-01', 'diary': 'book-open-01',
  '타임뷰': 'clock', 'timeline': 'clock',
  '피드': 'rss-01', 'feed': 'rss-01',
  '커뮤니티': 'users-01', 'community': 'users-01',
  '활동': 'activity', 'activity': 'activity',
  '지도': 'globe-01', 'map': 'globe-01',
  '예약': 'calendar', 'booking': 'calendar',
  '혜택': 'gift-01', 'benefit': 'gift-01',
  '다이얼뷰': 'clock',
};

/**
 * Blueprint 전체 트리를 코드 레벨에서 개선.
 * LLM이 rectangle을 생성해도 텍스트 컨텍스트 기반으로 적절한 아이콘으로 변환.
 */
export function enhanceBlueprint(root: Record<string, unknown>): Record<string, unknown> {
  let tintColorIdx = 0;
  // 통계 카운터
  const stats = { font: 0, color: 0, sizing: 0, icon: 0, structure: 0, fontSize: 0, alignment: 0 };

  // ── Step 0: 루트 프레임에 statusBar: true 자동 주입 ──
  if (isMobileRootFrame(root) && !root.statusBar) {
    const children = root.children as Record<string, unknown>[] | undefined;
    const hasStatusBarChild = children?.some(c => {
      const name = ((c.name as string) || '').toLowerCase();
      return name.includes('status bar') || name.includes('statusbar') ||
        (c.type === 'clone' && (c.name as string || '').toLowerCase().includes('status'));
    });
    if (!hasStatusBarChild) {
      root.statusBar = true;
      console.log('[enforce] Auto-injected statusBar: true on root frame');
      stats.structure++;
    }
  }

  // ── Step 0a: 규칙 A — 루트 프레임 구조 강제 ──
  if (root.type === 'frame') {
    const w = root.width as number | undefined;
    const h = root.height as number | undefined;
    const isMobileWidth = typeof w === 'number' && w >= 360 && w <= 430;
    const noWidth = typeof w !== 'number';
    // 모바일 루트 프레임 감지 (너비 미지정이거나 360-430 범위)
    if (isMobileWidth || noWidth) {
      if (!w) {
        root.width = 393;
        console.log('[enforce] Root frame width forced: 393');
        stats.structure++;
      }
      if (!h) {
        root.height = 852;
        console.log('[enforce] Root frame height forced: 852');
        stats.structure++;
      }
      if (!root.autoLayout) {
        root.autoLayout = { layoutMode: 'VERTICAL' };
        console.log('[enforce] Root frame autoLayout forced: VERTICAL');
        stats.structure++;
      }
      if (!root.fill) {
        root.fill = { r: 1, g: 1, b: 1, a: 1 };
        console.log('[enforce] Root frame fill forced: white');
        stats.structure++;
      }
      if (root.clipsContent === undefined) {
        root.clipsContent = true;
        console.log('[enforce] Root frame clipsContent forced: true');
        stats.structure++;
      }
      if (!root.name) {
        root.name = 'Mobile Screen';
        console.log('[enforce] Root frame name forced: Mobile Screen');
        stats.structure++;
      }
    }
  }

  // ── 색상 속성 정규화 헬퍼 (노드 내) ──
  function normalizeNodeColors(n: Record<string, unknown>): void {
    const colorProps = ['fill', 'fontColor', 'stroke', 'iconColor', 'backgroundColor'];
    for (const prop of colorProps) {
      if (n[prop] !== undefined) {
        const normalized = normalizeColor(n[prop]);
        if (normalized && typeof n[prop] !== 'object') {
          console.log(`[enforce] Color normalized: ${prop} ${JSON.stringify(n[prop])} → ${JSON.stringify(normalized)}`);
          n[prop] = normalized;
          stats.color++;
        } else if (normalized && typeof n[prop] === 'object') {
          const orig = n[prop] as Record<string, number>;
          // 0-255 범위 정규화 체크
          if (orig.r > 1 || orig.g > 1 || orig.b > 1) {
            console.log(`[enforce] Color range normalized: ${prop} (values > 1 detected)`);
            n[prop] = normalized;
            stats.color++;
          }
        }
      }
    }
  }

  function enhance(node: Record<string, unknown>, _parent?: Record<string, unknown>, isRootChild?: boolean): Record<string, unknown> {
    const n = { ...node };

    // ── 1. Tab Bar detection & fix (기존 + 규칙 G 확장) ──
    if (isTabBar(n)) {
      console.log('[enforce] Tab bar detected, fixing icons & structure');
      fixTabBar(n);
      // 규칙 G: Tab Bar 구조 강제
      if (!n.fill) {
        n.fill = { r: 1, g: 1, b: 1, a: 1 };
        console.log('[enforce] Tab bar fill forced: white');
        stats.structure++;
      }
      if (!n.stroke) {
        n.stroke = { r: 0.95, g: 0.96, b: 0.96, a: 1 };
        if (!n.strokeWeight) n.strokeWeight = 1;
        if (!n.strokeAlign) n.strokeAlign = 'INSIDE';
        if (n.strokeSide === undefined) n.strokeSide = 'TOP';
        console.log('[enforce] Tab bar stroke forced: top border');
        stats.structure++;
      }
      if (!n.height) {
        n.height = 83;
        console.log('[enforce] Tab bar height forced: 83');
        stats.structure++;
      }
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (al) {
        if (al.layoutMode !== 'HORIZONTAL') {
          al.layoutMode = 'HORIZONTAL';
          console.log('[enforce] Tab bar layoutMode forced: HORIZONTAL');
          stats.structure++;
        }
        if (!al.primaryAxisAlignItems) {
          al.primaryAxisAlignItems = 'SPACE_BETWEEN';
          console.log('[enforce] Tab bar alignment forced: SPACE_BETWEEN');
          stats.structure++;
        }
      }
      if (!n.layoutPositioning) {
        n.layoutPositioning = 'ABSOLUTE';
        console.log('[enforce] Tab bar layoutPositioning forced: ABSOLUTE');
        stats.structure++;
      }
      // 각 탭 아이템 정렬 강제
      const tabChildren = n.children as Record<string, unknown>[] | undefined;
      if (tabChildren) {
        for (const tab of tabChildren) {
          if (tab.type === 'frame') {
            const tabAl = tab.autoLayout as Record<string, unknown> | undefined;
            if (tabAl) {
              if (tabAl.layoutMode !== 'VERTICAL') tabAl.layoutMode = 'VERTICAL';
              if (!tabAl.counterAxisAlignItems) tabAl.counterAxisAlignItems = 'CENTER';
              if (!tabAl.primaryAxisAlignItems) tabAl.primaryAxisAlignItems = 'CENTER';
            }
          }
        }
      }
      stats.icon++;
    }

    // ── 2. List item icon fix ──
    if (isListItemWithPlaceholderIcon(n)) {
      console.log(`[enforce] List item "${n.name}" — converting placeholder to icon`);
      convertListItemIcon(n, tintColorIdx);
      tintColorIdx++;
      stats.icon++;
    }

    // ── 3. Standalone small rectangles/ellipses ──
    if (isSmallPlaceholder(n) && !isInsideListItem(n, _parent)) {
      const contextText = getContextText(n, _parent);
      const iconName = guessIconFromText(contextText) || 'star-01';
      const tint = ICON_TINT_COLORS[tintColorIdx % ICON_TINT_COLORS.length];
      tintColorIdx++;
      console.log(`[enforce] Converting standalone placeholder "${n.name}" → ${iconName}`);
      convertToIconBg(n, iconName, tint);
      stats.icon++;
    }

    // ── 4. Emoji text → icon conversion ──
    if (isEmojiOnlyText(n)) {
      const emoji = (n.text as string).trim();
      const iconName = EMOJI_TO_ICON_MAP[emoji] || guessIconFromEmoji(emoji) || 'star-01';
      const tint = ICON_TINT_COLORS[tintColorIdx % ICON_TINT_COLORS.length];
      tintColorIdx++;
      console.log(`[enforce] Converting emoji "${emoji}" → icon "${iconName}"`);
      if (_parent) {
        const parentAl = _parent.autoLayout as Record<string, unknown> | undefined;
        if (parentAl?.layoutMode === 'HORIZONTAL') {
          convertToIconBg(n, iconName, tint);
        } else {
          n.type = 'icon';
          n.name = iconName;
          n.size = (n.fontSize as number) || 24;
          delete n.text;
          delete n.fontSize;
          delete n.fontWeight;
          delete n.fontFamily;
          delete n.fontColor;
          delete n.textAlignHorizontal;
          delete n.layoutSizingHorizontal;
        }
      } else {
        n.type = 'icon';
        n.name = iconName;
        n.size = 24;
        delete n.text;
        delete n.fontSize;
        delete n.fontWeight;
        delete n.fontFamily;
        delete n.fontColor;
      }
      stats.icon++;
    }

    // ── 5. 텍스트 layoutSizingHorizontal — 부모 방향에 따라 결정 ──
    // VERTICAL 부모 → FILL (가로 폭 채움, 표준 cross-axis stretch)
    // HORIZONTAL 부모 → HUG (텍스트 내용에 맞춤)
    // ⚠️ HORIZONTAL 부모에서 FILL 시 글자가 세로로 1자씩 줄바꿈되는 치명적 버그
    if (n.type === 'text') {
      // 부모 방향 감지 (autoLayout.layoutMode 또는 직접 layoutMode)
      const parentAl = _parent?.autoLayout as Record<string, unknown> | undefined;
      const parentMode = (parentAl?.layoutMode as string) || (_parent?.layoutMode as string) || undefined;
      const isHorizontalParent = parentMode === 'HORIZONTAL';

      if (!n.layoutSizingHorizontal) {
        n.layoutSizingHorizontal = isHorizontalParent ? 'HUG' : 'FILL';
        stats.sizing++;
      } else if (n.layoutSizingHorizontal === 'FILL' && isHorizontalParent) {
        // LLM이 FILL로 설정했어도 HORIZONTAL 부모면 강제 HUG
        console.log(`[enforce] Text "${((n.text as string) || '').slice(0, 15)}" in HORIZONTAL parent: FILL → HUG`);
        n.layoutSizingHorizontal = 'HUG';
        stats.sizing++;
      }
    }

    // ── 5a. 규칙 B — 폰트 강제 (Pretendard) ──
    if (n.type === 'text') {
      const currentFont = ((n.fontFamily as string) || '').toLowerCase().trim();
      const textContent = (n.text as string) || '';
      const hasKorean = containsKorean(textContent) || containsKorean((n.name as string) || '');
      const isNonKoreanFont = !currentFont || NON_KOREAN_FONTS.some(f => currentFont.includes(f));

      if (hasKorean || isNonKoreanFont) {
        if ((n.fontFamily as string) !== 'Pretendard') {
          const oldFont = n.fontFamily || '(none)';
          n.fontFamily = 'Pretendard';
          console.log(`[enforce] Font forced: "${oldFont}" → "Pretendard" (text: "${textContent.slice(0, 20)}")`);
          stats.font++;
        }
      }
    }

    // ── 5b. 규칙 E — 최소 fontSize 강제 ──
    if (n.type === 'text') {
      const fs = n.fontSize as number | undefined;
      if (typeof fs === 'number' && fs < 10) {
        console.log(`[enforce] fontSize forced: ${fs} → 12`);
        n.fontSize = 12;
        stats.fontSize++;
      } else if (fs === undefined) {
        n.fontSize = 14;
        console.log('[enforce] fontSize default: 14');
        stats.fontSize++;
      }
    }

    // ── 5c. 규칙 C — 색상 정규화 ──
    normalizeNodeColors(n);

    // ── 5d. 규칙 D — VERTICAL 부모의 모든 FRAME 자식 FILL width ──
    // 루트 직계뿐 아니라 모든 depth에서 VERTICAL 부모의 FRAME 자식은 FILL 필수
    // code.js에도 auto-FILL이 있지만 enhanceBlueprint에서 미리 설정하면 더 안정적
    if (_parent && n.type === 'frame' && !n.layoutSizingHorizontal) {
      const parentAl = _parent.autoLayout as Record<string, unknown> | undefined;
      const parentMode = (parentAl?.layoutMode as string) || (_parent.layoutMode as string);
      if (parentMode === 'VERTICAL') {
        const name = ((n.name as string) || '').toLowerCase();
        const isStatusBar = name.includes('status bar') || name.includes('statusbar');
        const isSkip = /icon|chevron|dot|badge|tag|chip|indicator|fab|tab.?bar/i.test(name);
        const w = n.width as number | undefined;
        const isSmallFixed = typeof w === 'number' && w <= 60;
        if (!isStatusBar && !isSkip && !isSmallFixed) {
          n.layoutSizingHorizontal = 'FILL';
          if (isRootChild) {
            console.log(`[enforce] Root child "${n.name}" layoutSizingHorizontal forced: FILL`);
          } else {
            console.log(`[enforce] VERTICAL parent child "${n.name}" layoutSizingHorizontal forced: FILL`);
          }
          stats.sizing++;
        }
      }
    }

    // ── 5e-pre. Badge/Tag/Chip은 반드시 HUG ──
    if (n.type === 'frame') {
      const name = ((n.name as string) || '').toLowerCase();
      const isBadgeOrTag = /badge|tag|chip|label.*badge|뱃지|태그|칩/.test(name);
      if (isBadgeOrTag && n.layoutSizingHorizontal && n.layoutSizingHorizontal !== 'HUG') {
        console.log(`[enforce] Badge/Tag "${n.name}" layoutSizingHorizontal: ${n.layoutSizingHorizontal} → HUG`);
        n.layoutSizingHorizontal = 'HUG';
        stats.sizing++;
      }
    }

    // ── 5e. 규칙 F — Content 영역 FILL height ──
    if (n.type === 'frame') {
      const name = ((n.name as string) || '').toLowerCase();
      const contentNames = ['content', 'body', 'main', 'scroll', '리스트', '목록', '콘텐츠', '본문'];
      const isContentArea = contentNames.some(cn => name.includes(cn));
      if (isContentArea && !n.layoutSizingVertical) {
        n.layoutSizingVertical = 'FILL';
        console.log(`[enforce] Content area "${n.name}" layoutSizingVertical forced: FILL`);
        stats.sizing++;
      }
    }

    // ── 5f. 규칙 H — 단일 text 자식 중앙 정렬 ──
    if (n.type === 'frame' && Array.isArray(n.children)) {
      const children = n.children as Record<string, unknown>[];
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (al?.layoutMode === 'HORIZONTAL' && children.length === 1 && children[0].type === 'text') {
        // 버튼/배지 패턴: 부모에 CENTER 정렬 추가
        if (!al.counterAxisAlignItems) {
          al.counterAxisAlignItems = 'CENTER';
          console.log(`[enforce] Single-text frame "${n.name}" counterAxis forced: CENTER`);
          stats.alignment++;
        }
        if (!al.primaryAxisAlignItems) {
          al.primaryAxisAlignItems = 'CENTER';
          console.log(`[enforce] Single-text frame "${n.name}" primaryAxis forced: CENTER`);
          stats.alignment++;
        }
      }
    }

    // ── 5g. 규칙 I — 아이콘 래퍼 프레임 정사각형 강제 ──
    // 아이콘 1개만 감싸는 프레임(배경색 있음)은 반드시 정사각형이어야 함
    if (n.type === 'frame' && Array.isArray(n.children) && n.fill) {
      const children = n.children as Record<string, unknown>[];
      const iconChild = children.length === 1 && children[0].type === 'icon' ? children[0] : null;
      if (iconChild) {
        const iconSize = (iconChild.size as number) || 24;
        const w = n.width as number | undefined;
        const h = n.height as number | undefined;
        // Case 1: no explicit size → force square
        // Case 2: non-square → force to max(w, h) or icon + padding
        if (!w || !h || w !== h) {
          const desiredSize = Math.max(w || 0, h || 0, iconSize + 24); // icon + 12px padding each side
          n.width = desiredSize;
          n.height = desiredSize;
          console.log(`[enforce] Icon wrapper "${n.name}" forced square: ${desiredSize}×${desiredSize}`);
          stats.sizing++;
        }
        // Ensure center alignment
        const al = n.autoLayout as Record<string, unknown> | undefined;
        if (al) {
          al.primaryAxisAlignItems = 'CENTER';
          al.counterAxisAlignItems = 'CENTER';
        }
      }
    }

    // ── 5h. 규칙 J — 탭바 내 Pill/아이템 간격 강제 ──
    // Pill 컨테이너(탭바 내부)의 children에 FILL 강제
    if (n.type === 'frame' && Array.isArray(n.children)) {
      const name = ((n.name as string) || '').toLowerCase();
      const isPill = name.includes('pill') || name.includes('nav') || name.includes('탭');
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (isPill && al?.layoutMode === 'HORIZONTAL') {
        const pillChildren = n.children as Record<string, unknown>[];
        const allFrames = pillChildren.every(c => c.type === 'frame');
        if (allFrames && pillChildren.length >= 3) {
          // Pill 안의 탭 아이템들 → FILL width 강제
          for (const tab of pillChildren) {
            if (!tab.layoutSizingHorizontal || tab.layoutSizingHorizontal !== 'FILL') {
              tab.layoutSizingHorizontal = 'FILL';
              stats.sizing++;
            }
            if (!tab.layoutSizingVertical || tab.layoutSizingVertical !== 'FILL') {
              tab.layoutSizingVertical = 'FILL';
              stats.sizing++;
            }
          }
          console.log(`[enforce] Pill "${n.name}" children forced FILL: ${pillChildren.length} tabs`);
        }
      }
    }

    // ── 6. Hero section: padding + height + imageGenHint ──
    if (isHeroSection(n)) {
      // 6a. 좌우 패딩 강제 (Content 영역과 일관성)
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (al) {
        if (!al.paddingLeft && !al.paddingRight) {
          al.paddingLeft = 24;
          al.paddingRight = 24;
          console.log(`[enforce] Hero "${n.name}" padding forced: 24px left/right`);
          stats.structure++;
        }
      } else if (!n.padding) {
        // autoLayout 없는 경우 padding 배열로 설정
        n.padding = [20, 24, 20, 24]; // top, right, bottom, left
        console.log(`[enforce] Hero "${n.name}" padding array forced: [20, 24, 20, 24]`);
        stats.structure++;
      }

      // 6b. 높이 200px 강제
      if (!n.height || (n.height as number) < 180 || (n.height as number) > 220) {
        n.height = 200;
        console.log(`[enforce] Hero "${n.name}" height forced: 200`);
        stats.structure++;
      }

      // 6c. imageGenHint 자동 추가 — Banner Card 자식이 있으면 그곳에, 없으면 Hero Section에
      if (!n.imageGenHint) {
        const heroText = collectAllText(n);
        const hint = {
          prompt: `soft gradient background with abstract shapes, modern minimal style, matching the theme: ${heroText.slice(0, 60)}`,
          isHero: true,
        };
        // Banner Card 탐색: 자식 중 'banner' 또는 'card' 이름을 가진 프레임
        const children = (n.children as Record<string, unknown>[] | undefined) || [];
        const bannerCard = children.find(c => {
          const cName = ((c.name as string) || '').toLowerCase();
          return c.type === 'frame' && (cName.includes('banner') || cName.includes('card'));
        });
        if (bannerCard && !bannerCard.imageGenHint) {
          bannerCard.imageGenHint = hint;
          console.log(`[enforce] Added imageGenHint to Banner Card "${bannerCard.name}" (inside hero "${n.name}")`);
        } else if (!bannerCard) {
          n.imageGenHint = hint;
          console.log(`[enforce] Added imageGenHint to hero section "${n.name}" (no Banner Card found)`);
        }
      }
    }

    // ── Recurse children ──
    if (Array.isArray(n.children)) {
      n.children = (n.children as Record<string, unknown>[]).map(child =>
        enhance(child, n, false)
      );
    }

    return n;
  }

  // 루트 자식들은 isRootChild=true로 호출
  if (Array.isArray(root.children)) {
    root.children = (root.children as Record<string, unknown>[]).map(child =>
      enhance(child, root, true)
    );
  }
  // 루트 자신에 대해서도 색상 정규화 적용
  normalizeNodeColors(root);

  const totalCorrections = Object.values(stats).reduce((a, b) => a + b, 0);
  console.log(`[enforce] Blueprint enforcement complete: ${JSON.stringify(stats)} (${totalCorrections} total corrections, ${tintColorIdx} icons processed)`);
  return root;
}

/** 이모지 → DS-1 아이콘 매핑 */
const EMOJI_TO_ICON_MAP: Record<string, string> = {
  '🏠': 'home-01', '🏡': 'home-01', '🏢': 'home-02',
  '🔍': 'search-lg', '🔎': 'search-lg',
  '🔔': 'bell-01', '🔕': 'bell-01',
  '❤️': 'heart', '💜': 'heart', '💙': 'heart', '🧡': 'heart', '💛': 'heart', '💚': 'heart',
  '⭐': 'star-01', '🌟': 'star-01', '⭐️': 'star-01',
  '📱': 'phone-call-01', '📞': 'phone-call-01', '☎️': 'phone-call-01',
  '✉️': 'mail-01', '📧': 'mail-01', '📨': 'mail-01', '📩': 'mail-01',
  '🛒': 'shopping-cart-01', '🛍️': 'shopping-bag-01', '🛍': 'shopping-bag-01',
  '💰': 'currency-dollar-circle', '💵': 'currency-dollar-circle', '💳': 'credit-card-01', '💲': 'currency-dollar-circle',
  '🎁': 'gift-01', '🎀': 'gift-01',
  '👤': 'user-01', '👥': 'users-01', '🧑': 'user-01', '👨': 'user-01', '👩': 'user-01',
  '⚙️': 'settings-01', '🔧': 'settings-01', '🔨': 'settings-01',
  '🔒': 'lock-01', '🔓': 'lock-unlocked-01',
  '📅': 'calendar', '🗓️': 'calendar', '📆': 'calendar',
  '⏰': 'clock', '🕐': 'clock', '⏱️': 'clock',
  '🌍': 'globe-01', '🌎': 'globe-01', '🌏': 'globe-01',
  '🔗': 'link-01',
  '📸': 'camera-01', '📷': 'camera-01',
  '🖼️': 'image-01', '🖼': 'image-01',
  '✏️': 'edit-01', '📝': 'edit-01',
  '🗑️': 'trash-01', '🗑': 'trash-01',
  '📋': 'copy-01',
  '🔖': 'bookmark', '📌': 'bookmark',
  '🏷️': 'tag-01', '🏷': 'tag-01',
  '🚀': 'rocket-01',
  '📊': 'bar-chart-square-01', '📈': 'trend-up-01', '📉': 'trend-down-01',
  '✅': 'check-circle', '✔️': 'check',
  '❌': 'x-close', '⚠️': 'alert-triangle', 'ℹ️': 'info-circle', '❓': 'help-circle',
  '➕': 'plus', '➖': 'minus',
  '⬆️': 'arrow-up', '⬇️': 'arrow-down', '⬅️': 'arrow-left', '➡️': 'arrow-right',
  '▶️': 'play-circle', '⏸️': 'pause-circle',
  '🎵': 'music-note-01', '🎶': 'music-note-01',
  '📤': 'upload-01', '📥': 'download-04',
  '🔊': 'volume-max', '🎤': 'microphone-01',
  '🏅': 'award-01', '🏆': 'trophy-01', '🎯': 'target-01',
  '📖': 'book-open-01', '📚': 'book-open-01', '📕': 'book-open-01',
  '🎪': 'flag-01', '🎨': 'palette',
  '🏃': 'activity', '🏋️': 'activity', '💪': 'activity',
  '🎮': 'gaming-pad-01', '🕹️': 'gaming-pad-01',
  '✈️': 'plane', '🚗': 'car-01',
  '🍽️': 'coffee', '☕': 'coffee', '🍔': 'coffee',
  '💡': 'lightbulb-02',
  '🎉': 'celebration', '🥳': 'celebration', '🎊': 'celebration',
  '🔥': 'flame',
  '💬': 'message-circle-01', '💭': 'message-circle-01',
  '👍': 'thumbs-up', '👎': 'thumbs-down',
  '🧾': 'receipt',
  '📄': 'file-04', '📁': 'folder',
  '🎬': 'video-recorder', '🎥': 'video-recorder',
  '🩺': 'heart-hand', '💊': 'heart-hand',
  '🌱': 'leaf-01',
};

/** 이모지에서 아이콘 이름을 추측 (매핑에 없는 경우) */
function guessIconFromEmoji(_emoji: string): string | null {
  // EMOJI_TO_ICON_MAP에 없으면 null
  return null;
}

/** 이모지만 있는 텍스트인지 판별 */
function isEmojiOnlyText(n: Record<string, unknown>): boolean {
  if (n.type !== 'text' || !n.text) return false;
  const text = (n.text as string).trim();
  if (text.length === 0 || text.length > 10) return false;
  // Remove emoji, variation selectors, ZWJ, etc. If nothing remains, it's emoji-only
  const stripped = text.replace(/[\p{Emoji_Presentation}\p{Emoji}\uFE0F\u200D\u20E3\u{E0061}-\u{E007A}\u{E007F}]/gu, '').trim();
  return stripped.length === 0;
}

/** hex → {r,g,b,a} 변환. 0-255 범위도 0-1로 정규화 */
function normalizeColor(color: unknown): Record<string, number> | null {
  if (!color) return null;
  // 이미 {r,g,b} 객체
  if (typeof color === 'object' && color !== null && 'r' in color) {
    const c = color as Record<string, number>;
    let r = typeof c.r === 'number' ? c.r : 0;
    let g = typeof c.g === 'number' ? c.g : 0;
    let b = typeof c.b === 'number' ? c.b : 0;
    let a = typeof c.a === 'number' ? c.a : 1;
    // 0-255 범위 → 0-1 정규화
    if (r > 1 || g > 1 || b > 1) {
      r = r / 255;
      g = g / 255;
      b = b / 255;
    }
    return { r: Math.min(1, Math.max(0, r)), g: Math.min(1, Math.max(0, g)), b: Math.min(1, Math.max(0, b)), a: Math.min(1, Math.max(0, a)) };
  }
  // hex string
  if (typeof color === 'string') {
    const hex = color.replace('#', '');
    if (!/^[0-9a-fA-F]{3,8}$/.test(hex)) return null;
    let r: number, g: number, b: number, a = 1;
    if (hex.length === 3) {
      r = parseInt(hex[0] + hex[0], 16) / 255;
      g = parseInt(hex[1] + hex[1], 16) / 255;
      b = parseInt(hex[2] + hex[2], 16) / 255;
    } else if (hex.length === 6) {
      r = parseInt(hex.slice(0, 2), 16) / 255;
      g = parseInt(hex.slice(2, 4), 16) / 255;
      b = parseInt(hex.slice(4, 6), 16) / 255;
    } else if (hex.length === 8) {
      r = parseInt(hex.slice(0, 2), 16) / 255;
      g = parseInt(hex.slice(2, 4), 16) / 255;
      b = parseInt(hex.slice(4, 6), 16) / 255;
      a = parseInt(hex.slice(6, 8), 16) / 255;
    } else {
      return null;
    }
    return { r, g, b, a };
  }
  return null;
}

/** 한글 포함 여부 */
function containsKorean(text: string): boolean {
  return /[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F\uA960-\uA97F\uD7B0-\uD7FF]/.test(text);
}

/** 한글 미지원 폰트 목록 */
const NON_KOREAN_FONTS = ['inter', 'roboto', 'arial', 'dm sans', 'bricolage grotesque', 'bricolage', 'helvetica', 'sf pro', 'poppins', 'open sans', 'lato', 'montserrat', 'nunito', 'raleway', 'oswald'];

/** 모바일 루트 프레임 판별 */
function isMobileRootFrame(n: Record<string, unknown>): boolean {
  const w = n.width as number;
  const h = n.height as number;
  return n.type === 'frame' &&
    typeof w === 'number' && w >= 360 && w <= 430 &&
    typeof h === 'number' && h >= 700;
}

// ── Detection helpers ──

function isSmallRectangle(n: Record<string, unknown>): boolean {
  return isSmallPlaceholder(n) && n.type === 'rectangle';
}

/** rectangle 또는 ellipse — 아이콘 placeholder로 의심되는 작은 도형 */
function isSmallPlaceholder(n: Record<string, unknown>): boolean {
  if ((n.type !== 'rectangle' && n.type !== 'ellipse') || n.children) return false;
  const w = n.width as number;
  const h = n.height as number;
  if (typeof w !== 'number' || typeof h !== 'number') return false;
  if (w > 60 || h > 60) return false;
  // Skip small decorative elements: status bar indicators, dots, thin dividers
  // Real icon placeholders are typically ≥16px on both dimensions
  if (w < 16 || h < 16) return false;
  // Skip extreme aspect ratios (dividers, lines) — must be roughly square-ish
  const ratio = Math.max(w, h) / Math.min(w, h);
  if (ratio > 2.5) return false;
  return true;
}

function isInsideListItem(_n: Record<string, unknown>, parent?: Record<string, unknown>): boolean {
  if (!parent) return false;
  const al = parent.autoLayout as Record<string, unknown> | undefined;
  return al?.layoutMode === 'HORIZONTAL' && isListItemWithPlaceholderIcon(parent);
}

function isTabBar(n: Record<string, unknown>): boolean {
  const name = ((n.name as string) || '').toLowerCase();
  const children = n.children as Record<string, unknown>[] | undefined;
  if (!children || children.length < 2) return false;

  // Tab bars: horizontal, 3-5 children, near bottom (height ~50-90)
  const al = n.autoLayout as Record<string, unknown> | undefined;
  const isHorizontal = al?.layoutMode === 'HORIZONTAL';
  const isTabLike = name.includes('tab') || name.includes('탭') ||
    name.includes('nav') || name.includes('bottom') || name.includes('하단');
  const hasTabCount = children.length >= 3 && children.length <= 6;
  const height = n.height as number;
  const isTabHeight = typeof height === 'number' && height >= 48 && height <= 100;

  // Each child should have text content (tab labels)
  const hasTextChildren = children.some(c => {
    const cc = c.children as Record<string, unknown>[] | undefined;
    return cc?.some(gc => gc.type === 'text') || c.type === 'text';
  });

  return (isHorizontal || isTabLike) && hasTabCount && hasTextChildren && (isTabLike || isTabHeight);
}

function isListItemWithPlaceholderIcon(n: Record<string, unknown>): boolean {
  const al = n.autoLayout as Record<string, unknown> | undefined;
  if (al?.layoutMode !== 'HORIZONTAL') return false;

  const children = n.children as Record<string, unknown>[] | undefined;
  if (!children || children.length < 2) return false;

  // Has at least one small placeholder (rectangle or ellipse) and at least one text/frame sibling
  const hasPlaceholder = children.some(c => isSmallPlaceholder(c));
  // Also detect emoji text as icon placeholder
  const hasEmoji = children.some(c => isEmojiOnlyText(c));
  const hasTextContent = children.some(c =>
    (c.type === 'text' && !isEmojiOnlyText(c)) ||
    (c.type === 'frame' && (c.children as Record<string, unknown>[] | undefined)?.some(gc => gc.type === 'text'))
  );

  return (hasPlaceholder || hasEmoji) && hasTextContent;
}

// Keep backward compat alias
function isListItemWithRectIcon(n: Record<string, unknown>): boolean {
  return isListItemWithPlaceholderIcon(n);
}

function isHeroSection(n: Record<string, unknown>): boolean {
  const name = ((n.name as string) || '').toLowerCase();
  const width = n.width as number;
  const height = n.height as number;
  const isLargeFrame = n.type === 'frame' &&
    typeof width === 'number' && width >= 300 &&
    typeof height === 'number' && height >= 120 && height <= 280;
  const isHeroNamed = name.includes('hero') || name.includes('banner') || name.includes('히어로') || name.includes('배너');
  const hasDarkFill = n.fill && typeof n.fill === 'object' &&
    (n.fill as Record<string, number>).r < 0.3;

  return isLargeFrame && (isHeroNamed || hasDarkFill);
}

// ── Context text extraction ──

function getContextText(n: Record<string, unknown>, parent?: Record<string, unknown>): string {
  const parts: string[] = [];
  // Node name
  if (n.name) parts.push(n.name as string);
  // Sibling text in parent
  if (parent && Array.isArray(parent.children)) {
    for (const sibling of parent.children as Record<string, unknown>[]) {
      if (sibling.type === 'text' && sibling.text) {
        parts.push(sibling.text as string);
      }
      // Text inside frame siblings
      if (sibling.type === 'frame' && Array.isArray(sibling.children)) {
        for (const gc of sibling.children as Record<string, unknown>[]) {
          if (gc.type === 'text' && gc.text) {
            parts.push(gc.text as string);
          }
        }
      }
    }
  }
  // Parent name
  if (parent?.name) parts.push(parent.name as string);
  return parts.join(' ');
}

function collectAllText(n: Record<string, unknown>): string {
  const parts: string[] = [];
  if (n.type === 'text' && n.text) parts.push(n.text as string);
  if (n.name) parts.push(n.name as string);
  if (Array.isArray(n.children)) {
    for (const child of n.children as Record<string, unknown>[]) {
      parts.push(collectAllText(child));
    }
  }
  return parts.join(' ');
}

function guessIconFromText(text: string): string | null {
  const lower = text.toLowerCase();
  for (const [keyword, iconName] of Object.entries(ICON_KEYWORD_MAP)) {
    if (lower.includes(keyword)) return iconName;
  }
  return null;
}

// ── Conversion helpers ──

function convertToIconBg(n: Record<string, unknown>, iconName: string, tintColor: Record<string, number>): void {
  const bgSize = 44;
  n.type = 'frame';
  n.width = bgSize;
  n.height = bgSize;
  n.cornerRadius = 12;
  n.fill = tintColor;
  n.autoLayout = {
    layoutMode: 'VERTICAL',
    primaryAxisAlignItems: 'CENTER',
    counterAxisAlignItems: 'CENTER',
  };
  n.children = [{
    type: 'icon',
    name: iconName,
    size: 24,
  }];
  // Clean rectangle properties
  delete n.stroke;
  delete n.strokeWeight;
}

function convertListItemIcon(listItem: Record<string, unknown>, colorIdx: number): void {
  const children = listItem.children as Record<string, unknown>[];
  if (!children) return;

  // Find the placeholder to convert: rectangle, ellipse, or emoji text
  let placeholderIdx = children.findIndex(c => isSmallPlaceholder(c));
  if (placeholderIdx === -1) {
    // Try emoji text
    placeholderIdx = children.findIndex(c => isEmojiOnlyText(c));
  }
  if (placeholderIdx === -1) return;

  const placeholder = children[placeholderIdx];
  const tintColor = ICON_TINT_COLORS[colorIdx % ICON_TINT_COLORS.length];

  // If placeholder is emoji text, use emoji mapping first
  let iconName: string;
  if (isEmojiOnlyText(placeholder)) {
    const emoji = (placeholder.text as string).trim();
    iconName = EMOJI_TO_ICON_MAP[emoji] || guessIconFromText(getContextText(placeholder, listItem)) || 'star-01';
    console.log(`[enhance] List item emoji "${emoji}" → ${iconName}`);
  } else {
    const contextText = getContextText(placeholder, listItem);
    iconName = guessIconFromText(contextText) || 'star-01';
    console.log(`[enhance] List item icon: "${contextText.slice(0, 30)}" → ${iconName}`);
  }

  // Convert in-place to icon bg frame
  convertToIconBg(children[placeholderIdx], iconName, tintColor);
}

function fixTabBar(tabBar: Record<string, unknown>): void {
  const children = tabBar.children as Record<string, unknown>[];
  if (!children) return;

  for (const tab of children) {
    const tabChildren = tab.children as Record<string, unknown>[] | undefined;
    if (!tabChildren) continue;

    // Find text label in this tab (non-emoji text)
    let label = '';
    for (const c of tabChildren) {
      if (c.type === 'text' && c.text && !isEmojiOnlyText(c)) {
        label = (c.text as string).toLowerCase();
        break;
      }
    }

    // Find placeholder in this tab: rectangle, ellipse, or emoji text
    let placeholderIdx = tabChildren.findIndex(c => isSmallPlaceholder(c));
    if (placeholderIdx === -1) {
      placeholderIdx = tabChildren.findIndex(c => isEmojiOnlyText(c));
    }

    // Also check if tab has NO icon at all (only text children, no icon/clone/svg_icon)
    const hasRealIcon = tabChildren.some(c =>
      c.type === 'icon' || c.type === 'clone' || c.type === 'svg_icon'
    );

    if (placeholderIdx !== -1) {
      let iconName: string;
      const placeholder = tabChildren[placeholderIdx];
      if (isEmojiOnlyText(placeholder)) {
        const emoji = (placeholder.text as string).trim();
        iconName = EMOJI_TO_ICON_MAP[emoji] || TAB_ICON_MAP[label] || guessIconFromText(label) || 'star-01';
        console.log(`[enhance] Tab emoji "${emoji}" → ${iconName} (label: "${label}")`);
      } else {
        iconName = TAB_ICON_MAP[label] || guessIconFromText(label) || 'star-01';
        console.log(`[enhance] Tab icon: "${label}" → ${iconName}`);
      }
      tabChildren[placeholderIdx] = {
        type: 'icon',
        name: iconName,
        size: 24,
      };
    } else if (!hasRealIcon && label) {
      // No icon at all — inject one at the beginning
      const iconName = TAB_ICON_MAP[label] || guessIconFromText(label) || 'star-01';
      tabChildren.unshift({
        type: 'icon',
        name: iconName,
        size: 24,
      } as Record<string, unknown>);
      console.log(`[enhance] Tab missing icon, injected: "${label}" → ${iconName}`);
    }
  }
}

export async function prefetchImages(nodes: unknown[]): Promise<void> {
  const promises: Promise<void>[] = [];

  function collect(node: Record<string, unknown>) {
    const imageFill = node.imageFill as Record<string, unknown> | undefined;
    if (imageFill?.url) {
      promises.push(
        fetchImageAsBase64(imageFill.url as string).then((base64) => {
          if (base64) node.imageData = base64;
        })
      );
    }
    // SVG icon prefetch: download SVG text from GitHub
    if (node.type === 'svg_icon' && node.svgUrl) {
      promises.push(
        fetch(node.svgUrl as string)
          .then(r => r.ok ? r.text() : Promise.reject(`HTTP ${r.status}`))
          .then(svg => { node.svgData = svg; })
          .catch(err => {
            console.warn(`[prefetch] SVG fetch failed for ${node.svgUrl}: ${err}`);
          })
      );
    }
    const children = node.children as unknown[] | undefined;
    if (children) {
      for (const child of children) {
        collect(child as Record<string, unknown>);
      }
    }
  }

  for (const node of nodes) {
    collect(node as Record<string, unknown>);
  }
  await Promise.all(promises);
}
