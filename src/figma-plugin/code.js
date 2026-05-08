// Figma Design Agent Plugin
// Based on claude-talk-to-figma-mcp plugin, modified for auto-connect

// Plugin state
const state = {
  serverPort: 8767, // Fixed port for Figma Design Agent
};

// ★ Component Cache — persists across builds for instant lookups
const componentCache = new Map(); // componentKey → ComponentNode

// Get component from cache (O(1)) or import as fallback
async function getCachedComponent(componentKey) {
  if (componentCache.has(componentKey)) {
    return componentCache.get(componentKey);
  }
  // Fallback: single import
  try {
    const comp = await figma.importComponentByKeyAsync(componentKey);
    componentCache.set(componentKey, comp);
    return comp;
  } catch (e) {
    console.warn(`[cache] Import failed for ${componentKey}: ${e.message}`);
    return null;
  }
}

// Helper function for progress updates
function sendProgressUpdate(commandId, commandType, status, progress, totalItems, processedItems, message, payload = null) {
  const update = {
    type: 'command_progress',
    commandId,
    commandType,
    status,
    progress,
    totalItems,
    processedItems,
    message,
    timestamp: Date.now()
  };

  // Add optional chunk information if present
  if (payload) {
    if (payload.currentChunk !== undefined && payload.totalChunks !== undefined) {
      update.currentChunk = payload.currentChunk;
      update.totalChunks = payload.totalChunks;
      update.chunkSize = payload.chunkSize;
    }
    update.payload = payload;
  }

  // Send to UI
  figma.ui.postMessage(update);
  console.log(`Progress update: ${status} - ${progress}% - ${message}`);

  return update;
}

// Show UI
figma.showUI(__html__, { width: 300, height: 200, visible: true });

// Auto-connect on plugin start
setTimeout(() => {
  figma.ui.postMessage({
    type: "auto-connect",
    documentId: figma.fileKey || figma.root.id,
    documentName: figma.root.name,
  });
}, 500);

// Plugin commands from UI
figma.ui.onmessage = async (msg) => {
  switch (msg.type) {
    case "update-settings":
      updateSettings(msg);
      break;
    case "notify":
      figma.notify(msg.message);
      break;
    case "close-plugin":
      figma.closePlugin();
      break;
    case "execute-command":
      // Execute commands received from UI (which gets them from WebSocket)
      try {
        const result = await handleCommand(msg.command, msg.params);
        // Send result back to UI
        figma.ui.postMessage({
          type: "command-result",
          id: msg.id,
          result,
        });
      } catch (error) {
        figma.ui.postMessage({
          type: "command-error",
          id: msg.id,
          error: error.message || "Error executing command",
        });
      }
      break;
  }
};

// Listen for plugin commands from menu
figma.on("run", ({ command }) => {
  figma.ui.postMessage({
    type: "auto-connect",
    documentId: figma.fileKey || figma.root.id,
    documentName: figma.root.name,
  });
});

// Update plugin settings
function updateSettings(settings) {
  if (settings.serverPort) {
    state.serverPort = settings.serverPort;
  }

  figma.clientStorage.setAsync("settings", {
    serverPort: state.serverPort,
  });
}

// Handle commands from UI
// Force Figma to reflow stale auto-layout positions by selecting every
// FRAME / INSTANCE / GROUP / COMPONENT under a root, then clearing the
// selection. Without this, freshly built nodes can render at outdated
// positions until a user clicks one (the act of selecting triggers
// Figma's internal layout recalculation). 2026-05-08 fix per user
// observation: "5월" text drifted right in Schedule Title row until
// the row was double-clicked, after which it snapped back.
async function triggerLayoutReflow(params) {
  const rootId = params && params.nodeId;
  if (!rootId) {
    throw new Error("trigger_reflow: missing nodeId");
  }
  const root = await figma.getNodeByIdAsync(rootId);
  if (!root) {
    throw new Error("trigger_reflow: node not found: " + rootId);
  }
  const all = [];
  function walk(n) {
    if (!n) return;
    const t = n.type;
    if (t === "FRAME" || t === "INSTANCE" || t === "GROUP" || t === "COMPONENT" || t === "COMPONENT_SET") {
      all.push(n);
    }
    if ("children" in n) {
      for (var i = 0; i < n.children.length; i++) {
        walk(n.children[i]);
      }
    }
  }
  walk(root);
  // Bulk-select to flush layout cache, then restore previous selection.
  const prev = figma.currentPage.selection || [];
  try {
    figma.currentPage.selection = all;
    // Brief tick so Figma processes the selection change
    await new Promise(function (r) { setTimeout(r, 30); });
  } finally {
    figma.currentPage.selection = prev;
  }
  return { reflowedFrames: all.length };
}


async function handleCommand(command, params) {
  switch (command) {
    case "ping_check":
      return { ok: true, timestamp: Date.now() };
    case "trigger_reflow":
      return await triggerLayoutReflow(params);
    case "get_document_info":
      return await getDocumentInfo();
    case "get_selection":
      return await getSelection();
    case "get_node_info":
      if (!params || !params.nodeId) {
        throw new Error("Missing nodeId parameter");
      }
      return await getNodeInfo(params.nodeId, params.depth);
    case "get_nodes_info":
      if (!params || !params.nodeIds || !Array.isArray(params.nodeIds)) {
        throw new Error("Missing or invalid nodeIds parameter");
      }
      return await getNodesInfo(params.nodeIds);
    case "create_rectangle":
      return await createRectangle(params);
    case "create_frame":
      return await createFrame(params);
    case "create_text":
      return await createText(params);
    case "set_fill_color":
      return await setFillColor(params);
    case "set_stroke_color":
      return await setStrokeColor(params);
    case "set_selection_colors":
      return await setSelectionColors(params);
    case "move_node":
      return await moveNode(params);
    case "resize_node":
      return await resizeNode(params);
    case "delete_node":
      return await deleteNode(params);
    case "get_styles":
      return await getStyles();
    case "get_local_components":
      return await getLocalComponents();
    case "get_local_component_sets":
      return await getLocalComponentSets();
    // case "get_team_components":
    //   return await getTeamComponents();
    case "create_component_instance":
      return await createComponentInstance(params);
    case "get_instance_properties":
      return await getInstanceProperties(params);
    case "set_instance_properties":
      return await setInstanceProperties(params);
    case "export_node_as_image":
      return await exportNodeAsImage(params);
    case "set_corner_radius":
      return await setCornerRadius(params);
    case "set_text_content":
      return await setTextContent(params);
    case "clone_node":
      return await cloneNode(params);
    case "scan_text_nodes":
      return await scanTextNodes(params);
    case "set_multiple_text_contents":
      return await setMultipleTextContents(params);
    case "set_auto_layout":
      return await setAutoLayout(params);
    case "set_layout_sizing":
      return await setLayoutSizing(params);
    case "set_layout_sizing_batch":
      return await setLayoutSizingBatch(params);
    case "set_layout_positioning":
      return await setLayoutPositioning(params);
    // Consolidated text properties command
    case "set_text_properties":
      return await setTextProperties(params);
    // Individual text property commands (kept for batch_execute backward compatibility)
    case "set_font_name":
      return await setFontName(params);
    case "set_font_size":
      return await setFontSize(params);
    case "set_range_font_size":
      return await setRangeFontSize(params);
    case "set_font_weight":
      return await setFontWeight(params);
    case "set_letter_spacing":
      return await setLetterSpacing(params);
    case "set_line_height":
      return await setLineHeight(params);
    case "set_paragraph_spacing":
      return await setParagraphSpacing(params);
    case "set_text_case":
      return await setTextCase(params);
    case "set_text_decoration":
      return await setTextDecoration(params);
    case "set_text_align":
      return await setTextAlign(params);
    case "get_styled_text_segments":
      return await getStyledTextSegments(params);
    case "load_font_async":
      return await loadFontAsyncWrapper(params);
    case "get_remote_components":
      return await getRemoteComponents(params);
    case "set_effects":
      return await setEffects(params);
    case "set_effect_style_id":
      return await setEffectStyleId(params);
    case "set_text_style_id":
      return await setTextStyleId(params);
    case "group_nodes":
      return await groupNodes(params);
    case "ungroup_nodes":
      return await ungroupNodes(params);
    case "flatten_node":
      return await flattenNode(params);
    case "insert_child":
      return await insertChild(params);
    case "create_ellipse":
      return await createEllipse(params);
    case "create_polygon":
      return await createPolygon(params);
    case "create_star":
      return await createStar(params);
    case "create_vector":
      return await createVector(params);
    case "create_line":
      return await createLine(params);
    case "create_component_from_node":
      return await createComponentFromNode(params);
    case "create_component_set":
      return await createComponentSet(params);
    case "create_page":
      return await createPage(params);
    case "delete_page":
      return await deletePage(params);
    case "rename_page":
      return await renamePage(params);
    case "get_pages":
      return await getPages();
    case "set_current_page":
      return await setCurrentPage(params);
    case "rename_node":
      return await renameNode(params);
    case "find_components_by_name":
      return await findComponentsByName(params);
    case "get_component_key":
      return await getComponentKey(params);
    case "search_library_components":
      return await searchLibraryComponents(params);
    case "scan_instances_for_swap":
      return await scanInstancesForSwap(params);
    case "set_image_fill":
      return await setImageFill(params);
    case "get_local_variables":
      return await getLocalVariables(params);
    case "get_bound_variables":
      return await getBoundVariables(params);
    case "set_bound_variables":
      return await setBoundVariables(params);
    case "batch_bind_variables":
      return await batchBindVariables(params);
    case "batch_set_text_style_id":
      return await batchSetTextStyleId(params);
    case "batch_build_screen":
      return await batchBuildScreen(params);
    case "pre_cache_components":
      return await preCacheAllComponents(params);
    case "clear_component_cache":
      return clearComponentCache();
    case "batch_execute":
      return await batchExecute(params);
    default:
      throw new Error(`Unknown command: ${command}`);
  }
};

// Command implementations

async function getDocumentInfo() {
  await figma.currentPage.loadAsync();
  const page = figma.currentPage;
  // Return ALL pages in the document, not just the current one
  // Note: other pages may not be loaded, so avoid accessing .children on them
  const allPages = [];
  for (const p of figma.root.children) {
    try {
      await p.loadAsync();
      allPages.push({
        id: p.id,
        name: p.name,
        childCount: p.children.length,
      });
    } catch (e) {
      // If page can't be loaded, still include it with childCount -1
      allPages.push({
        id: p.id,
        name: p.name,
        childCount: -1,
      });
    }
  }
  return {
    name: page.name,
    id: page.id,
    type: page.type,
    children: page.children.map((node) => ({
      id: node.id,
      name: node.name,
      type: node.type,
    })),
    currentPage: {
      id: page.id,
      name: page.name,
      childCount: page.children.length,
    },
    pages: allPages,
  };
}

async function getSelection() {
  return {
    selectionCount: figma.currentPage.selection.length,
    selection: figma.currentPage.selection.map((node) => ({
      id: node.id,
      name: node.name,
      type: node.type,
      visible: node.visible,
    })),
  };
}

async function getNodeInfo(nodeId, maxDepth) {
  var node = await figma.getNodeByIdAsync(nodeId);

  if (!node) {
    throw new Error("Node not found with ID: " + nodeId);
  }

  // Always use collectNodeInfo with bounded depth (safe, predictable size)
  var depth = (maxDepth !== undefined && maxDepth !== null) ? maxDepth : 2;
  if (depth > 5) depth = 5; // Hard cap to prevent huge payloads
  return collectNodeInfo(node, depth, 0);
}

// Collect node properties with depth-limited recursion
function collectNodeInfo(node, maxDepth, currentDepth) {
  if (maxDepth === undefined) maxDepth = 3;
  if (currentDepth === undefined) currentDepth = 0;
  var info = {
    id: node.id,
    name: node.name,
    type: node.type,
    visible: node.visible,
  };

  // Parent ID (needed for hero image escalation etc.)
  if (node.parent) {
    info.parentId = node.parent.id;
  }

  // Position & size
  if ("x" in node) info.x = node.x;
  if ("y" in node) info.y = node.y;
  if ("width" in node) info.width = node.width;
  if ("height" in node) info.height = node.height;

  // Layout properties
  if ("layoutMode" in node && node.layoutMode !== "NONE") {
    info.layoutMode = node.layoutMode;
    info.primaryAxisAlignItems = node.primaryAxisAlignItems;
    info.counterAxisAlignItems = node.counterAxisAlignItems;
    info.itemSpacing = node.itemSpacing;
    info.paddingTop = node.paddingTop;
    info.paddingBottom = node.paddingBottom;
    info.paddingLeft = node.paddingLeft;
    info.paddingRight = node.paddingRight;
  }

  // Sizing
  if ("layoutSizingHorizontal" in node) info.layoutSizingHorizontal = node.layoutSizingHorizontal;
  if ("layoutSizingVertical" in node) info.layoutSizingVertical = node.layoutSizingVertical;

  // Layout positioning (AUTO or ABSOLUTE)
  if ("layoutPositioning" in node) info.layoutPositioning = node.layoutPositioning;

  // Fills & strokes
  if ("fills" in node) {
    try {
      var fills = node.fills;
      if (fills !== figma.mixed && Array.isArray(fills)) {
        info.fills = fills.map(function(f) {
          var fill = { type: f.type, visible: f.visible };
          if (f.color) fill.color = { r: f.color.r, g: f.color.g, b: f.color.b };
          if (f.opacity !== undefined) fill.opacity = f.opacity;
          return fill;
        });
      }
    } catch (e) { /* mixed fills */ }
  }
  if ("strokes" in node) {
    try {
      info.strokes = node.strokes;
      info.strokeWeight = node.strokeWeight;
    } catch (e) { /* mixed strokes */ }
  }

  // Corner radius
  if ("cornerRadius" in node) {
    info.cornerRadius = node.cornerRadius;
    if (node.cornerRadius === figma.mixed) {
      info.topLeftRadius = node.topLeftRadius;
      info.topRightRadius = node.topRightRadius;
      info.bottomLeftRadius = node.bottomLeftRadius;
      info.bottomRightRadius = node.bottomRightRadius;
    }
  }

  // Text properties
  if (node.type === "TEXT") {
    info.characters = node.characters;
    try {
      if (node.fontSize !== figma.mixed) info.fontSize = node.fontSize;
      if (node.fontName !== figma.mixed) info.fontName = node.fontName;
      if (node.textAlignHorizontal) info.textAlignHorizontal = node.textAlignHorizontal;
      if (node.textAlignVertical) info.textAlignVertical = node.textAlignVertical;
      if (node.lineHeight !== figma.mixed) info.lineHeight = node.lineHeight;
      if (node.letterSpacing !== figma.mixed) info.letterSpacing = node.letterSpacing;
      if (node.textAutoResize) info.textAutoResize = node.textAutoResize;
    } catch (e) { /* mixed text props */ }
  }

  // Component instance info
  if (node.type === "INSTANCE") {
    try {
      var mainComp = node.mainComponent;
      if (mainComp) {
        info.componentId = mainComp.id;
        info.componentName = mainComp.name;
        if (mainComp.parent && mainComp.parent.type === "COMPONENT_SET") {
          info.componentSetName = mainComp.parent.name;
        }
      }
    } catch (e) { /* remote component */ }
  }

  // Children with depth-limited recursion + child count limit
  var MAX_CHILDREN = 50;
  if ("children" in node && node.children) {
    var childCount = node.children.length;
    var truncated = childCount > MAX_CHILDREN;
    var childrenToProcess = truncated ? node.children.slice(0, MAX_CHILDREN) : node.children;
    if (currentDepth < maxDepth) {
      info.children = childrenToProcess.map(function(child) {
        return collectNodeInfo(child, maxDepth, currentDepth + 1);
      });
    } else {
      // At max depth: shallow summary only
      info.children = childrenToProcess.map(function(child) {
        var c = { id: child.id, name: child.name, type: child.type };
        if ("width" in child) c.width = child.width;
        if ("height" in child) c.height = child.height;
        if ("characters" in child) c.characters = child.characters;
        return c;
      });
    }
    if (truncated) {
      info._childrenTruncated = true;
      info._totalChildren = childCount;
      info._shownChildren = MAX_CHILDREN;
    }
  }

  // Effects
  if ("effects" in node && Array.isArray(node.effects)) {
    info.effects = node.effects;
  }

  // Opacity & blend
  if ("opacity" in node) info.opacity = node.opacity;
  if ("blendMode" in node) info.blendMode = node.blendMode;

  // Constraints
  if ("constraints" in node) info.constraints = node.constraints;

  info._fallback = true; // Mark as fallback response
  return info;
}

async function getNodesInfo(nodeIds) {
  try {
    // Load all nodes in parallel
    const nodes = await Promise.all(
      nodeIds.map((id) => figma.getNodeByIdAsync(id))
    );

    // Filter out any null values (nodes that weren't found)
    const validNodes = nodes.filter((node) => node !== null);

    // Export all valid nodes with timeout, fall back per-node
    const responses = await Promise.all(
      validNodes.map(async (node) => {
        try {
          var tid;
          var tp = new Promise(function(_, reject) {
            tid = setTimeout(function() { reject(new Error("exportAsync timed out")); }, 15000);
          });
          var response = await Promise.race([
            node.exportAsync({ format: "JSON_REST_V1" }),
            tp
          ]);
          clearTimeout(tid);
          return {
            nodeId: node.id,
            document: response.document,
          };
        } catch (exportErr) {
          console.log("exportAsync fallback for node " + node.id + ": " + exportErr.message);
          return {
            nodeId: node.id,
            document: collectNodeInfo(node),
          };
        }
      })
    );

    return responses;
  } catch (error) {
    throw new Error(`Error getting nodes info: ${error.message}`);
  }
}

async function createRectangle(params) {
  const {
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    name = "Rectangle",
    parentId,
  } = params || {};

  const rect = figma.createRectangle();
  rect.x = x;
  rect.y = y;
  rect.resize(width, height);
  rect.name = name;

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(rect);
  } else {
    figma.currentPage.appendChild(rect);
  }

  return {
    id: rect.id,
    name: rect.name,
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
    parentId: rect.parent ? rect.parent.id : undefined,
  };
}

async function createFrame(params) {
  const {
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    name = "Frame",
    parentId,
    fillColor,
    strokeColor,
    strokeWeight,
  } = params || {};

  const frame = figma.createFrame();
  frame.x = x;
  frame.y = y;
  frame.resize(width, height);
  frame.name = name;

  // Set fill color if provided
  if (fillColor) {
    const paintStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(fillColor.r) || 0,
        g: parseFloat(fillColor.g) || 0,
        b: parseFloat(fillColor.b) || 0,
      },
      opacity: parseFloat(fillColor.a) || 1,
    };
    frame.fills = [paintStyle];
  }

  // Set stroke color and weight if provided
  if (strokeColor) {
    const strokeStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(strokeColor.r) || 0,
        g: parseFloat(strokeColor.g) || 0,
        b: parseFloat(strokeColor.b) || 0,
      },
      opacity: parseFloat(strokeColor.a) || 1,
    };
    frame.strokes = [strokeStyle];
  }

  // Set stroke weight if provided
  if (strokeWeight !== undefined) {
    frame.strokeWeight = strokeWeight;
  }

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(frame);
  } else {
    figma.currentPage.appendChild(frame);
  }

  return {
    id: frame.id,
    name: frame.name,
    x: frame.x,
    y: frame.y,
    width: frame.width,
    height: frame.height,
    fills: frame.fills,
    strokes: frame.strokes,
    strokeWeight: frame.strokeWeight,
    parentId: frame.parent ? frame.parent.id : undefined,
  };
}

async function createText(params) {
  const {
    x = 0,
    y = 0,
    text = "Text",
    fontSize = 14,
    fontWeight = 400,
    fontColor = { r: 0, g: 0, b: 0, a: 1 }, // Default to black
    name = "Text",
    parentId,
    textAlignHorizontal,
    textAutoResize,
  } = params || {};

  // Map common font weights to Figma font styles
  const getFontStyle = (weight) => {
    switch (weight) {
      case 100:
        return "Thin";
      case 200:
        return "Extra Light";
      case 300:
        return "Light";
      case 400:
        return "Regular";
      case 500:
        return "Medium";
      case 600:
        return "Semi Bold";
      case 700:
        return "Bold";
      case 800:
        return "Extra Bold";
      case 900:
        return "Black";
      default:
        return "Regular";
    }
  };

  const textNode = figma.createText();
  textNode.x = x;
  textNode.y = y;
  textNode.name = name;
  try {
    await loadFontWithTimeout({
      family: "Inter",
      style: getFontStyle(fontWeight),
    });
    textNode.fontName = { family: "Inter", style: getFontStyle(fontWeight) };
    textNode.fontSize = parseInt(fontSize);
  } catch (error) {
    console.error("Error setting font size", error);
  }
  setCharacters(textNode, text);

  // Set text color
  const paintStyle = {
    type: "SOLID",
    color: {
      r: parseFloat(fontColor.r) || 0,
      g: parseFloat(fontColor.g) || 0,
      b: parseFloat(fontColor.b) || 0,
    },
    opacity: parseFloat(fontColor.a) || 1,
  };
  textNode.fills = [paintStyle];

  // Set text alignment if provided
  if (textAlignHorizontal && ["LEFT", "CENTER", "RIGHT", "JUSTIFIED"].includes(textAlignHorizontal)) {
    textNode.textAlignHorizontal = textAlignHorizontal;
  }

  // Set text auto resize if provided (WIDTH_AND_HEIGHT, HEIGHT, NONE, TRUNCATE)
  if (textAutoResize && ["WIDTH_AND_HEIGHT", "HEIGHT", "NONE", "TRUNCATE"].includes(textAutoResize)) {
    textNode.textAutoResize = textAutoResize;
  }

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(textNode);
  } else {
    figma.currentPage.appendChild(textNode);
  }

  return {
    id: textNode.id,
    name: textNode.name,
    x: textNode.x,
    y: textNode.y,
    width: textNode.width,
    height: textNode.height,
    characters: textNode.characters,
    fontSize: textNode.fontSize,
    fontWeight: fontWeight,
    fontColor: fontColor,
    fontName: textNode.fontName,
    fills: textNode.fills,
    parentId: textNode.parent ? textNode.parent.id : undefined,
  };
}

async function setFillColor(params) {
  console.log("setFillColor", params);
  const {
    nodeId,
    color: { r, g, b, a },
  } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (!("fills" in node)) {
    throw new Error(`Node does not support fills: ${nodeId}`);
  }

  // Validate that MCP layer provided complete data
  if (r === undefined || g === undefined || b === undefined || a === undefined) {
    throw new Error("Incomplete color data received from MCP layer. All RGBA components must be provided.");
  }

  // Parse values - no defaults, just format conversion
  const rgbColor = {
    r: parseFloat(r),
    g: parseFloat(g),
    b: parseFloat(b),
    a: parseFloat(a)
  };

  // Validate parsing succeeded
  if (isNaN(rgbColor.r) || isNaN(rgbColor.g) || isNaN(rgbColor.b) || isNaN(rgbColor.a)) {
    throw new Error("Invalid color values received - all components must be valid numbers");
  }

  // Handle fill visibility toggle
  var fillVisible = (params && params.visible !== undefined) ? params.visible : true;

  // Set fill - pure translation to Figma API format
  const paintStyle = {
    type: "SOLID",
    visible: fillVisible,
    color: {
      r: rgbColor.r,
      g: rgbColor.g,
      b: rgbColor.b,
    },
    opacity: rgbColor.a,
  };

  console.log("paintStyle", paintStyle);

  node.fills = [paintStyle];

  return {
    id: node.id,
    name: node.name,
    fills: [paintStyle],
  };
}

async function setStrokeColor(params) {
  const {
    nodeId,
    color: { r, g, b, a },
    strokeWeight,
  } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (!("strokes" in node)) {
    throw new Error(`Node does not support strokes: ${nodeId}`);
  }

  if (r === undefined || g === undefined || b === undefined || a === undefined) {
    throw new Error("Incomplete color data received from MCP layer. All RGBA components must be provided.");
  }

  if (strokeWeight === undefined) {
    throw new Error("Stroke weight must be provided by MCP layer.");
  }

  const rgbColor = {
    r: parseFloat(r),
    g: parseFloat(g),
    b: parseFloat(b),
    a: parseFloat(a)
  };
  const strokeWeightParsed = parseFloat(strokeWeight);

  if (isNaN(rgbColor.r) || isNaN(rgbColor.g) || isNaN(rgbColor.b) || isNaN(rgbColor.a)) {
    throw new Error("Invalid color values received - all components must be valid numbers");
  }

  if (isNaN(strokeWeightParsed)) {
    throw new Error("Invalid stroke weight - must be a valid number");
  }

  // strokeWeight=0 이면 stroke 완전 제거 — 단, individual side weight가
  // 명시된 경우는 예외 (bottom-only underline 등)
  var hasIndividualNonZero =
    (params.strokeTopWeight !== undefined && parseFloat(params.strokeTopWeight) > 0) ||
    (params.strokeBottomWeight !== undefined && parseFloat(params.strokeBottomWeight) > 0) ||
    (params.strokeLeftWeight !== undefined && parseFloat(params.strokeLeftWeight) > 0) ||
    (params.strokeRightWeight !== undefined && parseFloat(params.strokeRightWeight) > 0);
  if (strokeWeightParsed === 0 && !hasIndividualNonZero) {
    node.strokes = [];
    if ("strokeWeight" in node) node.strokeWeight = 0;
    return { id: node.id, name: node.name, strokes: [], strokeWeight: 0 };
  }

  const paintStyle = {
    type: "SOLID",
    color: {
      r: rgbColor.r,
      g: rgbColor.g,
      b: rgbColor.b,
    },
    opacity: rgbColor.a,
  };

  node.strokes = [paintStyle];

  // Set stroke weight if available
  if ("strokeWeight" in node) {
    node.strokeWeight = strokeWeightParsed;
  }

  // Individual stroke weights (bottom-only border 등)
  // 개별 stroke weight 설정 시 strokeWeight가 figma.mixed(Symbol)로 변환됨
  var hasIndividual = params.strokeTopWeight !== undefined || params.strokeBottomWeight !== undefined || params.strokeLeftWeight !== undefined || params.strokeRightWeight !== undefined;
  if (hasIndividual && "strokeTopWeight" in node) {
    node.strokeTopWeight = parseFloat(params.strokeTopWeight !== undefined ? params.strokeTopWeight : strokeWeightParsed);
    node.strokeBottomWeight = parseFloat(params.strokeBottomWeight !== undefined ? params.strokeBottomWeight : strokeWeightParsed);
    node.strokeLeftWeight = parseFloat(params.strokeLeftWeight !== undefined ? params.strokeLeftWeight : strokeWeightParsed);
    node.strokeRightWeight = parseFloat(params.strokeRightWeight !== undefined ? params.strokeRightWeight : strokeWeightParsed);
  }

  // strokeWeight가 figma.mixed(Symbol)일 수 있으므로 typeof 체크
  var swVal = "strokeWeight" in node ? node.strokeWeight : undefined;
  var safeStrokeWeight = (typeof swVal === "number") ? swVal : undefined;

  return {
    id: node.id,
    name: node.name,
    strokes: node.strokes,
    strokeWeight: safeStrokeWeight,
    strokeTopWeight: "strokeTopWeight" in node && typeof node.strokeTopWeight === "number" ? node.strokeTopWeight : undefined,
    strokeBottomWeight: "strokeBottomWeight" in node && typeof node.strokeBottomWeight === "number" ? node.strokeBottomWeight : undefined,
    strokeLeftWeight: "strokeLeftWeight" in node && typeof node.strokeLeftWeight === "number" ? node.strokeLeftWeight : undefined,
    strokeRightWeight: "strokeRightWeight" in node && typeof node.strokeRightWeight === "number" ? node.strokeRightWeight : undefined,
  };
}

async function setSelectionColors(params) {
  const { nodeId, r, g, b, a, commandId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (r === undefined || g === undefined || b === undefined) {
    throw new Error("RGB components (r, g, b) are required");
  }

  const newColor = {
    r: parseFloat(r),
    g: parseFloat(g),
    b: parseFloat(b),
  };
  const opacity = a !== undefined ? parseFloat(a) : 1;

  // Get all descendant nodes + the target node itself
  let targets = [];
  if ("findAll" in node) {
    targets = [node].concat(node.findAll(() => true));
  } else {
    targets = [node];
  }

  let changedCount = 0;
  const totalNodes = targets.length;
  const chunkSize = 200; // Process 200 nodes at a time

  sendProgressUpdate(commandId, "set_selection_colors", "started", 0, totalNodes, 0, `Starting color update for ${totalNodes} nodes...`);

  for (let i = 0; i < totalNodes; i += chunkSize) {
    const chunk = targets.slice(i, i + chunkSize);
    
    for (const n of chunk) {
      let nodeModified = false;

      // Update strokes
      if ("strokes" in n && Array.isArray(n.strokes) && n.strokes.length > 0) {
        let strokesChanged = false;
        const newStrokes = n.strokes.map(s => {
          if (s.type === "SOLID") {
            // Only update if color or opacity is different
            if (s.color.r !== newColor.r || s.color.g !== newColor.g || s.color.b !== newColor.b || s.opacity !== opacity) {
              strokesChanged = true;
              return Object.assign({}, s, { color: newColor, opacity: opacity });
            }
          }
          return s;
        });
        
        if (strokesChanged) {
          n.strokes = newStrokes;
          nodeModified = true;
        }
      }

      // Update fills
      if ("fills" in n && Array.isArray(n.fills) && n.fills.length > 0) {
        let fillsChanged = false;
        const newFills = n.fills.map(f => {
          if (f.type === "SOLID" && f.visible !== false) {
            // Only update if color or opacity is different
            if (f.color.r !== newColor.r || f.color.g !== newColor.g || f.color.b !== newColor.b || f.opacity !== opacity) {
              fillsChanged = true;
              return Object.assign({}, f, { color: newColor, opacity: opacity, visible: true });
            }
          }
          return f;
        });

        if (fillsChanged) {
          n.fills = newFills;
          nodeModified = true;
        }
      }

      if (nodeModified) {
        changedCount++;
      }
    }

    // After each chunk, yield to main thread and send progress
    const processedCount = Math.min(i + chunkSize, totalNodes);
    const progress = Math.round((processedCount / totalNodes) * 100);
    
    sendProgressUpdate(commandId, "set_selection_colors", "in_progress", progress, totalNodes, processedCount, `Processed ${processedCount}/${totalNodes} nodes...`);
    
    // Tiny delay to breathe
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  return {
    id: node.id,
    name: node.name,
    nodesChanged: changedCount,
    totalProcessed: totalNodes
  };
}

async function moveNode(params) {
  const { nodeId, x, y } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (x === undefined || y === undefined) {
    throw new Error("Missing x or y parameters");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (!("x" in node) || !("y" in node)) {
    throw new Error(`Node does not support position: ${nodeId}`);
  }

  node.x = x;
  node.y = y;

  return {
    id: node.id,
    name: node.name,
    x: node.x,
    y: node.y,
  };
}

async function resizeNode(params) {
  const { nodeId, width, height } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (width === undefined || height === undefined) {
    throw new Error("Missing width or height parameters");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (!("resize" in node)) {
    throw new Error(`Node does not support resizing: ${nodeId}`);
  }

  node.resize(width, height);

  return {
    id: node.id,
    name: node.name,
    width: node.width,
    height: node.height,
  };
}

async function deleteNode(params) {
  const { nodeId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  // Save node info before deleting
  const nodeInfo = {
    id: node.id,
    name: node.name,
    type: node.type,
  };

  node.remove();

  return nodeInfo;
}

async function getStyles() {
  const styles = {
    colors: await figma.getLocalPaintStylesAsync(),
    texts: await figma.getLocalTextStylesAsync(),
    effects: await figma.getLocalEffectStylesAsync(),
    grids: await figma.getLocalGridStylesAsync(),
  };

  return {
    colors: styles.colors.map((style) => ({
      id: style.id,
      name: style.name,
      key: style.key,
      paint: style.paints[0],
    })),
    texts: styles.texts.map((style) => ({
      id: style.id,
      name: style.name,
      key: style.key,
      fontSize: style.fontSize,
      fontName: style.fontName,
    })),
    effects: styles.effects.map((style) => ({
      id: style.id,
      name: style.name,
      key: style.key,
    })),
    grids: styles.grids.map((style) => ({
      id: style.id,
      name: style.name,
      key: style.key,
    })),
  };
}

async function getLocalComponents() {
  await figma.loadAllPagesAsync();

  const components = figma.root.findAllWithCriteria({
    types: ["COMPONENT"],
  });

  return {
    count: components.length,
    components: components.map((component) => ({
      id: component.id,
      name: component.name,
      key: "key" in component ? component.key : null,
    })),
  };
}

async function getLocalComponentSets() {
  await figma.loadAllPagesAsync();

  var sets = figma.root.findAllWithCriteria({
    types: ["COMPONENT_SET"],
  });

  return {
    count: sets.length,
    componentSets: sets.map(function(set) {
      var children = set.children || [];
      return {
        id: set.id,
        name: set.name,
        key: "key" in set ? set.key : null,
        variantProperties: "componentPropertyDefinitions" in set
          ? set.componentPropertyDefinitions
          : null,
        variants: children
          .filter(function(c) { return c.type === "COMPONENT"; })
          .map(function(c) {
            return {
              id: c.id,
              name: c.name,
              key: "key" in c ? c.key : null,
            };
          }),
      };
    }),
  };
}

async function findComponentsByName(params) {
  var query = (params && params.query) ? params.query.toLowerCase() : "";
  if (!query) {
    throw new Error("Missing query parameter");
  }

  // First try current page
  var components = figma.currentPage.findAllWithCriteria({
    types: ["COMPONENT"]
  });

  var matches = components.filter(function(c) {
    return c.name.toLowerCase().indexOf(query) !== -1;
  });

  // If no matches on current page, try all pages
  if (matches.length === 0) {
    try {
      await figma.loadAllPagesAsync();
      components = figma.root.findAllWithCriteria({
        types: ["COMPONENT"]
      });
      matches = components.filter(function(c) {
        return c.name.toLowerCase().indexOf(query) !== -1;
      });
    } catch (e) {
      // loadAllPagesAsync can fail
    }
  }

  return {
    count: matches.length,
    components: matches.map(function(c) {
      return {
        id: c.id,
        name: c.name,
        key: "key" in c ? c.key : null
      };
    })
  };
}

async function getComponentKey(params) {
  var nodeId = params && params.nodeId;
  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }
  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error("Node not found: " + nodeId);
  }

  var result = { id: node.id, name: node.name, type: node.type };

  // If it's a component, get its key
  if (node.type === "COMPONENT") {
    result.key = node.key;
    // Also get parent info (might be a component set)
    if (node.parent) {
      result.parentId = node.parent.id;
      result.parentName = node.parent.name;
      result.parentType = node.parent.type;
    }
  }

  // If it's an instance, try to get mainComponent info
  if (node.type === "INSTANCE") {
    var mc = null;
    try {
      mc = node.mainComponent;
    } catch (e) {
      // sync fails for dynamic-page / remote components, try async
    }
    if (!mc) {
      try {
        var tid;
        var tp = new Promise(function(_, reject) {
          tid = setTimeout(function() { reject(new Error("async timeout")); }, 15000);
        });
        mc = await Promise.race([node.getMainComponentAsync(), tp]);
        clearTimeout(tid);
      } catch (e2) {
        result.mainComponentError = e2.message;
      }
    }
    if (mc) {
      result.mainComponentId = mc.id;
      result.mainComponentName = mc.name;
      result.mainComponentKey = mc.key;
      if (mc.parent) {
        result.mainComponentParentId = mc.parent.id;
        result.mainComponentParentName = mc.parent.name;
        result.mainComponentParentType = mc.parent.type;
      }
    }
  }

  return result;
}

async function searchLibraryComponents(params) {
  var query = (params && params.query) ? params.query.toLowerCase() : "";
  if (!query) {
    throw new Error("Missing query parameter");
  }

  var components = await figma.teamLibrary.getAvailableComponentsAsync();
  var matches = components.filter(function(c) {
    return c.name.toLowerCase().indexOf(query) !== -1;
  });

  return {
    totalLibraryComponents: components.length,
    matchCount: matches.length,
    matches: matches.slice(0, 50).map(function(c) {
      return {
        key: c.key,
        name: c.name,
        description: c.description || null,
        libraryName: c.libraryName || null
      };
    })
  };
}

async function scanInstancesForSwap(params) {
  var pageName = (params && params.pageName) ? params.pageName : "icons";
  var parentNodeName = (params && params.parentNodeName) ? params.parentNodeName : "icon_list";
  var nameFilter = (params && params.nameFilter) ? params.nameFilter.toLowerCase() : null;

  // Find the target page
  var targetPage = null;
  for (var i = 0; i < figma.root.children.length; i++) {
    var page = figma.root.children[i];
    if (page.name.toLowerCase() === pageName.toLowerCase()) {
      targetPage = page;
      break;
    }
  }
  if (!targetPage) {
    var pageNames = [];
    for (var p = 0; p < figma.root.children.length; p++) {
      pageNames.push(figma.root.children[p].name);
    }
    throw new Error("Page '" + pageName + "' not found. Available pages: " + pageNames.join(", "));
  }

  // Load the page to access its children
  await targetPage.loadAsync();

  // Find the parent node by name (BFS)
  var parentNode = null;
  var queue = [];
  for (var c = 0; c < targetPage.children.length; c++) {
    queue.push(targetPage.children[c]);
  }
  while (queue.length > 0) {
    var current = queue.shift();
    if (current.name === parentNodeName) {
      parentNode = current;
      break;
    }
    if (current.children) {
      for (var ch = 0; ch < current.children.length; ch++) {
        queue.push(current.children[ch]);
      }
    }
  }
  if (!parentNode) {
    throw new Error("Node '" + parentNodeName + "' not found on page '" + pageName + "'");
  }

  // Scan all instance children recursively
  var instances = [];
  var scanQueue = [];
  for (var s = 0; s < parentNode.children.length; s++) {
    scanQueue.push(parentNode.children[s]);
  }
  while (scanQueue.length > 0) {
    var node = scanQueue.shift();
    if (node.type === "INSTANCE") {
      var name = node.name;
      if (!nameFilter || name.toLowerCase().indexOf(nameFilter) !== -1) {
        instances.push(node);
      }
    }
    if (node.children) {
      for (var sc = 0; sc < node.children.length; sc++) {
        scanQueue.push(node.children[sc]);
      }
    }
  }

  // Resolve componentId for each matched instance
  var resolved = [];
  for (var r = 0; r < instances.length; r++) {
    var inst = instances[r];
    var compId = null;
    // Try sync mainComponent first
    try {
      var mc = inst.mainComponent;
      if (mc) compId = mc.id;
    } catch (e) {}
    // Fallback: use exportAsync to get componentId from REST JSON
    if (!compId) {
      try {
        var exported = await inst.exportAsync({ format: "JSON_REST_V1" });
        if (exported && exported.document && exported.document.componentId) {
          compId = exported.document.componentId;
        }
      } catch (e) {}
    }
    resolved.push({
      nodeId: inst.id,
      name: inst.name,
      componentId: compId
    });
  }

  return {
    pageName: targetPage.name,
    parentNodeName: parentNode.name,
    parentNodeId: parentNode.id,
    instanceCount: resolved.length,
    instances: resolved
  };
}

async function setImageFill(params) {
  var nodeId = params && params.nodeId;
  var imageData = params && params.imageData; // base64 string
  var scaleMode = (params && params.scaleMode) || "FILL";

  if (!nodeId) throw new Error("Missing nodeId parameter");
  if (params && params.url && !imageData) {
    throw new Error("set_image_fill does NOT support 'url' parameter. Use 'imageData' (base64-encoded PNG/JPEG) instead. Read the file and base64-encode it.");
  }
  if (!imageData) throw new Error("Missing imageData parameter (base64-encoded PNG/JPEG string)");

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) throw new Error("Node not found: " + nodeId);

  // Decode base64 to Uint8Array
  var chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  var output = [];
  var buffer = 0, bits = 0;
  for (var i = 0; i < imageData.length; i++) {
    var c = imageData.charAt(i);
    if (c === "=" || c === "\n" || c === "\r") continue;
    var idx = chars.indexOf(c);
    if (idx === -1) continue;
    buffer = (buffer << 6) | idx;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      output.push((buffer >> bits) & 0xFF);
    }
  }
  var bytes = new Uint8Array(output);

  var image = figma.createImage(bytes);
  node.fills = [{
    type: "IMAGE",
    scaleMode: scaleMode,
    imageHash: image.hash
  }];

  return { nodeId: node.id, name: node.name, imageHash: image.hash };
}

// async function getTeamComponents() {
//   try {
//     const teamComponents =
//       await figma.teamLibrary.getAvailableComponentsAsync();

//     return {
//       count: teamComponents.length,
//       components: teamComponents.map((component) => ({
//         key: component.key,
//         name: component.name,
//         description: component.description,
//         libraryName: component.libraryName,
//       })),
//     };
//   } catch (error) {
//     throw new Error(`Error getting team components: ${error.message}`);
//   }
// }

async function createComponentInstance(params) {
  const { componentKey, x = 0, y = 0 } = params || {};

  if (!componentKey) {
    throw new Error("Missing componentKey parameter");
  }

  try {
    console.log(`Looking for component with key: ${componentKey}...`);

    // ★ Use component cache for fast lookup
    let component = await getCachedComponent(componentKey);
    if (!component) {
      throw new Error(`Component not found: ${componentKey}. It may be in a team library you don't have access to.`);
    }
    console.log(`Component ready: ${component.name}`);

    // Create instance and set properties in a separate try block to handle errors specifically from this step
    try {
      const instance = component.createInstance();
      instance.x = x;
      instance.y = y;

      figma.currentPage.appendChild(instance);
      console.log(`Component instance created and added to page successfully`);

      return {
        id: instance.id,
        name: instance.name,
        x: instance.x,
        y: instance.y,
        width: instance.width,
        height: instance.height,
        componentId: instance.componentId,
      };
    } catch (instanceError) {
      console.error(`Error creating component instance: ${instanceError.message}`);
      throw new Error(`Error creating component instance: ${instanceError.message}`);
    }
  } catch (error) {
    console.error(`Detailed error creating component instance: ${error.message || "Unknown error"}`);
    console.error(`Stack trace: ${error.stack || "Not available"}`);

    // Provide more helpful error messages for common failure scenarios
    if (error.message.includes("timeout") || error.message.includes("Timeout")) {
      throw new Error(`The component import timed out after 10 seconds. This usually happens with complex remote components or network issues. Try again later or use a simpler component.`);
    } else if (error.message.includes("not found") || error.message.includes("Not found")) {
      throw new Error(`Component with key "${componentKey}" not found. Make sure the component exists and is accessible in your document or team libraries.`);
    } else if (error.message.includes("permission") || error.message.includes("Permission")) {
      throw new Error(`You don't have permission to use this component. Make sure you have access to the team library containing this component.`);
    } else {
      throw new Error(`Error creating component instance: ${error.message}`);
    }
  }
}

async function getInstanceProperties(params) {
  const { nodeId, includeDefinitions } = params || {};
  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }
  if (node.type !== "INSTANCE") {
    throw new Error(`Node is not an instance. Type: ${node.type}`);
  }

  const properties = node.componentProperties;

  let definitions = {};
  let mainComp = null;

  // Try sync mainComponent first (fast, works for local components)
  try {
    mainComp = node.mainComponent;
  } catch (e) {
    // node.mainComponent can throw for remote library components
  }

  if (includeDefinitions) {
    // If sync failed or has no definitions, try async with timeout
    var asyncComp = null;
    if (!mainComp) {
      try {
        var timeoutId;
        var timeoutPromise = new Promise(function(_, reject) {
          timeoutId = setTimeout(function() {
            reject(new Error("getMainComponentAsync timed out"));
          }, 30000);
        });
        asyncComp = await Promise.race([node.getMainComponentAsync(), timeoutPromise]);
        clearTimeout(timeoutId);
      } catch (e) {
        // getMainComponentAsync can fail or timeout
      }
    }

    var defSource = asyncComp || mainComp;
    if (defSource) {
      mainComp = defSource;
      definitions = defSource.componentPropertyDefinitions || {};
      // For variant components, definitions may be on the parent ComponentSet
      if (Object.keys(definitions).length === 0 && defSource.parent && defSource.parent.type === "COMPONENT_SET") {
        definitions = defSource.parent.componentPropertyDefinitions || {};
      }
    }
  }

  const componentName = mainComp ? mainComp.name : null;
  const componentKey = mainComp ? mainComp.key : null;

  const result = {};
  for (const [key, prop] of Object.entries(properties)) {
    const def = definitions[key];
    result[key] = {
      type: prop.type,
      value: prop.value,
      preferredValues: (def && def.preferredValues) ? def.preferredValues : null
    };
  }

  return {
    nodeId: node.id,
    name: node.name,
    componentName: componentName,
    componentKey: componentKey,
    properties: result
  };
}

async function setInstanceProperties(params) {
  const { nodeId, properties } = params || {};
  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }
  if (!properties || typeof properties !== "object") {
    throw new Error("Missing or invalid properties parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }
  if (node.type !== "INSTANCE") {
    throw new Error(`Node is not an instance. Type: ${node.type}`);
  }

  // INSTANCE_SWAP values are node IDs (e.g. "5:913"), not component keys.
  // No pre-import needed — setProperties accepts node IDs directly.
  var updates = {};
  for (var _k in properties) {
    if (properties.hasOwnProperty(_k)) {
      updates[_k] = properties[_k];
    }
  }
  node.setProperties(updates);

  const updatedProps = node.componentProperties;
  const result = {};
  for (const [key, prop] of Object.entries(updatedProps)) {
    result[key] = {
      type: prop.type,
      value: prop.value
    };
  }

  return {
    nodeId: node.id,
    name: node.name,
    properties: result
  };
}

async function exportNodeAsImage(params) {
  const { nodeId, scale = 1, format = "PNG" } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  console.log(`[exportNodeAsImage] Starting export for node ${nodeId}, scale: ${scale}, format: ${format}`);
  const startTime = Date.now();

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  console.log(`[exportNodeAsImage] Node found: ${node.name}, type: ${node.type}, size: ${node.width}x${node.height}`);

  if (!("exportAsync" in node)) {
    throw new Error(`Node does not support exporting: ${nodeId}`);
  }

  try {
    const settings = {
      format: format,
      constraint: { type: "SCALE", value: scale },
    };

    // Set up a timeout for large exports
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error(`Export timed out after 60s for node ${nodeId} (${node.name}, ${node.width}x${node.height})`));
      }, 60000); // 60 seconds timeout
    });

    const exportPromise = node.exportAsync(settings);

    const bytes = await Promise.race([exportPromise, timeoutPromise])
      .finally(() => {
        clearTimeout(timeoutId);
      });

    console.log(`[exportNodeAsImage] Export completed in ${Date.now() - startTime}ms, bytes: ${bytes.length}`);

    let mimeType;
    switch (format) {
      case "PNG":
        mimeType = "image/png";
        break;
      case "JPG":
        mimeType = "image/jpeg";
        break;
      case "SVG":
        mimeType = "image/svg+xml";
        break;
      case "PDF":
        mimeType = "application/pdf";
        break;
      default:
        mimeType = "application/octet-stream";
    }

    // Proper way to convert Uint8Array to base64
    const base64 = customBase64Encode(bytes);
    // const imageData = `data:${mimeType};base64,${base64}`;

    return {
      nodeId,
      format,
      scale,
      mimeType,
      imageData: base64,
    };
  } catch (error) {
    throw new Error(`Error exporting node as image: ${error.message}`);
  }
}
function customBase64Encode(bytes) {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let base64 = "";

  const byteLength = bytes.byteLength;
  const byteRemainder = byteLength % 3;
  const mainLength = byteLength - byteRemainder;

  let a, b, c, d;
  let chunk;

  // Main loop deals with bytes in chunks of 3
  for (let i = 0; i < mainLength; i = i + 3) {
    // Combine the three bytes into a single integer
    chunk = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];

    // Use bitmasks to extract 6-bit segments from the triplet
    a = (chunk & 16515072) >> 18; // 16515072 = (2^6 - 1) << 18
    b = (chunk & 258048) >> 12; // 258048 = (2^6 - 1) << 12
    c = (chunk & 4032) >> 6; // 4032 = (2^6 - 1) << 6
    d = chunk & 63; // 63 = 2^6 - 1

    // Convert the raw binary segments to the appropriate ASCII encoding
    base64 += chars[a] + chars[b] + chars[c] + chars[d];
  }

  // Deal with the remaining bytes and padding
  if (byteRemainder === 1) {
    chunk = bytes[mainLength];

    a = (chunk & 252) >> 2; // 252 = (2^6 - 1) << 2

    // Set the 4 least significant bits to zero
    b = (chunk & 3) << 4; // 3 = 2^2 - 1

    base64 += chars[a] + chars[b] + "==";
  } else if (byteRemainder === 2) {
    chunk = (bytes[mainLength] << 8) | bytes[mainLength + 1];

    a = (chunk & 64512) >> 10; // 64512 = (2^6 - 1) << 10
    b = (chunk & 1008) >> 4; // 1008 = (2^6 - 1) << 4

    // Set the 2 least significant bits to zero
    c = (chunk & 15) << 2; // 15 = 2^4 - 1

    base64 += chars[a] + chars[b] + chars[c] + "=";
  }

  return base64;
}

async function setCornerRadius(params) {
  const { nodeId, radius, corners } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (radius === undefined) {
    throw new Error("Missing radius parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  // Check if node supports corner radius
  if (!("cornerRadius" in node)) {
    throw new Error(`Node does not support corner radius: ${nodeId}`);
  }

  // If corners array is provided, set individual corner radii
  if (corners && Array.isArray(corners) && corners.length === 4) {
    if ("topLeftRadius" in node) {
      // Node supports individual corner radii
      if (corners[0]) node.topLeftRadius = radius;
      if (corners[1]) node.topRightRadius = radius;
      if (corners[2]) node.bottomRightRadius = radius;
      if (corners[3]) node.bottomLeftRadius = radius;
    } else {
      // Node only supports uniform corner radius
      node.cornerRadius = radius;
    }
  } else {
    // Set uniform corner radius
    node.cornerRadius = radius;
  }

  return {
    id: node.id,
    name: node.name,
    cornerRadius: "cornerRadius" in node ? node.cornerRadius : undefined,
    topLeftRadius: "topLeftRadius" in node ? node.topLeftRadius : undefined,
    topRightRadius: "topRightRadius" in node ? node.topRightRadius : undefined,
    bottomRightRadius:
      "bottomRightRadius" in node ? node.bottomRightRadius : undefined,
    bottomLeftRadius:
      "bottomLeftRadius" in node ? node.bottomLeftRadius : undefined,
  };
}

async function setTextContent(params) {
  const { nodeId, text } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (text === undefined) {
    throw new Error("Missing text parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);

    // Replace <br> marker with Unicode Line Separator (U+2028)
    // This produces a Shift+Enter (soft line break) in Figma,
    // instead of a paragraph break (\n / Enter).
    var processedText = text.replace(/<br>/g, "\u2028");

    await setCharacters(node, processedText);

    return {
      id: node.id,
      name: node.name,
      characters: node.characters,
      fontName: node.fontName,
    };
  } catch (error) {
    throw new Error(`Error setting text content: ${error.message}`);
  }
}

// Initialize settings on load
(async function initializePlugin() {
  try {
    const savedSettings = await figma.clientStorage.getAsync("settings");
    if (savedSettings) {
      if (savedSettings.serverPort) {
        state.serverPort = savedSettings.serverPort;
      }
    }

    // Send initial settings to UI
    figma.ui.postMessage({
      type: "init-settings",
      settings: {
        serverPort: state.serverPort,
      },
    });
  } catch (error) {
    console.error("Error loading settings:", error);
  }
})();

function uniqBy(arr, predicate) {
  const cb = typeof predicate === "function" ? predicate : (o) => o[predicate];
  return [
    ...arr
      .reduce((map, item) => {
        const key = item === null || item === undefined ? item : cb(item);

        map.has(key) || map.set(key, item);

        return map;
      }, new Map())
      .values(),
  ];
}
const setCharacters = async (node, characters, options) => {
  const fallbackFont = (options && options.fallbackFont) || {
    family: "Inter",
    style: "Regular",
  };
  try {
    if (node.fontName === figma.mixed) {
      if (options && options.smartStrategy === "prevail") {
        const fontHashTree = {};
        for (let i = 1; i < node.characters.length; i++) {
          const charFont = node.getRangeFontName(i - 1, i);
          const key = `${charFont.family}::${charFont.style}`;
          fontHashTree[key] = fontHashTree[key] ? fontHashTree[key] + 1 : 1;
        }
        const prevailedTreeItem = Object.entries(fontHashTree).sort(
          (a, b) => b[1] - a[1]
        )[0];
        const [family, style] = prevailedTreeItem[0].split("::");
        const prevailedFont = {
          family,
          style,
        };
        await loadFontWithTimeout(prevailedFont);
        node.fontName = prevailedFont;
      } else if (options && options.smartStrategy === "strict") {
        return setCharactersWithStrictMatchFont(node, characters, fallbackFont);
      } else if (options && options.smartStrategy === "experimental") {
        return setCharactersWithSmartMatchFont(node, characters, fallbackFont);
      } else {
        const firstCharFont = node.getRangeFontName(0, 1);
        await loadFontWithTimeout(firstCharFont);
        node.fontName = firstCharFont;
      }
    } else {
      await loadFontWithTimeout({
        family: node.fontName.family,
        style: node.fontName.style,
      });
    }
  } catch (err) {
    console.warn(
      `Failed to load "${node.fontName["family"]} ${node.fontName["style"]}" font and replaced with fallback "${fallbackFont.family} ${fallbackFont.style}"`,
      err
    );
    await loadFontWithTimeout(fallbackFont);
    node.fontName = fallbackFont;
  }
  try {
    node.characters = characters;
    return true;
  } catch (err) {
    console.warn(`Failed to set characters. Skipped.`, err);
    return false;
  }
};

const setCharactersWithStrictMatchFont = async (
  node,
  characters,
  fallbackFont
) => {
  const fontHashTree = {};
  for (let i = 1; i < node.characters.length; i++) {
    const startIdx = i - 1;
    const startCharFont = node.getRangeFontName(startIdx, i);
    const startCharFontVal = `${startCharFont.family}::${startCharFont.style}`;
    while (i < node.characters.length) {
      i++;
      const charFont = node.getRangeFontName(i - 1, i);
      if (startCharFontVal !== `${charFont.family}::${charFont.style}`) {
        break;
      }
    }
    fontHashTree[`${startIdx}_${i}`] = startCharFontVal;
  }
  await loadFontWithTimeout(fallbackFont);
  node.fontName = fallbackFont;
  node.characters = characters;
  console.log(fontHashTree);
  await Promise.all(
    Object.keys(fontHashTree).map(async (range) => {
      console.log(range, fontHashTree[range]);
      const [start, end] = range.split("_");
      const [family, style] = fontHashTree[range].split("::");
      const matchedFont = {
        family,
        style,
      };
      await loadFontWithTimeout(matchedFont);
      return node.setRangeFontName(Number(start), Number(end), matchedFont);
    })
  );
  return true;
};

const getDelimiterPos = (str, delimiter, startIdx = 0, endIdx = str.length) => {
  const indices = [];
  let temp = startIdx;
  for (let i = 0; i < endIdx; i++) {
    if (
      str[i] === delimiter &&
      i + startIdx !== endIdx &&
      temp !== i + startIdx
    ) {
      indices.push([temp, i + startIdx]);
      temp = i + startIdx + 1;
    }
  }
  temp !== endIdx && indices.push([temp, endIdx]);
  return indices.filter(Boolean);
};

const buildLinearOrder = (node) => {
  const fontTree = [];
  const newLinesPos = getDelimiterPos(node.characters, "\n");
  newLinesPos.forEach(([newLinesRangeStart, newLinesRangeEnd], n) => {
    const newLinesRangeFont = node.getRangeFontName(
      newLinesRangeStart,
      newLinesRangeEnd
    );
    if (newLinesRangeFont === figma.mixed) {
      const spacesPos = getDelimiterPos(
        node.characters,
        " ",
        newLinesRangeStart,
        newLinesRangeEnd
      );
      spacesPos.forEach(([spacesRangeStart, spacesRangeEnd], s) => {
        const spacesRangeFont = node.getRangeFontName(
          spacesRangeStart,
          spacesRangeEnd
        );
        if (spacesRangeFont === figma.mixed) {
          const spacesRangeFont = node.getRangeFontName(
            spacesRangeStart,
            spacesRangeStart[0]
          );
          fontTree.push({
            start: spacesRangeStart,
            delimiter: " ",
            family: spacesRangeFont.family,
            style: spacesRangeFont.style,
          });
        } else {
          fontTree.push({
            start: spacesRangeStart,
            delimiter: " ",
            family: spacesRangeFont.family,
            style: spacesRangeFont.style,
          });
        }
      });
    } else {
      fontTree.push({
        start: newLinesRangeStart,
        delimiter: "\n",
        family: newLinesRangeFont.family,
        style: newLinesRangeFont.style,
      });
    }
  });
  return fontTree
    .sort((a, b) => +a.start - +b.start)
    .map(({ family, style, delimiter }) => ({ family, style, delimiter }));
};

const setCharactersWithSmartMatchFont = async (
  node,
  characters,
  fallbackFont
) => {
  const rangeTree = buildLinearOrder(node);
  const fontsToLoad = uniqBy(
    rangeTree,
    ({ family, style }) => `${family}::${style}`
  ).map(({ family, style }) => ({
    family,
    style,
  }));

  await Promise.all([...fontsToLoad, fallbackFont].map(function(f) { return loadFontWithTimeout(f); }));

  node.fontName = fallbackFont;
  node.characters = characters;

  let prevPos = 0;
  rangeTree.forEach(({ family, style, delimiter }) => {
    if (prevPos < node.characters.length) {
      const delimeterPos = node.characters.indexOf(delimiter, prevPos);
      const endPos =
        delimeterPos > prevPos ? delimeterPos : node.characters.length;
      const matchedFont = {
        family,
        style,
      };
      node.setRangeFontName(prevPos, endPos, matchedFont);
      prevPos = endPos + 1;
    }
  });
  return true;
};

// Add the cloneNode function implementation
async function cloneNode(params) {
  const { nodeId, x, y, targetParentId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  // Clone the node
  const clone = node.clone();

  // If x and y are provided, move the clone to that position
  if (x !== undefined && y !== undefined) {
    if (!("x" in clone) || !("y" in clone)) {
      throw new Error(`Cloned node does not support position: ${nodeId}`);
    }
    clone.x = x;
    clone.y = y;
  }

  // Add the clone to target parent if specified, else same parent as original, else current page
  if (targetParentId) {
    const targetParent = await figma.getNodeByIdAsync(targetParentId);
    if (targetParent && "appendChild" in targetParent) {
      targetParent.appendChild(clone);
    } else {
      figma.currentPage.appendChild(clone);
    }
  } else if (node.parent) {
    node.parent.appendChild(clone);
  } else {
    figma.currentPage.appendChild(clone);
  }

  return {
    id: clone.id,
    name: clone.name,
    x: "x" in clone ? clone.x : undefined,
    y: "y" in clone ? clone.y : undefined,
    width: "width" in clone ? clone.width : undefined,
    height: "height" in clone ? clone.height : undefined,
  };
}

async function scanTextNodes(params) {
  console.log(`Starting to scan text nodes from node ID: ${params.nodeId}`);
  const { nodeId, useChunking = true, chunkSize = 10, commandId = generateCommandId() } = params || {};

  const node = await figma.getNodeByIdAsync(nodeId);

  if (!node) {
    console.error(`Node with ID ${nodeId} not found`);
    // Send error progress update
    sendProgressUpdate(
      commandId,
      'scan_text_nodes',
      'error',
      0,
      0,
      0,
      `Node with ID ${nodeId} not found`,
      { error: `Node not found: ${nodeId}` }
    );
    throw new Error(`Node with ID ${nodeId} not found`);
  }

  // If chunking is not enabled, use the original implementation
  if (!useChunking) {
    const textNodes = [];
    try {
      // Send started progress update
      sendProgressUpdate(
        commandId,
        'scan_text_nodes',
        'started',
        0,
        1, // Not known yet how many nodes there are
        0,
        `Starting scan of node "${node.name || nodeId}" without chunking`,
        null
      );

      await findTextNodes(node, [], 0, textNodes);

      // Send completed progress update
      sendProgressUpdate(
        commandId,
        'scan_text_nodes',
        'completed',
        100,
        textNodes.length,
        textNodes.length,
        `Scan complete. Found ${textNodes.length} text nodes.`,
        { textNodes }
      );

      return {
        success: true,
        message: `Scanned ${textNodes.length} text nodes.`,
        count: textNodes.length,
        textNodes: textNodes,
        commandId
      };
    } catch (error) {
      console.error("Error scanning text nodes:", error);

      // Send error progress update
      sendProgressUpdate(
        commandId,
        'scan_text_nodes',
        'error',
        0,
        0,
        0,
        `Error scanning text nodes: ${error.message}`,
        { error: error.message }
      );

      throw new Error(`Error scanning text nodes: ${error.message}`);
    }
  }

  // Chunked implementation
  console.log(`Using chunked scanning with chunk size: ${chunkSize}`);

  // First, collect all nodes to process (without processing them yet)
  const nodesToProcess = [];

  // Send started progress update
  sendProgressUpdate(
    commandId,
    'scan_text_nodes',
    'started',
    0,
    0, // Not known yet how many nodes there are
    0,
    `Starting chunked scan of node "${node.name || nodeId}"`,
    { chunkSize }
  );

  await collectNodesToProcess(node, [], 0, nodesToProcess);

  const totalNodes = nodesToProcess.length;
  console.log(`Found ${totalNodes} total nodes to process`);

  // Calculate number of chunks needed
  const totalChunks = Math.ceil(totalNodes / chunkSize);
  console.log(`Will process in ${totalChunks} chunks`);

  // Send update after node collection
  sendProgressUpdate(
    commandId,
    'scan_text_nodes',
    'in_progress',
    5, // 5% progress for collection phase
    totalNodes,
    0,
    `Found ${totalNodes} nodes to scan. Will process in ${totalChunks} chunks.`,
    {
      totalNodes,
      totalChunks,
      chunkSize
    }
  );

  // Process nodes in chunks
  const allTextNodes = [];
  let processedNodes = 0;
  let chunksProcessed = 0;

  for (let i = 0; i < totalNodes; i += chunkSize) {
    const chunkEnd = Math.min(i + chunkSize, totalNodes);
    console.log(`Processing chunk ${chunksProcessed + 1}/${totalChunks} (nodes ${i} to ${chunkEnd - 1})`);

    // Send update before processing chunk
    sendProgressUpdate(
      commandId,
      'scan_text_nodes',
      'in_progress',
      Math.round(5 + ((chunksProcessed / totalChunks) * 90)), // 5-95% for processing
      totalNodes,
      processedNodes,
      `Processing chunk ${chunksProcessed + 1}/${totalChunks}`,
      {
        currentChunk: chunksProcessed + 1,
        totalChunks,
        textNodesFound: allTextNodes.length
      }
    );

    const chunkNodes = nodesToProcess.slice(i, chunkEnd);
    const chunkTextNodes = [];

    // Process each node in this chunk
    for (const nodeInfo of chunkNodes) {
      if (nodeInfo.node.type === "TEXT") {
        try {
          const textNodeInfo = await processTextNode(nodeInfo.node, nodeInfo.parentPath, nodeInfo.depth);
          if (textNodeInfo) {
            chunkTextNodes.push(textNodeInfo);
          }
        } catch (error) {
          console.error(`Error processing text node: ${error.message}`);
          // Continue with other nodes
        }
      }

      // Brief delay to allow UI updates and prevent freezing
      await delay(5);
    }

    // Add results from this chunk
    allTextNodes.push(...chunkTextNodes);
    processedNodes += chunkNodes.length;
    chunksProcessed++;

    // Send update after processing chunk
    sendProgressUpdate(
      commandId,
      'scan_text_nodes',
      'in_progress',
      Math.round(5 + ((chunksProcessed / totalChunks) * 90)), // 5-95% for processing
      totalNodes,
      processedNodes,
      `Processed chunk ${chunksProcessed}/${totalChunks}. Found ${allTextNodes.length} text nodes so far.`,
      {
        currentChunk: chunksProcessed,
        totalChunks,
        processedNodes,
        textNodesFound: allTextNodes.length,
        chunkResult: chunkTextNodes
      }
    );

    // Small delay between chunks to prevent UI freezing
    if (i + chunkSize < totalNodes) {
      await delay(50);
    }
  }

  // Send completed progress update
  sendProgressUpdate(
    commandId,
    'scan_text_nodes',
    'completed',
    100,
    totalNodes,
    processedNodes,
    `Scan complete. Found ${allTextNodes.length} text nodes.`,
    {
      textNodes: allTextNodes,
      processedNodes,
      chunks: chunksProcessed
    }
  );

  return {
    success: true,
    message: `Chunked scan complete. Found ${allTextNodes.length} text nodes.`,
    totalNodes: allTextNodes.length,
    processedNodes: processedNodes,
    chunks: chunksProcessed,
    textNodes: allTextNodes,
    commandId
  };
}

// Helper function to collect all nodes that need to be processed
async function collectNodesToProcess(node, parentPath = [], depth = 0, nodesToProcess = []) {
  // Skip invisible nodes
  if (node.visible === false) return;

  // Get the path to this node
  const nodePath = [...parentPath, node.name || `Unnamed ${node.type}`];

  // Add this node to the processing list
  nodesToProcess.push({
    node: node,
    parentPath: nodePath,
    depth: depth
  });

  // Recursively add children
  if ("children" in node) {
    for (const child of node.children) {
      await collectNodesToProcess(child, nodePath, depth + 1, nodesToProcess);
    }
  }
}

// Process a single text node
async function processTextNode(node, parentPath, depth) {
  if (node.type !== "TEXT") return null;

  try {
    // Safely extract font information
    let fontFamily = "";
    let fontStyle = "";

    if (node.fontName) {
      if (typeof node.fontName === "object") {
        if ("family" in node.fontName) fontFamily = node.fontName.family;
        if ("style" in node.fontName) fontStyle = node.fontName.style;
      }
    }

    // Create a safe representation of the text node
    const safeTextNode = {
      id: node.id,
      name: node.name || "Text",
      type: node.type,
      characters: node.characters,
      fontSize: typeof node.fontSize === "number" ? node.fontSize : 0,
      fontFamily: fontFamily,
      fontStyle: fontStyle,
      x: typeof node.x === "number" ? node.x : 0,
      y: typeof node.y === "number" ? node.y : 0,
      width: typeof node.width === "number" ? node.width : 0,
      height: typeof node.height === "number" ? node.height : 0,
      path: parentPath.join(" > "),
      depth: depth,
    };

    // Highlight the node briefly (optional visual feedback)
    try {
      const originalFills = JSON.parse(JSON.stringify(node.fills));
      node.fills = [
        {
          type: "SOLID",
          color: { r: 1, g: 0.5, b: 0 },
          opacity: 0.3,
        },
      ];

      // Brief delay for the highlight to be visible
      await delay(100);

      try {
        node.fills = originalFills;
      } catch (err) {
        console.error("Error resetting fills:", err);
      }
    } catch (highlightErr) {
      console.error("Error highlighting text node:", highlightErr);
      // Continue anyway, highlighting is just visual feedback
    }

    return safeTextNode;
  } catch (nodeErr) {
    console.error("Error processing text node:", nodeErr);
    return null;
  }
}

// A delay function that returns a promise
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Keep the original findTextNodes for backward compatibility
async function findTextNodes(node, parentPath = [], depth = 0, textNodes = []) {
  // Skip invisible nodes
  if (node.visible === false) return;

  // Get the path to this node including its name
  const nodePath = [...parentPath, node.name || `Unnamed ${node.type}`];

  if (node.type === "TEXT") {
    try {
      // Safely extract font information to avoid Symbol serialization issues
      let fontFamily = "";
      let fontStyle = "";

      if (node.fontName) {
        if (typeof node.fontName === "object") {
          if ("family" in node.fontName) fontFamily = node.fontName.family;
          if ("style" in node.fontName) fontStyle = node.fontName.style;
        }
      }

      // Create a safe representation of the text node with only serializable properties
      const safeTextNode = {
        id: node.id,
        name: node.name || "Text",
        type: node.type,
        characters: node.characters,
        fontSize: typeof node.fontSize === "number" ? node.fontSize : 0,
        fontFamily: fontFamily,
        fontStyle: fontStyle,
        x: typeof node.x === "number" ? node.x : 0,
        y: typeof node.y === "number" ? node.y : 0,
        width: typeof node.width === "number" ? node.width : 0,
        height: typeof node.height === "number" ? node.height : 0,
        path: nodePath.join(" > "),
        depth: depth,
      };

      // Only highlight the node if it's not being done via API
      try {
        // Safe way to create a temporary highlight without causing serialization issues
        const originalFills = JSON.parse(JSON.stringify(node.fills));
        node.fills = [
          {
            type: "SOLID",
            color: { r: 1, g: 0.5, b: 0 },
            opacity: 0.3,
          },
        ];

        // Promise-based delay instead of setTimeout
        await delay(500);

        try {
          node.fills = originalFills;
        } catch (err) {
          console.error("Error resetting fills:", err);
        }
      } catch (highlightErr) {
        console.error("Error highlighting text node:", highlightErr);
        // Continue anyway, highlighting is just visual feedback
      }

      textNodes.push(safeTextNode);
    } catch (nodeErr) {
      console.error("Error processing text node:", nodeErr);
      // Skip this node but continue with others
    }
  }

  // Recursively process children of container nodes
  if ("children" in node) {
    for (const child of node.children) {
      await findTextNodes(child, nodePath, depth + 1, textNodes);
    }
  }
}

// Replace text in a specific node
async function setMultipleTextContents(params) {
  const { nodeId, text } = params || {};
  const commandId = params.commandId || generateCommandId();

  if (!nodeId || !text || !Array.isArray(text)) {
    const errorMsg = "Missing required parameters: nodeId and text array";

    // Send error progress update
    sendProgressUpdate(
      commandId,
      'set_multiple_text_contents',
      'error',
      0,
      0,
      0,
      errorMsg,
      { error: errorMsg }
    );

    throw new Error(errorMsg);
  }

  console.log(
    `Starting text replacement for node: ${nodeId} with ${text.length} text replacements`
  );

  // Send started progress update
  sendProgressUpdate(
    commandId,
    'set_multiple_text_contents',
    'started',
    0,
    text.length,
    0,
    `Starting text replacement for ${text.length} nodes`,
    { totalReplacements: text.length }
  );

  // Define the results array and counters
  const results = [];
  let successCount = 0;
  let failureCount = 0;

  // Split text replacements into chunks of 5
  const CHUNK_SIZE = 5;
  const chunks = [];

  for (let i = 0; i < text.length; i += CHUNK_SIZE) {
    chunks.push(text.slice(i, i + CHUNK_SIZE));
  }

  console.log(`Split ${text.length} replacements into ${chunks.length} chunks`);

  // Send chunking info update
  sendProgressUpdate(
    commandId,
    'set_multiple_text_contents',
    'in_progress',
    5, // 5% progress for planning phase
    text.length,
    0,
    `Preparing to replace text in ${text.length} nodes using ${chunks.length} chunks`,
    {
      totalReplacements: text.length,
      chunks: chunks.length,
      chunkSize: CHUNK_SIZE
    }
  );

  // Process each chunk sequentially
  for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
    const chunk = chunks[chunkIndex];
    console.log(`Processing chunk ${chunkIndex + 1}/${chunks.length} with ${chunk.length} replacements`);

    // Send chunk processing start update
    sendProgressUpdate(
      commandId,
      'set_multiple_text_contents',
      'in_progress',
      Math.round(5 + ((chunkIndex / chunks.length) * 90)), // 5-95% for processing
      text.length,
      successCount + failureCount,
      `Processing text replacements chunk ${chunkIndex + 1}/${chunks.length}`,
      {
        currentChunk: chunkIndex + 1,
        totalChunks: chunks.length,
        successCount,
        failureCount
      }
    );

    // Process replacements within a chunk in parallel
    const chunkPromises = chunk.map(async (replacement) => {
      if (!replacement.nodeId || replacement.text === undefined) {
        console.error(`Missing nodeId or text for replacement`);
        return {
          success: false,
          nodeId: replacement.nodeId || "unknown",
          error: "Missing nodeId or text in replacement entry"
        };
      }

      try {
        console.log(`Attempting to replace text in node: ${replacement.nodeId}`);

        // Get the text node to update (just to check it exists and get original text)
        const textNode = await figma.getNodeByIdAsync(replacement.nodeId);

        if (!textNode) {
          console.error(`Text node not found: ${replacement.nodeId}`);
          return {
            success: false,
            nodeId: replacement.nodeId,
            error: `Node not found: ${replacement.nodeId}`
          };
        }

        if (textNode.type !== "TEXT") {
          console.error(`Node is not a text node: ${replacement.nodeId} (type: ${textNode.type})`);
          return {
            success: false,
            nodeId: replacement.nodeId,
            error: `Node is not a text node: ${replacement.nodeId} (type: ${textNode.type})`
          };
        }

        // Save original text for the result
        const originalText = textNode.characters;
        console.log(`Original text: "${originalText}"`);
        console.log(`Will translate to: "${replacement.text}"`);

        // Highlight the node before changing text
        let originalFills;
        try {
          // Save original fills for restoration later
          originalFills = JSON.parse(JSON.stringify(textNode.fills));
          // Apply highlight color (orange with 30% opacity)
          textNode.fills = [
            {
              type: "SOLID",
              color: { r: 1, g: 0.5, b: 0 },
              opacity: 0.3,
            },
          ];
        } catch (highlightErr) {
          console.error(`Error highlighting text node: ${highlightErr.message}`);
          // Continue anyway, highlighting is just visual feedback
        }

        // Use the existing setTextContent function to handle font loading and text setting
        await setTextContent({
          nodeId: replacement.nodeId,
          text: replacement.text
        });

        // Keep highlight for a moment after text change, then restore original fills
        if (originalFills) {
          try {
            // Use delay function for consistent timing
            await delay(500);
            textNode.fills = originalFills;
          } catch (restoreErr) {
            console.error(`Error restoring fills: ${restoreErr.message}`);
          }
        }

        console.log(`Successfully replaced text in node: ${replacement.nodeId}`);
        return {
          success: true,
          nodeId: replacement.nodeId,
          originalText: originalText,
          translatedText: replacement.text
        };
      } catch (error) {
        console.error(`Error replacing text in node ${replacement.nodeId}: ${error.message}`);
        return {
          success: false,
          nodeId: replacement.nodeId,
          error: `Error applying replacement: ${error.message}`
        };
      }
    });

    // Wait for all replacements in this chunk to complete
    const chunkResults = await Promise.all(chunkPromises);

    // Process results for this chunk
    chunkResults.forEach(result => {
      if (result.success) {
        successCount++;
      } else {
        failureCount++;
      }
      results.push(result);
    });

    // Send chunk processing complete update with partial results
    sendProgressUpdate(
      commandId,
      'set_multiple_text_contents',
      'in_progress',
      Math.round(5 + (((chunkIndex + 1) / chunks.length) * 90)), // 5-95% for processing
      text.length,
      successCount + failureCount,
      `Completed chunk ${chunkIndex + 1}/${chunks.length}. ${successCount} successful, ${failureCount} failed so far.`,
      {
        currentChunk: chunkIndex + 1,
        totalChunks: chunks.length,
        successCount,
        failureCount,
        chunkResults: chunkResults
      }
    );

    // Add a small delay between chunks to avoid overloading Figma
    if (chunkIndex < chunks.length - 1) {
      console.log('Pausing between chunks to avoid overloading Figma...');
      await delay(1000); // 1 second delay between chunks
    }
  }

  console.log(
    `Replacement complete: ${successCount} successful, ${failureCount} failed`
  );

  // Send completed progress update
  sendProgressUpdate(
    commandId,
    'set_multiple_text_contents',
    'completed',
    100,
    text.length,
    successCount + failureCount,
    `Text replacement complete: ${successCount} successful, ${failureCount} failed`,
    {
      totalReplacements: text.length,
      replacementsApplied: successCount,
      replacementsFailed: failureCount,
      completedInChunks: chunks.length,
      results: results
    }
  );

  return {
    success: successCount > 0,
    nodeId: nodeId,
    replacementsApplied: successCount,
    replacementsFailed: failureCount,
    totalReplacements: text.length,
    results: results,
    completedInChunks: chunks.length,
    commandId
  };
}

// Function to generate simple UUIDs for command IDs
function generateCommandId() {
  return 'cmd_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

async function setAutoLayout(params) {
  const {
    nodeId,
    layoutMode,
    paddingTop,
    paddingBottom,
    paddingLeft,
    paddingRight,
    itemSpacing,
    primaryAxisAlignItems,
    counterAxisAlignItems,
    layoutWrap,
    strokesIncludedInLayout,
    clipsContent
  } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (!layoutMode) {
    throw new Error("Missing layoutMode parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  // Check if the node is a frame or group
  if (!("layoutMode" in node)) {
    throw new Error(`Node does not support auto layout: ${nodeId}`);
  }

  // Configure layout mode
  if (layoutMode === "NONE") {
    node.layoutMode = "NONE";
  } else {
    // Set auto layout properties
    node.layoutMode = layoutMode;

    // Configure padding if provided
    if (paddingTop !== undefined) node.paddingTop = paddingTop;
    if (paddingBottom !== undefined) node.paddingBottom = paddingBottom;
    if (paddingLeft !== undefined) node.paddingLeft = paddingLeft;
    if (paddingRight !== undefined) node.paddingRight = paddingRight;

    // Configure item spacing
    if (itemSpacing !== undefined) node.itemSpacing = itemSpacing;

    // Configure alignment (with validation to prevent Figma API errors)
    if (primaryAxisAlignItems !== undefined) {
      const vp = ["MIN", "CENTER", "MAX", "SPACE_BETWEEN"];
      const pv = String(primaryAxisAlignItems).toUpperCase().replace(/-/g, "_");
      node.primaryAxisAlignItems = vp.includes(pv) ? pv : "MIN";
    }

    if (counterAxisAlignItems !== undefined) {
      const vc = ["MIN", "CENTER", "MAX", "BASELINE"];
      const cv = String(counterAxisAlignItems).toUpperCase().replace(/-/g, "_");
      node.counterAxisAlignItems = vc.includes(cv) ? cv : "MIN";
    }

    // Configure wrap
    if (layoutWrap !== undefined) {
      node.layoutWrap = layoutWrap;
    }

    // Configure stroke inclusion
    if (strokesIncludedInLayout !== undefined) {
      node.strokesIncludedInLayout = strokesIncludedInLayout;
    }

    // Configure clips content
    if (clipsContent !== undefined) {
      node.clipsContent = clipsContent;
    }
  }

  return {
    id: node.id,
    name: node.name,
    layoutMode: node.layoutMode,
    paddingTop: node.paddingTop,
    paddingBottom: node.paddingBottom,
    paddingLeft: node.paddingLeft,
    paddingRight: node.paddingRight,
    itemSpacing: node.itemSpacing,
    primaryAxisAlignItems: node.primaryAxisAlignItems,
    counterAxisAlignItems: node.counterAxisAlignItems,
    layoutWrap: node.layoutWrap,
    strokesIncludedInLayout: node.strokesIncludedInLayout,
    clipsContent: node.clipsContent
  };
}

async function setLayoutSizing(params) {
  var nodeId = (params || {}).nodeId;
  var layoutSizingHorizontal = (params || {}).layoutSizingHorizontal;
  var layoutSizingVertical = (params || {}).layoutSizingVertical;
  var horizontal = (params || {}).horizontal;
  var vertical = (params || {}).vertical;
  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error("Node not found with ID: " + nodeId);
  }

  var hMode = layoutSizingHorizontal || horizontal;
  var vMode = layoutSizingVertical || vertical;

  if (hMode) {
    node.layoutSizingHorizontal = hMode;
  }
  if (vMode) {
    node.layoutSizingVertical = vMode;
  }

  return {
    nodeId: node.id,
    name: node.name,
    layoutSizingHorizontal: node.layoutSizingHorizontal,
    layoutSizingVertical: node.layoutSizingVertical
  };
}

// Batch set layout sizing on multiple nodes in a single command — avoids N round trips
// and consolidates layout reflows. Items: [{nodeId, horizontal, vertical}]
async function setLayoutSizingBatch(params) {
  var items = (params || {}).items;
  if (!items || !Array.isArray(items)) {
    throw new Error("Missing items array parameter");
  }

  var results = [];
  var errors = [];

  // Phase 1: Resolve all nodes first (async)
  var nodes = [];
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    if (!item.nodeId) {
      errors.push({ index: i, error: "Missing nodeId" });
      nodes.push(null);
      continue;
    }
    var node = await figma.getNodeByIdAsync(item.nodeId);
    if (!node) {
      errors.push({ index: i, nodeId: item.nodeId, error: "Node not found" });
      nodes.push(null);
      continue;
    }
    nodes.push(node);
  }

  // Phase 2: Apply all sizing mutations synchronously (single reflow)
  for (var j = 0; j < items.length; j++) {
    var n = nodes[j];
    if (!n) continue;
    var it = items[j];
    var h = it.layoutSizingHorizontal || it.horizontal;
    var v = it.layoutSizingVertical || it.vertical;
    try {
      if (h) n.layoutSizingHorizontal = h;
      if (v) n.layoutSizingVertical = v;
      results.push({
        index: j,
        nodeId: n.id,
        name: n.name,
        layoutSizingHorizontal: n.layoutSizingHorizontal,
        layoutSizingVertical: n.layoutSizingVertical,
        success: true
      });
    } catch (e) {
      errors.push({ index: j, nodeId: n.id, error: e.message || String(e) });
    }
  }

  return {
    total: items.length,
    succeeded: results.length,
    failed: errors.length,
    results: results,
    errors: errors
  };
}

async function setLayoutPositioning(params) {
  var nodeId = (params || {}).nodeId;
  var positioning = (params || {}).layoutPositioning || "ABSOLUTE";
  if (!nodeId) throw new Error("Missing nodeId parameter");

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) throw new Error("Node not found: " + nodeId);

  node.layoutPositioning = positioning;

  // Also set constraints if provided
  if (params.constraints) {
    node.constraints = params.constraints;
  }

  return {
    nodeId: node.id,
    name: node.name,
    layoutPositioning: node.layoutPositioning,
    constraints: node.constraints
  };
}

// Nuevas funciones para propiedades de texto

async function setFontName(params) {
  const { nodeId, family, style } = params || {};
  if (!nodeId || !family) {
    throw new Error("Missing nodeId or font family");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout({ family, style: style || "Regular" });
    node.fontName = { family, style: style || "Regular" };
    return {
      id: node.id,
      name: node.name,
      fontName: node.fontName
    };
  } catch (error) {
    throw new Error(`Error setting font name: ${error.message}`);
  }
}

async function setFontSize(params) {
  const { nodeId, fontSize } = params || {};
  if (!nodeId || fontSize === undefined) {
    throw new Error("Missing nodeId or fontSize");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    node.fontSize = fontSize;
    return {
      id: node.id,
      name: node.name,
      fontSize: node.fontSize
    };
  } catch (error) {
    throw new Error(`Error setting font size: ${error.message}`);
  }
}

async function setRangeFontSize(params) {
  var nodeId = (params && params.nodeId) ? params.nodeId : null;
  var ranges = (params && params.ranges) ? params.ranges : null;

  if (!nodeId || !ranges || !Array.isArray(ranges)) {
    throw new Error("Missing nodeId or ranges. Expected { nodeId, ranges: [{ start, end, fontSize }] }");
  }

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error("Node not found with ID: " + nodeId);
  }
  if (node.type !== "TEXT") {
    throw new Error("Node is not a text node: " + nodeId);
  }

  // Load all fonts used in the text node
  var len = node.characters.length;
  for (var i = 0; i < len; i++) {
    var fontAtPos = node.getRangeFontName(i, i + 1);
    await loadFontWithTimeout(fontAtPos);
  }

  var applied = [];
  for (var r = 0; r < ranges.length; r++) {
    var range = ranges[r];
    var start = range.start;
    var end = range.end;
    var fontSize = range.fontSize;
    node.setRangeFontSize(start, end, fontSize);
    applied.push({ start: start, end: end, fontSize: fontSize });
  }

  return {
    id: node.id,
    name: node.name,
    characters: node.characters,
    applied: applied
  };
}

async function setFontWeight(params) {
  const { nodeId, weight } = params || {};
  if (!nodeId || weight === undefined) {
    throw new Error("Missing nodeId or weight");
  }

  // Map weight to font style
  const getFontStyle = (weight) => {
    switch (weight) {
      case 100: return "Thin";
      case 200: return "Extra Light";
      case 300: return "Light";
      case 400: return "Regular";
      case 500: return "Medium";
      case 600: return "Semi Bold";
      case 700: return "Bold";
      case 800: return "Extra Bold";
      case 900: return "Black";
      default: return "Regular";
    }
  };

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    const family = node.fontName.family;
    const style = getFontStyle(weight);
    await loadFontWithTimeout({ family, style });
    node.fontName = { family, style };
    return {
      id: node.id,
      name: node.name,
      fontName: node.fontName,
      weight: weight
    };
  } catch (error) {
    throw new Error(`Error setting font weight: ${error.message}`);
  }
}

async function setLetterSpacing(params) {
  const { nodeId, letterSpacing, unit = "PIXELS" } = params || {};
  if (!nodeId || letterSpacing === undefined) {
    throw new Error("Missing nodeId or letterSpacing");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    node.letterSpacing = { value: letterSpacing, unit };
    return {
      id: node.id,
      name: node.name,
      letterSpacing: node.letterSpacing
    };
  } catch (error) {
    throw new Error(`Error setting letter spacing: ${error.message}`);
  }
}

async function setLineHeight(params) {
  const { nodeId, lineHeight, unit = "PIXELS" } = params || {};
  if (!nodeId || lineHeight === undefined) {
    throw new Error("Missing nodeId or lineHeight");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    node.lineHeight = { value: lineHeight, unit };
    return {
      id: node.id,
      name: node.name,
      lineHeight: node.lineHeight
    };
  } catch (error) {
    throw new Error(`Error setting line height: ${error.message}`);
  }
}

async function setParagraphSpacing(params) {
  const { nodeId, paragraphSpacing } = params || {};
  if (!nodeId || paragraphSpacing === undefined) {
    throw new Error("Missing nodeId or paragraphSpacing");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    node.paragraphSpacing = paragraphSpacing;
    return {
      id: node.id,
      name: node.name,
      paragraphSpacing: node.paragraphSpacing
    };
  } catch (error) {
    throw new Error(`Error setting paragraph spacing: ${error.message}`);
  }
}

async function setTextCase(params) {
  const { nodeId, textCase } = params || {};
  if (!nodeId || textCase === undefined) {
    throw new Error("Missing nodeId or textCase");
  }

  // Valid textCase values: "ORIGINAL", "UPPER", "LOWER", "TITLE"
  if (!["ORIGINAL", "UPPER", "LOWER", "TITLE"].includes(textCase)) {
    throw new Error("Invalid textCase value. Must be one of: ORIGINAL, UPPER, LOWER, TITLE");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    node.textCase = textCase;
    return {
      id: node.id,
      name: node.name,
      textCase: node.textCase
    };
  } catch (error) {
    throw new Error(`Error setting text case: ${error.message}`);
  }
}

async function setTextDecoration(params) {
  const { nodeId, textDecoration } = params || {};
  if (!nodeId || textDecoration === undefined) {
    throw new Error("Missing nodeId or textDecoration");
  }

  // Valid textDecoration values: "NONE", "UNDERLINE", "STRIKETHROUGH"
  if (!["NONE", "UNDERLINE", "STRIKETHROUGH"].includes(textDecoration)) {
    throw new Error("Invalid textDecoration value. Must be one of: NONE, UNDERLINE, STRIKETHROUGH");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    node.textDecoration = textDecoration;
    return {
      id: node.id,
      name: node.name,
      textDecoration: node.textDecoration
    };
  } catch (error) {
    throw new Error(`Error setting text decoration: ${error.message}`);
  }
}

async function setTextAlign(params) {
  const { nodeId, textAlignHorizontal, textAlignVertical } = params || {};
  if (!nodeId) {
    throw new Error("Missing nodeId");
  }

  const validHorizontal = ["LEFT", "CENTER", "RIGHT", "JUSTIFIED"];
  const validVertical = ["TOP", "CENTER", "BOTTOM"];

  if (textAlignHorizontal && !validHorizontal.includes(textAlignHorizontal)) {
    throw new Error("Invalid textAlignHorizontal value. Must be one of: LEFT, CENTER, RIGHT, JUSTIFIED");
  }

  if (textAlignVertical && !validVertical.includes(textAlignVertical)) {
    throw new Error("Invalid textAlignVertical value. Must be one of: TOP, CENTER, BOTTOM");
  }

  if (!textAlignHorizontal && !textAlignVertical) {
    throw new Error("Must provide textAlignHorizontal or textAlignVertical");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    await loadFontWithTimeout(node.fontName);
    if (textAlignHorizontal) {
      node.textAlignHorizontal = textAlignHorizontal;
    }
    if (textAlignVertical) {
      node.textAlignVertical = textAlignVertical;
    }
    return {
      id: node.id,
      name: node.name,
      textAlignHorizontal: node.textAlignHorizontal,
      textAlignVertical: node.textAlignVertical
    };
  } catch (error) {
    throw new Error(`Error setting text alignment: ${error.message}`);
  }
}

// Consolidated text properties handler
async function setTextProperties(params) {
  var _params = params || {};
  var nodeId = _params.nodeId;
  if (!nodeId) {
    throw new Error("Missing nodeId");
  }

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error("Node not found with ID: " + nodeId);
  }
  if (node.type !== "TEXT") {
    throw new Error("Node is not a text node: " + nodeId);
  }

  var applied = [];

  // Weight-to-style mapping
  var getFontStyle = function(weight) {
    switch (weight) {
      case 100: return "Thin";
      case 200: return "Extra Light";
      case 300: return "Light";
      case 400: return "Regular";
      case 500: return "Medium";
      case 600: return "Semi Bold";
      case 700: return "Bold";
      case 800: return "Extra Bold";
      case 900: return "Black";
      default: return "Regular";
    }
  };

  try {
    // Determine the target font: if fontFamily or fontWeight is specified, we need to load a new font
    var currentFont = node.fontName;
    var targetFamily = _params.fontFamily || currentFont.family;
    var targetStyle = _params.fontStyle || currentFont.style;

    // fontWeight overrides fontStyle
    if (_params.fontWeight !== undefined && _params.fontWeight !== null) {
      targetStyle = getFontStyle(_params.fontWeight);
    }

    // Load the target font first (needed for any text property change)
    await loadFontWithTimeout({ family: targetFamily, style: targetStyle });

    // Apply font family/style change
    if (_params.fontFamily || _params.fontStyle || _params.fontWeight !== undefined && _params.fontWeight !== null) {
      node.fontName = { family: targetFamily, style: targetStyle };
      applied.push("font: " + targetFamily + " " + targetStyle);
    }

    // Apply fontSize
    if (_params.fontSize !== undefined && _params.fontSize !== null) {
      node.fontSize = _params.fontSize;
      applied.push("fontSize: " + _params.fontSize);
    }

    // Apply letterSpacing
    if (_params.letterSpacing !== undefined && _params.letterSpacing !== null) {
      var lsUnit = _params.letterSpacingUnit || "PIXELS";
      node.letterSpacing = { value: _params.letterSpacing, unit: lsUnit };
      applied.push("letterSpacing: " + _params.letterSpacing + " " + lsUnit);
    }

    // Apply lineHeight
    if (_params.lineHeight !== undefined && _params.lineHeight !== null) {
      var lhUnit = _params.lineHeightUnit || "PIXELS";
      node.lineHeight = { value: _params.lineHeight, unit: lhUnit };
      applied.push("lineHeight: " + _params.lineHeight + " " + lhUnit);
    }

    // Apply paragraphSpacing
    if (_params.paragraphSpacing !== undefined && _params.paragraphSpacing !== null) {
      node.paragraphSpacing = _params.paragraphSpacing;
      applied.push("paragraphSpacing: " + _params.paragraphSpacing);
    }

    // Apply textCase
    if (_params.textCase) {
      node.textCase = _params.textCase;
      applied.push("textCase: " + _params.textCase);
    }

    // Apply textDecoration
    if (_params.textDecoration) {
      node.textDecoration = _params.textDecoration;
      applied.push("textDecoration: " + _params.textDecoration);
    }

    // Apply text alignment
    if (_params.textAlignHorizontal) {
      node.textAlignHorizontal = _params.textAlignHorizontal;
      applied.push("textAlignHorizontal: " + _params.textAlignHorizontal);
    }
    if (_params.textAlignVertical) {
      node.textAlignVertical = _params.textAlignVertical;
      applied.push("textAlignVertical: " + _params.textAlignVertical);
    }

    // Apply textAutoResize
    if (_params.textAutoResize) {
      var validResize = ["WIDTH_AND_HEIGHT", "HEIGHT", "NONE", "TRUNCATE"];
      if (validResize.indexOf(_params.textAutoResize) !== -1) {
        node.textAutoResize = _params.textAutoResize;
        applied.push("textAutoResize: " + _params.textAutoResize);
      }
    }

    // Apply maxLines
    if (_params.maxLines !== undefined && _params.maxLines !== null) {
      var ml = parseInt(_params.maxLines);
      if (ml > 0) {
        node.maxLines = ml;
        applied.push("maxLines: " + ml);
      }
    }

    if (applied.length === 0) {
      applied.push("no changes (no properties specified)");
    }

    return {
      id: node.id,
      name: node.name,
      applied: applied
    };
  } catch (error) {
    throw new Error("Error setting text properties: " + error.message);
  }
}

async function getStyledTextSegments(params) {
  const { nodeId, property } = params || {};
  if (!nodeId || !property) {
    throw new Error("Missing nodeId or property");
  }

  // Valid properties: "fillStyleId", "fontName", "fontSize", "textCase", 
  // "textDecoration", "textStyleId", "fills", "letterSpacing", "lineHeight", "fontWeight"
  const validProperties = [
    "fillStyleId", "fontName", "fontSize", "textCase",
    "textDecoration", "textStyleId", "fills", "letterSpacing",
    "lineHeight", "fontWeight"
  ];

  if (!validProperties.includes(property)) {
    throw new Error(`Invalid property. Must be one of: ${validProperties.join(", ")}`);
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type !== "TEXT") {
    throw new Error(`Node is not a text node: ${nodeId}`);
  }

  try {
    const segments = node.getStyledTextSegments([property]);

    // Prepare segments data in a format safe for serialization
    const safeSegments = segments.map(segment => {
      const safeSegment = {
        characters: segment.characters,
        start: segment.start,
        end: segment.end
      };

      // Handle different property types for safe serialization
      if (property === "fontName") {
        if (segment[property] && typeof segment[property] === "object") {
          safeSegment[property] = {
            family: segment[property].family || "",
            style: segment[property].style || ""
          };
        } else {
          safeSegment[property] = { family: "", style: "" };
        }
      } else if (property === "letterSpacing" || property === "lineHeight") {
        // Handle spacing properties which have a value and unit
        if (segment[property] && typeof segment[property] === "object") {
          safeSegment[property] = {
            value: segment[property].value || 0,
            unit: segment[property].unit || "PIXELS"
          };
        } else {
          safeSegment[property] = { value: 0, unit: "PIXELS" };
        }
      } else if (property === "fills") {
        // Handle fills which can be complex
        safeSegment[property] = segment[property] ? JSON.parse(JSON.stringify(segment[property])) : [];
      } else {
        // Handle simple properties
        safeSegment[property] = segment[property];
      }

      return safeSegment;
    });

    return {
      id: node.id,
      name: node.name,
      property: property,
      segments: safeSegments
    };
  } catch (error) {
    throw new Error(`Error getting styled text segments: ${error.message}`);
  }
}

// Helper: wrap figma.loadFontAsync with a timeout to prevent infinite hang
// Save raw reference so global replace won't cause recursion
var _origLoadFontAsync = figma.loadFontAsync.bind(figma);
function loadFontWithTimeout(fontName, timeoutMs) {
  timeoutMs = timeoutMs || 10000;
  return new Promise(function(resolve, reject) {
    var timer = setTimeout(function() {
      reject(new Error("Font loading timed out after " + (timeoutMs / 1000) + "s for " + fontName.family + " " + fontName.style));
    }, timeoutMs);
    _origLoadFontAsync(fontName).then(function(result) {
      clearTimeout(timer);
      resolve(result);
    }).catch(function(err) {
      clearTimeout(timer);
      reject(err);
    });
  });
}

async function loadFontAsyncWrapper(params) {
  var family = (params && params.family) ? params.family : undefined;
  var style = (params && params.style) ? params.style : "Regular";
  if (!family) {
    throw new Error("Missing font family");
  }

  try {
    await loadFontWithTimeout({ family: family, style: style }, 10000);
    return {
      success: true,
      family: family,
      style: style,
      message: "Successfully loaded " + family + " " + style
    };
  } catch (error) {
    throw new Error("Error loading font: " + error.message);
  }
}

async function getRemoteComponents() {
  try {
    // Check if figma.teamLibrary is available
    if (!figma.teamLibrary) {
      console.error("Error: figma.teamLibrary API is not available");
      throw new Error("The figma.teamLibrary API is not available in this context");
    }

    // Check if figma.teamLibrary.getAvailableComponentsAsync exists
    if (!figma.teamLibrary.getAvailableComponentsAsync) {
      console.error("Error: figma.teamLibrary.getAvailableComponentsAsync is not available");
      throw new Error("The getAvailableComponentsAsync method is not available");
    }

    console.log("Starting remote components retrieval...");

    // Set up a manual timeout to detect deadlocks
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error("Internal timeout while retrieving remote components (45s)"));
      }, 45000); // 45 seconds internal timeout
    });

    // Execute the request with a manual timeout
    const fetchPromise = figma.teamLibrary.getAvailableComponentsAsync();

    // Use Promise.race to implement the timeout
    const teamComponents = await Promise.race([fetchPromise, timeoutPromise])
      .finally(() => {
        clearTimeout(timeoutId); // Clear the timeout
      });

    console.log(`Retrieved ${teamComponents.length} remote components`);

    return {
      success: true,
      count: teamComponents.length,
      components: teamComponents.map(component => ({
        key: component.key,
        name: component.name,
        description: component.description || "",
        libraryName: component.libraryName
      }))
    };
  } catch (error) {
    console.error(`Detailed error retrieving remote components: ${error.message || "Unknown error"}`);
    console.error(`Stack trace: ${error.stack || "Not available"}`);

    // Instead of returning an error object, throw an exception with the error message
    throw new Error(`Error retrieving remote components: ${error.message}`);
  }
}

// Set Effects Tool
async function setEffects(params) {
  const { nodeId, effects } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (!effects || !Array.isArray(effects)) {
    throw new Error("Missing or invalid effects parameter. Must be an array.");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (!("effects" in node)) {
    throw new Error(`Node does not support effects: ${nodeId}`);
  }

  try {
    // Convert incoming effects to valid Figma effects
    const validEffects = effects.map(effect => {
      // Ensure all effects have the required properties
      if (!effect.type) {
        throw new Error("Each effect must have a type property");
      }

      // Create a clean effect object based on type
      switch (effect.type) {
        case "DROP_SHADOW":
        case "INNER_SHADOW":
          return {
            type: effect.type,
            color: effect.color || { r: 0, g: 0, b: 0, a: 0.5 },
            offset: effect.offset || { x: 0, y: 0 },
            radius: effect.radius || 5,
            spread: effect.spread || 0,
            visible: effect.visible !== undefined ? effect.visible : true,
            blendMode: effect.blendMode || "NORMAL"
          };
        case "LAYER_BLUR":
        case "BACKGROUND_BLUR":
          return {
            type: effect.type,
            radius: effect.radius || 5,
            visible: effect.visible !== undefined ? effect.visible : true
          };
        default:
          throw new Error(`Unsupported effect type: ${effect.type}`);
      }
    });

    // Apply the effects to the node
    node.effects = validEffects;

    return {
      id: node.id,
      name: node.name,
      effects: node.effects
    };
  } catch (error) {
    throw new Error(`Error setting effects: ${error.message}`);
  }
}

// Set Effect Style ID Tool
async function setEffectStyleId(params) {
  const { nodeId, effectStyleId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (!effectStyleId) {
    throw new Error("Missing effectStyleId parameter");
  }

  try {
    // Set up a manual timeout to detect long operations
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error("Timeout while setting effect style ID (20s). The operation took too long to complete."));
      }, 20000); // 20 seconds timeout
    });

    console.log(`Starting to set effect style ID ${effectStyleId} on node ${nodeId}...`);

    // Get node and validate in a promise
    const nodePromise = (async () => {
      const node = await figma.getNodeByIdAsync(nodeId);
      if (!node) {
        throw new Error(`Node not found with ID: ${nodeId}`);
      }

      if (!("effectStyleId" in node)) {
        throw new Error(`Node with ID ${nodeId} does not support effect styles`);
      }

      // Try to validate the effect style exists before applying
      console.log(`Fetching effect styles to validate style ID: ${effectStyleId}`);
      const effectStyles = await figma.getLocalEffectStylesAsync();
      const foundStyle = effectStyles.find(style => style.id === effectStyleId);

      if (!foundStyle) {
        throw new Error(`Effect style not found with ID: ${effectStyleId}. Available styles: ${effectStyles.length}`);
      }

      console.log(`Effect style found, applying to node...`);

      // Apply the effect style to the node
      node.effectStyleId = effectStyleId;

      return {
        id: node.id,
        name: node.name,
        effectStyleId: node.effectStyleId,
        appliedEffects: node.effects
      };
    })();

    // Race between the node operation and the timeout
    const result = await Promise.race([nodePromise, timeoutPromise])
      .finally(() => {
        // Clear the timeout to prevent memory leaks
        clearTimeout(timeoutId);
      });

    console.log(`Successfully set effect style ID on node ${nodeId}`);
    return result;
  } catch (error) {
    console.error(`Error setting effect style ID: ${error.message || "Unknown error"}`);
    console.error(`Stack trace: ${error.stack || "Not available"}`);

    // Proporcionar mensajes de error específicos para diferentes casos
    if (error.message.includes("timeout") || error.message.includes("Timeout")) {
      throw new Error(`The operation timed out after 8 seconds. This could happen with complex nodes or effects. Try with a simpler node or effect style.`);
    } else if (error.message.includes("not found") && error.message.includes("Node")) {
      throw new Error(`Node with ID "${nodeId}" not found. Make sure the node exists in the current document.`);
    } else if (error.message.includes("not found") && error.message.includes("style")) {
      throw new Error(`Effect style with ID "${effectStyleId}" not found. Make sure the style exists in your local styles.`);
    } else if (error.message.includes("does not support")) {
      throw new Error(`The selected node type does not support effect styles. Only certain node types like frames, components, and instances can have effect styles.`);
    } else {
      throw new Error(`Error setting effect style ID: ${error.message}`);
    }
  }
}

// Set Text Style ID Tool
async function setTextStyleId(params) {
  const { nodeId, textStyleId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (!textStyleId) {
    throw new Error("Missing textStyleId parameter");
  }

  try {
    // Set up a manual timeout to detect long operations
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error("Timeout while setting text style ID (8s). The operation took too long to complete."));
      }, 8000); // 8 seconds timeout
    });

    console.log(`Starting to set text style ID ${textStyleId} on node ${nodeId}...`);

    // Get node and validate in a promise
    const nodePromise = (async () => {
      var node = await figma.getNodeByIdAsync(nodeId);
      if (!node) {
        throw new Error("Node not found with ID: " + nodeId);
      }

      if (node.type !== "TEXT") {
        throw new Error("Node with ID " + nodeId + " is not a text node (type: " + node.type + ")");
      }

      // Check if this is a remote library style (S:key,nodeId format)
      var remoteMatch = textStyleId.match(/^S:([^,]+),(.+)$/);
      if (remoteMatch) {
        var styleKey = remoteMatch[1];
        console.log("Importing remote text style with key: " + styleKey);
        var importedStyle = await figma.importStyleByKeyAsync(styleKey);
        if (!importedStyle) {
          throw new Error("Failed to import remote text style with key: " + styleKey);
        }
        console.log("Imported style: " + importedStyle.name + " (id: " + importedStyle.id + ")");
        await loadFontWithTimeout(importedStyle.fontName);
        await node.setTextStyleIdAsync(importedStyle.id);
        return {
          id: node.id,
          name: node.name,
          textStyleId: node.textStyleId,
          styleName: importedStyle.name
        };
      }

      // Local style fallback
      console.log("Fetching local text styles to validate style ID: " + textStyleId);
      var textStyles = await figma.getLocalTextStylesAsync();
      var foundStyle = textStyles.find(function(style) { return style.id === textStyleId || style.key === textStyleId; });

      if (!foundStyle) {
        throw new Error("Text style with ID \"" + textStyleId + "\" not found in local or remote styles.");
      }

      var actualStyleId = foundStyle.id;
      console.log("Text style \"" + foundStyle.name + "\" found, applying to node...");
      await loadFontWithTimeout(foundStyle.fontName);
      await node.setTextStyleIdAsync(actualStyleId);

      return {
        id: node.id,
        name: node.name,
        textStyleId: node.textStyleId,
        styleName: foundStyle.name
      };
    })();

    // Race between the node operation and the timeout
    const result = await Promise.race([nodePromise, timeoutPromise])
      .finally(() => {
        // Clear the timeout to prevent memory leaks
        clearTimeout(timeoutId);
      });

    console.log(`Successfully set text style ID on node ${nodeId}`);
    return result;
  } catch (error) {
    console.error(`Error setting text style ID: ${error.message || "Unknown error"}`);
    console.error(`Stack trace: ${error.stack || "Not available"}`);

    // Provide specific error messages for different cases
    if (error.message.includes("timeout") || error.message.includes("Timeout")) {
      throw new Error(`The operation timed out after 8 seconds. This could happen with complex nodes. Try with a simpler node.`);
    } else if (error.message.includes("not found") && error.message.includes("Node")) {
      throw new Error(`Node with ID "${nodeId}" not found. Make sure the node exists in the current document.`);
    } else if (error.message.includes("not found") && error.message.includes("style")) {
      throw new Error(`Text style with ID "${textStyleId}" not found. Make sure the style exists in your local styles.`);
    } else if (error.message.includes("not a text node")) {
      throw new Error(`The selected node is not a text node. Only text nodes can have text styles applied.`);
    } else {
      throw new Error(`Error setting text style ID: ${error.message}`);
    }
  }
}

// Function to group nodes
async function groupNodes(params) {
  const { nodeIds, name } = params || {};

  if (!nodeIds || !Array.isArray(nodeIds) || nodeIds.length < 2) {
    throw new Error("Must provide at least two nodeIds to group");
  }

  try {
    // Get all nodes to be grouped
    const nodesToGroup = [];
    for (const nodeId of nodeIds) {
      const node = await figma.getNodeByIdAsync(nodeId);
      if (!node) {
        throw new Error(`Node not found with ID: ${nodeId}`);
      }
      nodesToGroup.push(node);
    }

    // Verify that all nodes have the same parent
    const parent = nodesToGroup[0].parent;
    for (const node of nodesToGroup) {
      if (node.parent !== parent) {
        throw new Error("All nodes must have the same parent to be grouped");
      }
    }

    // Create a group and add the nodes to it
    const group = figma.group(nodesToGroup, parent);

    // Optionally set a name for the group
    if (name) {
      group.name = name;
    }

    return {
      id: group.id,
      name: group.name,
      type: group.type,
      children: group.children.map(child => ({ id: child.id, name: child.name, type: child.type }))
    };
  } catch (error) {
    throw new Error(`Error grouping nodes: ${error.message}`);
  }
}

// Function to ungroup nodes
async function ungroupNodes(params) {
  const { nodeId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  try {
    const node = await figma.getNodeByIdAsync(nodeId);
    if (!node) {
      throw new Error(`Node not found with ID: ${nodeId}`);
    }

    // Verify that the node is a group or a frame
    if (node.type !== "GROUP" && node.type !== "FRAME") {
      throw new Error(`Node with ID ${nodeId} is not a GROUP or FRAME`);
    }

    // Get the parent and children before ungrouping
    const parent = node.parent;
    const children = [...node.children];

    // Ungroup the node
    const ungroupedItems = figma.ungroup(node);

    return {
      success: true,
      ungroupedCount: ungroupedItems.length,
      items: ungroupedItems.map(item => ({ id: item.id, name: item.name, type: item.type }))
    };
  } catch (error) {
    throw new Error(`Error ungrouping node: ${error.message}`);
  }
}

// Function to flatten nodes (e.g., boolean operations, convert to path)
async function flattenNode(params) {
  const { nodeId } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  try {
    const node = await figma.getNodeByIdAsync(nodeId);
    if (!node) {
      throw new Error(`Node not found with ID: ${nodeId}`);
    }

    // Check for specific node types that can be flattened
    const flattenableTypes = ["VECTOR", "BOOLEAN_OPERATION", "STAR", "POLYGON", "ELLIPSE", "RECTANGLE"];

    if (!flattenableTypes.includes(node.type)) {
      throw new Error(`Node with ID ${nodeId} and type ${node.type} cannot be flattened. Only vector-based nodes can be flattened.`);
    }

    // Verify the node has the flatten method before calling it
    if (typeof node.flatten !== 'function') {
      throw new Error(`Node with ID ${nodeId} does not support the flatten operation.`);
    }

    // Implement a timeout mechanism
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error("Flatten operation timed out after 20 seconds. The node may be too complex."));
      }, 20000); // 20 seconds timeout
    });

    // Execute the flatten operation in a promise
    const flattenPromise = new Promise((resolve, reject) => {
      // Execute in the next tick to allow UI updates
      setTimeout(() => {
        try {
          console.log(`Starting flatten operation for node ID ${nodeId}...`);
          const flattened = node.flatten();
          console.log(`Flatten operation completed successfully for node ID ${nodeId}`);
          resolve(flattened);
        } catch (err) {
          console.error(`Error during flatten operation: ${err.message}`);
          reject(err);
        }
      }, 0);
    });

    // Race between the timeout and the operation
    const flattened = await Promise.race([flattenPromise, timeoutPromise])
      .finally(() => {
        // Clear the timeout to prevent memory leaks
        clearTimeout(timeoutId);
      });

    return {
      id: flattened.id,
      name: flattened.name,
      type: flattened.type
    };
  } catch (error) {
    console.error(`Error in flattenNode: ${error.message}`);
    if (error.message.includes("timed out")) {
      // Provide a more helpful message for timeout errors
      throw new Error(`The flatten operation timed out. This usually happens with complex nodes. Try simplifying the node first or breaking it into smaller parts.`);
    } else {
      throw new Error(`Error flattening node: ${error.message}`);
    }
  }
}

// Function to insert a child into a parent node
async function insertChild(params) {
  const { parentId, childId, index } = params || {};

  if (!parentId) {
    throw new Error("Missing parentId parameter");
  }

  if (!childId) {
    throw new Error("Missing childId parameter");
  }

  try {
    // Get the parent and child nodes
    const parent = await figma.getNodeByIdAsync(parentId);
    if (!parent) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }

    const child = await figma.getNodeByIdAsync(childId);
    if (!child) {
      throw new Error(`Child node not found with ID: ${childId}`);
    }

    // Check if the parent can have children
    if (!("appendChild" in parent)) {
      throw new Error(`Parent node with ID ${parentId} cannot have children`);
    }

    // Save child's current parent for proper handling
    const originalParent = child.parent;

    // Insert the child at the specified index or append it
    if (index !== undefined && index >= 0 && index <= parent.children.length) {
      parent.insertChild(index, child);
    } else {
      parent.appendChild(child);
    }

    // Set absolute positioning if requested (for overlay elements in auto layout frames)
    if (params.absolute && "layoutPositioning" in child) {
      child.layoutPositioning = "ABSOLUTE";
    }

    // Verify that the insertion worked
    const newIndex = parent.children.indexOf(child);

    return {
      parentId: parent.id,
      childId: child.id,
      index: newIndex,
      success: newIndex !== -1,
      previousParentId: originalParent ? originalParent.id : null
    };
  } catch (error) {
    console.error(`Error inserting child: ${error.message}`, error);
    throw new Error(`Error inserting child: ${error.message}`);
  }
}

async function createEllipse(params) {
  const {
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    name = "Ellipse",
    parentId,
    fillColor = { r: 0.8, g: 0.8, b: 0.8, a: 1 },
    strokeColor,
    strokeWeight
  } = params || {};

  // Create a new ellipse node
  const ellipse = figma.createEllipse();
  ellipse.name = name;

  // Position and size the ellipse
  ellipse.x = x;
  ellipse.y = y;
  ellipse.resize(width, height);

  // Set fill color if provided
  if (fillColor) {
    const fillStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(fillColor.r) || 0,
        g: parseFloat(fillColor.g) || 0,
        b: parseFloat(fillColor.b) || 0,
      },
      opacity: parseFloat(fillColor.a) || 1
    };
    ellipse.fills = [fillStyle];
  }

  // Set stroke color and weight if provided
  if (strokeColor) {
    const strokeStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(strokeColor.r) || 0,
        g: parseFloat(strokeColor.g) || 0,
        b: parseFloat(strokeColor.b) || 0,
      },
      opacity: parseFloat(strokeColor.a) || 1
    };
    ellipse.strokes = [strokeStyle];

    if (strokeWeight) {
      ellipse.strokeWeight = strokeWeight;
    }
  }

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(ellipse);
  } else {
    figma.currentPage.appendChild(ellipse);
  }

  return {
    id: ellipse.id,
    name: ellipse.name,
    type: ellipse.type,
    x: ellipse.x,
    y: ellipse.y,
    width: ellipse.width,
    height: ellipse.height
  };
}

async function createPolygon(params) {
  const {
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    sides = 6,
    name = "Polygon",
    parentId,
    fillColor,
    strokeColor,
    strokeWeight
  } = params || {};

  // Create the polygon
  const polygon = figma.createPolygon();
  polygon.x = x;
  polygon.y = y;
  polygon.resize(width, height);
  polygon.name = name;

  // Set the number of sides
  if (sides >= 3) {
    polygon.pointCount = sides;
  }

  // Set fill color if provided
  if (fillColor) {
    const paintStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(fillColor.r) || 0,
        g: parseFloat(fillColor.g) || 0,
        b: parseFloat(fillColor.b) || 0,
      },
      opacity: parseFloat(fillColor.a) || 1,
    };
    polygon.fills = [paintStyle];
  }

  // Set stroke color and weight if provided
  if (strokeColor) {
    const strokeStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(strokeColor.r) || 0,
        g: parseFloat(strokeColor.g) || 0,
        b: parseFloat(strokeColor.b) || 0,
      },
      opacity: parseFloat(strokeColor.a) || 1,
    };
    polygon.strokes = [strokeStyle];
  }

  // Set stroke weight if provided
  if (strokeWeight !== undefined) {
    polygon.strokeWeight = strokeWeight;
  }

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(polygon);
  } else {
    figma.currentPage.appendChild(polygon);
  }

  return {
    id: polygon.id,
    name: polygon.name,
    type: polygon.type,
    x: polygon.x,
    y: polygon.y,
    width: polygon.width,
    height: polygon.height,
    pointCount: polygon.pointCount,
    fills: polygon.fills,
    strokes: polygon.strokes,
    strokeWeight: polygon.strokeWeight,
    parentId: polygon.parent ? polygon.parent.id : undefined,
  };
}

async function createStar(params) {
  const {
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    points = 5,
    innerRadius = 0.5, // As a proportion of the outer radius
    name = "Star",
    parentId,
    fillColor,
    strokeColor,
    strokeWeight
  } = params || {};

  // Create the star
  const star = figma.createStar();
  star.x = x;
  star.y = y;
  star.resize(width, height);
  star.name = name;

  // Set the number of points
  if (points >= 3) {
    star.pointCount = points;
  }

  // Set the inner radius ratio
  if (innerRadius > 0 && innerRadius < 1) {
    star.innerRadius = innerRadius;
  }

  // Set fill color if provided
  if (fillColor) {
    const paintStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(fillColor.r) || 0,
        g: parseFloat(fillColor.g) || 0,
        b: parseFloat(fillColor.b) || 0,
      },
      opacity: parseFloat(fillColor.a) || 1,
    };
    star.fills = [paintStyle];
  }

  // Set stroke color and weight if provided
  if (strokeColor) {
    const strokeStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(strokeColor.r) || 0,
        g: parseFloat(strokeColor.g) || 0,
        b: parseFloat(strokeColor.b) || 0,
      },
      opacity: parseFloat(strokeColor.a) || 1,
    };
    star.strokes = [strokeStyle];
  }

  // Set stroke weight if provided
  if (strokeWeight !== undefined) {
    star.strokeWeight = strokeWeight;
  }

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(star);
  } else {
    figma.currentPage.appendChild(star);
  }

  return {
    id: star.id,
    name: star.name,
    type: star.type,
    x: star.x,
    y: star.y,
    width: star.width,
    height: star.height,
    pointCount: star.pointCount,
    innerRadius: star.innerRadius,
    fills: star.fills,
    strokes: star.strokes,
    strokeWeight: star.strokeWeight,
    parentId: star.parent ? star.parent.id : undefined,
  };
}

async function createVector(params) {
  const {
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    name = "Vector",
    parentId,
    vectorPaths = [],
    fillColor,
    strokeColor,
    strokeWeight
  } = params || {};

  // Create the vector
  const vector = figma.createVector();
  vector.x = x;
  vector.y = y;
  vector.resize(width, height);
  vector.name = name;

  // Set vector paths if provided
  if (vectorPaths && vectorPaths.length > 0) {
    vector.vectorPaths = vectorPaths.map(path => {
      return {
        windingRule: path.windingRule || "EVENODD",
        data: path.data || ""
      };
    });
  }

  // Set fill color if provided
  if (fillColor) {
    const paintStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(fillColor.r) || 0,
        g: parseFloat(fillColor.g) || 0,
        b: parseFloat(fillColor.b) || 0,
      },
      opacity: parseFloat(fillColor.a) || 1,
    };
    vector.fills = [paintStyle];
  }

  // Set stroke color and weight if provided
  if (strokeColor) {
    const strokeStyle = {
      type: "SOLID",
      color: {
        r: parseFloat(strokeColor.r) || 0,
        g: parseFloat(strokeColor.g) || 0,
        b: parseFloat(strokeColor.b) || 0,
      },
      opacity: parseFloat(strokeColor.a) || 1,
    };
    vector.strokes = [strokeStyle];
  }

  // Set stroke weight if provided
  if (strokeWeight !== undefined) {
    vector.strokeWeight = strokeWeight;
  }

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(vector);
  } else {
    figma.currentPage.appendChild(vector);
  }

  return {
    id: vector.id,
    name: vector.name,
    type: vector.type,
    x: vector.x,
    y: vector.y,
    width: vector.width,
    height: vector.height,
    vectorNetwork: vector.vectorNetwork,
    fills: vector.fills,
    strokes: vector.strokes,
    strokeWeight: vector.strokeWeight,
    parentId: vector.parent ? vector.parent.id : undefined,
  };
}

async function createLine(params) {
  const {
    x1 = 0,
    y1 = 0,
    x2 = 100,
    y2 = 0,
    name = "Line",
    parentId,
    strokeColor = { r: 0, g: 0, b: 0, a: 1 },
    strokeWeight = 1,
    strokeCap = "NONE" // Can be "NONE", "ROUND", "SQUARE", "ARROW_LINES", or "ARROW_EQUILATERAL"
  } = params || {};

  // Create a vector node to represent the line
  const line = figma.createVector();
  line.name = name;

  // Position the line at the starting point
  line.x = x1;
  line.y = y1;

  // Calculate the vector size
  const width = Math.abs(x2 - x1);
  const height = Math.abs(y2 - y1);
  line.resize(width > 0 ? width : 1, height > 0 ? height : 1);

  // Create vector path data for a straight line
  // SVG path data format: M (move to) starting point, L (line to) ending point
  const dx = x2 - x1;
  const dy = y2 - y1;

  // Calculate relative endpoint coordinates in the vector's local coordinate system
  const endX = dx > 0 ? width : 0;
  const endY = dy > 0 ? height : 0;
  const startX = dx > 0 ? 0 : width;
  const startY = dy > 0 ? 0 : height;

  // Generate SVG path data for the line
  const pathData = `M ${startX} ${startY} L ${endX} ${endY}`;

  // Set vector paths
  line.vectorPaths = [{
    windingRule: "NONZERO",
    data: pathData
  }];

  // Set stroke color
  const strokeStyle = {
    type: "SOLID",
    color: {
      r: parseFloat(strokeColor.r) || 0,
      g: parseFloat(strokeColor.g) || 0,
      b: parseFloat(strokeColor.b) || 0,
    },
    opacity: parseFloat(strokeColor.a) || 1
  };
  line.strokes = [strokeStyle];

  // Set stroke weight
  line.strokeWeight = strokeWeight;

  // Set stroke cap style if supported
  if (["NONE", "ROUND", "SQUARE", "ARROW_LINES", "ARROW_EQUILATERAL"].includes(strokeCap)) {
    line.strokeCap = strokeCap;
  }

  // Set fill to none (transparent) as lines typically don't have fills
  line.fills = [];

  // If parentId is provided, append to that node, otherwise append to current page
  if (parentId) {
    const parentNode = await figma.getNodeByIdAsync(parentId);
    if (!parentNode) {
      throw new Error(`Parent node not found with ID: ${parentId}`);
    }
    if (!("appendChild" in parentNode)) {
      throw new Error(`Parent node does not support children: ${parentId}`);
    }
    parentNode.appendChild(line);
  } else {
    figma.currentPage.appendChild(line);
  }

  return {
    id: line.id,
    name: line.name,
    type: line.type,
    x: line.x,
    y: line.y,
    width: line.width,
    height: line.height,
    strokeWeight: line.strokeWeight,
    strokeCap: line.strokeCap,
    strokes: line.strokes,
    vectorPaths: line.vectorPaths,
    parentId: line.parent ? line.parent.id : undefined
  };
}

// Rename a node (frame, component, group, etc.)
async function renameNode(params) {
  const { nodeId, name } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  if (!name) {
    throw new Error("Missing name parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  if (node.type === "DOCUMENT") {
    throw new Error("Cannot rename the document node");
  }

  const oldName = node.name;
  node.name = name;

  return {
    id: node.id,
    name: node.name,
    oldName: oldName,
    type: node.type
  };
}

// Create component from an existing node
async function createComponentFromNode(params) {
  const { nodeId, name } = params || {};

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  const node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error(`Node not found with ID: ${nodeId}`);
  }

  // Check if the node can be converted to a component
  if (node.type === "DOCUMENT" || node.type === "PAGE") {
    throw new Error(`Cannot create component from ${node.type}`);
  }

  // If already a component, return its info
  if (node.type === "COMPONENT") {
    return {
      id: node.id,
      name: node.name,
      key: node.key,
      alreadyComponent: true
    };
  }

  let component;

  // For frames, groups, and other container nodes, we can use createComponentFromNode
  if ("createComponentFromNode" in figma && (node.type === "FRAME" || node.type === "GROUP" || node.type === "INSTANCE")) {
    // Use Figma's built-in createComponentFromNode API
    component = figma.createComponentFromNode(node);
  } else {
    // For other node types, we need a different approach
    // Create a new component and copy properties from the original node
    const parent = node.parent;
    const index = parent ? parent.children.indexOf(node) : 0;

    // Create frame first if it's not a frame-like node
    if (node.type === "RECTANGLE" || node.type === "ELLIPSE" || node.type === "POLYGON" ||
      node.type === "STAR" || node.type === "VECTOR" || node.type === "TEXT" || node.type === "LINE") {
      // Create a component and add the node as a child
      component = figma.createComponent();
      component.x = node.x;
      component.y = node.y;
      component.resize(node.width, node.height);

      // Clone the node and add it to the component
      const clone = node.clone();
      clone.x = 0;
      clone.y = 0;
      component.appendChild(clone);

      // Add component to the same parent at the same position
      if (parent && "insertChild" in parent) {
        parent.insertChild(index, component);
      } else {
        figma.currentPage.appendChild(component);
      }

      // Remove the original node
      node.remove();
    } else if (node.type === "FRAME" || node.type === "GROUP") {
      // Fallback for frames/groups if createComponentFromNode is not available
      component = figma.createComponent();
      component.x = node.x;
      component.y = node.y;
      component.resize(node.width, node.height);

      // Copy children
      for (const child of [...node.children]) {
        component.appendChild(child);
      }

      // Copy visual properties if available
      if ("fills" in node && "fills" in component) {
        component.fills = node.fills;
      }
      if ("strokes" in node && "strokes" in component) {
        component.strokes = node.strokes;
      }
      if ("effects" in node && "effects" in component) {
        component.effects = node.effects;
      }
      if ("cornerRadius" in node && "cornerRadius" in component) {
        component.cornerRadius = node.cornerRadius;
      }

      // Add component to the same parent
      if (parent && "insertChild" in parent) {
        parent.insertChild(index, component);
      } else {
        figma.currentPage.appendChild(component);
      }

      // Remove the original node
      node.remove();
    } else {
      throw new Error(`Cannot create component from node type: ${node.type}`);
    }
  }

  // Set the name if provided
  if (name) {
    component.name = name;
  }

  return {
    id: component.id,
    name: component.name,
    key: component.key,
    width: component.width,
    height: component.height,
    x: component.x,
    y: component.y
  };
}

// Create component set from multiple components
async function createComponentSet(params) {
  const { componentIds, name } = params || {};

  if (!componentIds || !Array.isArray(componentIds) || componentIds.length === 0) {
    throw new Error("Missing or empty componentIds parameter");
  }

  const components = [];
  for (const id of componentIds) {
    const node = await figma.getNodeByIdAsync(id);
    if (!node) {
      throw new Error(`Node not found with ID: ${id}`);
    }
    if (node.type !== "COMPONENT") {
      throw new Error(`Node with ID ${id} is not a component (type: ${node.type})`);
    }
    components.push(node);
  }

  // Combine components into a component set
  const componentSet = figma.combineAsVariants(components, figma.currentPage);

  if (name) {
    componentSet.name = name;
  }

  return {
    id: componentSet.id,
    name: componentSet.name,
    key: componentSet.key,
    variantCount: componentSet.children.length,
    width: componentSet.width,
    height: componentSet.height
  };
}

// Create a new page
async function createPage(params) {
  const { name } = params || {};

  if (!name) {
    throw new Error("Missing name parameter");
  }

  const page = figma.createPage();
  page.name = name;

  return {
    id: page.id,
    name: page.name
  };
}

// Delete a page
async function deletePage(params) {
  const { pageId } = params || {};

  if (!pageId) {
    throw new Error("Missing pageId parameter");
  }

  // Cannot delete the only page or the current page if it's the only one
  if (figma.root.children.length <= 1) {
    throw new Error("Cannot delete the only page in the document");
  }

  const page = figma.root.children.find(p => p.id === pageId);
  if (!page) {
    throw new Error(`Page not found with ID: ${pageId}`);
  }

  const pageName = page.name;

  // If deleting current page, switch to another page first
  if (figma.currentPage.id === pageId) {
    const otherPage = figma.root.children.find(p => p.id !== pageId);
    if (otherPage) {
      await figma.setCurrentPageAsync(otherPage);
    }
  }

  page.remove();

  return {
    success: true,
    name: pageName
  };
}

// Rename a page
async function renamePage(params) {
  const { pageId, name } = params || {};

  if (!pageId) {
    throw new Error("Missing pageId parameter");
  }
  if (!name) {
    throw new Error("Missing name parameter");
  }

  const page = figma.root.children.find(p => p.id === pageId);
  if (!page) {
    throw new Error(`Page not found with ID: ${pageId}`);
  }

  const oldName = page.name;
  page.name = name;

  return {
    id: page.id,
    name: page.name,
    oldName: oldName
  };
}

// Get all pages in the document
async function getPages() {
  return {
    pages: figma.root.children.map(page => ({
      id: page.id,
      name: page.name,
      childCount: page.children.length,
      isCurrent: page.id === figma.currentPage.id
    })),
    currentPageId: figma.currentPage.id
  };
}

// Set the current page
async function setCurrentPage(params) {
  const { pageId } = params || {};

  if (!pageId) {
    throw new Error("Missing pageId parameter");
  }

  const page = figma.root.children.find(p => p.id === pageId);
  if (!page) {
    throw new Error(`Page not found with ID: ${pageId}`);
  }

  await figma.setCurrentPageAsync(page);

  return {
    id: page.id,
    name: page.name
  };
}

// Helper: extract resolved value from a variable, resolving aliases recursively (max 5 depth)
async function resolveVariableValue(variable, depth) {
  if (depth === undefined) depth = 0;
  if (depth > 5) return null;
  if (!variable || !variable.valuesByMode) return null;
  var modeIds = Object.keys(variable.valuesByMode);
  if (modeIds.length === 0) return null;
  var val = variable.valuesByMode[modeIds[0]];
  // Resolve variable alias recursively
  if (val && val.type === "VARIABLE_ALIAS") {
    try {
      var aliasVar = await figma.variables.getVariableByIdAsync(val.id);
      if (aliasVar) {
        return await resolveVariableValue(aliasVar, depth + 1);
      }
    } catch (e) {
      return { alias: val.id, error: e.message || String(e) };
    }
    return null;
  }
  // COLOR type: convert to hex
  if (variable.resolvedType === "COLOR" && val && typeof val.r === "number") {
    var rr = Math.round(val.r * 255);
    var gg = Math.round(val.g * 255);
    var bb = Math.round(val.b * 255);
    var hex = "#" + ((1 << 24) + (rr << 16) + (gg << 8) + bb).toString(16).slice(1);
    if (val.a !== undefined && val.a < 1) {
      var aa = Math.round(val.a * 255).toString(16);
      if (aa.length === 1) aa = "0" + aa;
      hex = hex + aa;
    }
    return hex;
  }
  return val;
}

// Get local variables (design tokens)
async function getLocalVariables(params) {
  var filterType = (params && params.type) ? params.type : null;
  var includeLibrary = (params && params.includeLibrary) ? true : false;
  var variables = await figma.variables.getLocalVariablesAsync(filterType || undefined);

  var localVarInfos = [];
  for (var vi = 0; vi < variables.length; vi++) {
    var v = variables[vi];
    localVarInfos.push({
      id: v.id,
      name: v.name,
      key: v.key,
      resolvedType: v.resolvedType,
      variableCollectionId: v.variableCollectionId,
      value: await resolveVariableValue(v),
      source: "local"
    });
  }

  var result = {
    count: variables.length,
    variables: localVarInfos,
    libraryCollections: []
  };

  // Optionally include library variable collections
  if (includeLibrary) {
    try {
      var collections = await figma.teamLibrary.getAvailableLibraryVariableCollectionsAsync();
      var libCollections = [];
      for (var i = 0; i < collections.length; i++) {
        var col = collections[i];
        var libVars = await figma.teamLibrary.getVariablesInLibraryCollectionAsync(col.key);

        // Import all variables in parallel to resolve values
        var importPromises = libVars.map(function(lv) {
          return figma.variables.importVariableByKeyAsync(lv.key).catch(function() { return null; });
        });
        var importedVars = await Promise.all(importPromises);

        var varsInfo = [];
        for (var j = 0; j < libVars.length; j++) {
          var entry = {
            name: libVars[j].name,
            key: libVars[j].key,
            resolvedType: libVars[j].resolvedType
          };
          if (importedVars[j]) {
            entry.value = await resolveVariableValue(importedVars[j]);
          }
          varsInfo.push(entry);
        }
        libCollections.push({
          name: col.name,
          key: col.key,
          libraryName: col.libraryName,
          variableCount: libVars.length,
          variables: varsInfo
        });
      }
      result.libraryCollections = libCollections;
    } catch (e) {
      result.libraryError = e.message || String(e);
    }
  }

  return result;
}

// Get bound variables of a node
async function getBoundVariables(params) {
  var nodeId = (params && params.nodeId) ? params.nodeId : null;
  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error("Node not found with ID: " + nodeId);
  }

  var boundVars = node.boundVariables ? node.boundVariables : {};
  var result = {};

  var fields = Object.keys(boundVars);
  for (var i = 0; i < fields.length; i++) {
    var field = fields[i];
    var binding = boundVars[field];
    if (binding) {
      // binding can be a single VariableAlias or an array
      if (Array.isArray(binding)) {
        var arr = [];
        for (var j = 0; j < binding.length; j++) {
          var varId = binding[j].id;
          var variable = await figma.variables.getVariableByIdAsync(varId);
          arr.push({
            id: varId,
            name: variable ? variable.name : "unknown"
          });
        }
        result[field] = arr;
      } else {
        var varId2 = binding.id;
        var variable2 = await figma.variables.getVariableByIdAsync(varId2);
        result[field] = {
          id: varId2,
          name: variable2 ? variable2.name : "unknown"
        };
      }
    }
  }

  return {
    id: node.id,
    name: node.name,
    type: node.type,
    boundVariables: result
  };
}

// Set bound variables on a node by variable name
async function setBoundVariables(params) {
  var nodeId = (params && params.nodeId) ? params.nodeId : null;
  var bindings = (params && params.bindings) ? params.bindings : null;

  if (!nodeId) {
    throw new Error("Missing nodeId parameter");
  }
  if (!bindings || typeof bindings !== "object") {
    throw new Error("Missing or invalid bindings parameter. Expected { field: variableName, ... }");
  }

  var node = await figma.getNodeByIdAsync(nodeId);
  if (!node) {
    throw new Error("Node not found with ID: " + nodeId);
  }

  // Step 1: Build lookup from local variables
  var allVariables = await figma.variables.getLocalVariablesAsync();
  var varByName = {};
  for (var i = 0; i < allVariables.length; i++) {
    var v = allVariables[i];
    varByName[v.name] = v;
  }

  // Step 2: Build lookup from library variables (import as needed)
  var libVarByName = {};
  try {
    var collections = await figma.teamLibrary.getAvailableLibraryVariableCollectionsAsync();
    for (var ci = 0; ci < collections.length; ci++) {
      var libVars = await figma.teamLibrary.getVariablesInLibraryCollectionAsync(collections[ci].key);
      for (var li = 0; li < libVars.length; li++) {
        libVarByName[libVars[li].name] = libVars[li];
      }
    }
  } catch (e) {
    // Library access may fail - continue with local only
  }

  var fields = Object.keys(bindings);
  var applied = [];
  var errors = [];

  for (var j = 0; j < fields.length; j++) {
    var field = fields[j];
    var varName = bindings[field];

    if (varName === null) {
      // Unbind
      try {
        // Check if field is a paint field (fills/0, strokes/0)
        var unbindPaint = field.match(/^(fills|strokes)\/(\d+)$/);
        if (unbindPaint) {
          var ubPaintField = unbindPaint[1];
          var ubPaintIdx = parseInt(unbindPaint[2], 10);
          var ubPaints = JSON.parse(JSON.stringify(node[ubPaintField]));
          if (ubPaints && ubPaints[ubPaintIdx]) {
            ubPaints[ubPaintIdx] = figma.variables.setBoundVariableForPaint(ubPaints[ubPaintIdx], "color", null);
            node[ubPaintField] = ubPaints;
          }
        } else {
          node.setBoundVariable(field, null);
        }
        applied.push({ field: field, action: "unbound" });
      } catch (e) {
        errors.push({ field: field, error: e.message || String(e) });
      }
      continue;
    }

    // Search in local variables first
    var variable = varByName[varName];
    if (!variable) {
      // Try partial match for local vars
      var localKeys = Object.keys(varByName);
      for (var k = 0; k < localKeys.length; k++) {
        if (localKeys[k].endsWith("/" + varName) || localKeys[k].endsWith("." + varName)) {
          variable = varByName[localKeys[k]];
          break;
        }
      }
    }

    // If not found locally, search in library variables and import
    if (!variable) {
      var libVar = libVarByName[varName];
      if (!libVar) {
        // Try partial match for library vars
        var libKeys = Object.keys(libVarByName);
        for (var lk = 0; lk < libKeys.length; lk++) {
          if (libKeys[lk].endsWith("/" + varName) || libKeys[lk].endsWith("." + varName)) {
            libVar = libVarByName[libKeys[lk]];
            break;
          }
        }
      }
      if (libVar) {
        try {
          variable = await figma.variables.importVariableByKeyAsync(libVar.key);
        } catch (importErr) {
          errors.push({ field: field, variableName: varName, error: "Import failed: " + (importErr.message || String(importErr)) });
          continue;
        }
      }
    }

    if (!variable) {
      errors.push({ field: field, variableName: varName, error: "Variable not found in local or library" });
      continue;
    }

    try {
      // Check if field is a paint field (fills/0, strokes/0) — must use setBoundVariableForPaint
      var paintMatch = field.match(/^(fills|strokes)\/(\d+)$/);
      if (paintMatch) {
        var paintField = paintMatch[1];
        var paintIdx = parseInt(paintMatch[2], 10);
        var paints = JSON.parse(JSON.stringify(node[paintField]));
        if (!paints || !paints[paintIdx]) {
          throw new Error("No paint at index " + paintIdx + " in " + paintField);
        }
        paints[paintIdx] = figma.variables.setBoundVariableForPaint(paints[paintIdx], "color", variable);
        node[paintField] = paints;
      } else {
        node.setBoundVariable(field, variable);
      }
      applied.push({ field: field, variableName: variable.name, variableId: variable.id });
    } catch (e) {
      errors.push({ field: field, variableName: varName, error: e.message || String(e) });
    }
  }

  return {
    id: node.id,
    name: node.name,
    applied: applied,
    errors: errors
  };
}

// Batch bind variables to multiple nodes in a single call (loads variables ONCE)
async function batchBindVariables(params) {
  var items = (params && params.items) ? params.items : null;
  if (!items || !Array.isArray(items) || items.length === 0) {
    throw new Error("Missing or empty items array parameter");
  }

  // Phase 0: Load ALL variables ONCE
  var allVariables = await figma.variables.getLocalVariablesAsync();
  var varByName = {};
  for (var i = 0; i < allVariables.length; i++) {
    varByName[allVariables[i].name] = allVariables[i];
  }

  var libVarByName = {};
  try {
    var collections = await figma.teamLibrary.getAvailableLibraryVariableCollectionsAsync();
    for (var ci = 0; ci < collections.length; ci++) {
      var libVars = await figma.teamLibrary.getVariablesInLibraryCollectionAsync(collections[ci].key);
      for (var li = 0; li < libVars.length; li++) {
        libVarByName[libVars[li].name] = libVars[li];
      }
    }
  } catch (e) {
    // Library access may fail - continue with local only
  }

  // Phase 1: Collect all unique variable names and pre-import library vars
  var neededNames = {};
  for (var ni = 0; ni < items.length; ni++) {
    var bindings = items[ni].bindings || {};
    var bFields = Object.keys(bindings);
    for (var bf = 0; bf < bFields.length; bf++) {
      var vn = bindings[bFields[bf]];
      if (vn !== null && vn !== undefined) {
        neededNames[vn] = true;
      }
    }
  }

  // Resolve all needed variables (local first, then library import)
  var resolvedVars = {};
  var nameList = Object.keys(neededNames);
  for (var ri = 0; ri < nameList.length; ri++) {
    var name = nameList[ri];
    // Search local
    var resolved = varByName[name];
    if (!resolved) {
      var localKeys = Object.keys(varByName);
      for (var lk = 0; lk < localKeys.length; lk++) {
        if (localKeys[lk].endsWith("/" + name) || localKeys[lk].endsWith("." + name)) {
          resolved = varByName[localKeys[lk]];
          break;
        }
      }
    }
    // Search library
    if (!resolved) {
      var libVar = libVarByName[name];
      if (!libVar) {
        var libKeys = Object.keys(libVarByName);
        for (var lk2 = 0; lk2 < libKeys.length; lk2++) {
          if (libKeys[lk2].endsWith("/" + name) || libKeys[lk2].endsWith("." + name)) {
            libVar = libVarByName[libKeys[lk2]];
            break;
          }
        }
      }
      if (libVar) {
        try {
          resolved = await figma.variables.importVariableByKeyAsync(libVar.key);
        } catch (importErr) {
          // Will be reported per-binding later
        }
      }
    }
    if (resolved) {
      resolvedVars[name] = resolved;
    }
  }

  // Phase 2: Apply bindings to all nodes
  var results = [];
  var allErrors = [];
  var succeeded = 0;
  var failed = 0;

  for (var ai = 0; ai < items.length; ai++) {
    var item = items[ai];
    var nodeId = item.nodeId;
    var nodeBindings = item.bindings || {};

    var node = await figma.getNodeByIdAsync(nodeId);
    if (!node) {
      allErrors.push({ nodeId: nodeId, error: "Node not found" });
      failed++;
      continue;
    }

    var nodeApplied = [];
    var nodeErrors = [];
    var fields = Object.keys(nodeBindings);

    for (var fj = 0; fj < fields.length; fj++) {
      var field = fields[fj];
      var varName = nodeBindings[field];

      // Unbind
      if (varName === null) {
        try {
          var unbindPaint = field.match(/^(fills|strokes)\/(\d+)$/);
          if (unbindPaint) {
            var ubPaintField = unbindPaint[1];
            var ubPaintIdx = parseInt(unbindPaint[2], 10);
            var ubPaints = JSON.parse(JSON.stringify(node[ubPaintField]));
            if (ubPaints && ubPaints[ubPaintIdx]) {
              ubPaints[ubPaintIdx] = figma.variables.setBoundVariableForPaint(ubPaints[ubPaintIdx], "color", null);
              node[ubPaintField] = ubPaints;
            }
          } else {
            node.setBoundVariable(field, null);
          }
          nodeApplied.push({ field: field, action: "unbound" });
        } catch (e) {
          nodeErrors.push({ field: field, error: e.message || String(e) });
        }
        continue;
      }

      var variable = resolvedVars[varName];
      if (!variable) {
        nodeErrors.push({ field: field, variableName: varName, error: "Variable not found" });
        continue;
      }

      try {
        var paintMatch = field.match(/^(fills|strokes)\/(\d+)$/);
        if (paintMatch) {
          var paintField = paintMatch[1];
          var paintIdx = parseInt(paintMatch[2], 10);
          var paints = JSON.parse(JSON.stringify(node[paintField]));
          if (!paints || !paints[paintIdx]) {
            throw new Error("No paint at index " + paintIdx + " in " + paintField);
          }
          paints[paintIdx] = figma.variables.setBoundVariableForPaint(paints[paintIdx], "color", variable);
          node[paintField] = paints;
        } else {
          node.setBoundVariable(field, variable);
        }
        nodeApplied.push({ field: field, variableName: variable.name });
      } catch (e) {
        nodeErrors.push({ field: field, variableName: varName, error: e.message || String(e) });
      }
    }

    if (nodeApplied.length > 0) {
      results.push({ nodeId: node.id, name: node.name, applied: nodeApplied.length, errors: nodeErrors.length });
      succeeded++;
    }
    if (nodeErrors.length > 0) {
      allErrors.push({ nodeId: nodeId, errors: nodeErrors });
      if (nodeApplied.length === 0) failed++;
    }
  }

  return {
    total: items.length,
    succeeded: succeeded,
    failed: failed,
    results: results,
    errors: allErrors
  };
}

// Batch set text style IDs on multiple text nodes (imports each unique style ONCE)
async function batchSetTextStyleId(params) {
  var items = (params && params.items) ? params.items : null;
  if (!items || !Array.isArray(items) || items.length === 0) {
    throw new Error("Missing or empty items array parameter");
  }

  // Phase 0: Collect unique style IDs and import/load each ONCE
  var uniqueStyleIds = {};
  for (var ui = 0; ui < items.length; ui++) {
    uniqueStyleIds[items[ui].textStyleId] = null; // placeholder
  }

  var styleKeys = Object.keys(uniqueStyleIds);
  var localStyles = null; // lazy load

  for (var si = 0; si < styleKeys.length; si++) {
    var textStyleId = styleKeys[si];
    try {
      var remoteMatch = textStyleId.match(/^S:([^,]+),(.+)$/);
      if (remoteMatch) {
        var styleKey = remoteMatch[1];
        var importedStyle = await figma.importStyleByKeyAsync(styleKey);
        if (importedStyle) {
          await loadFontWithTimeout(importedStyle.fontName);
          uniqueStyleIds[textStyleId] = importedStyle;
        }
      } else {
        // Local style lookup
        if (!localStyles) {
          localStyles = await figma.getLocalTextStylesAsync();
        }
        var found = null;
        for (var ls = 0; ls < localStyles.length; ls++) {
          if (localStyles[ls].id === textStyleId || localStyles[ls].key === textStyleId) {
            found = localStyles[ls];
            break;
          }
        }
        if (found) {
          await loadFontWithTimeout(found.fontName);
          uniqueStyleIds[textStyleId] = found;
        }
      }
    } catch (e) {
      // Style import/font failed - will be reported per-item
      console.log("Failed to import style " + textStyleId + ": " + (e.message || String(e)));
    }
  }

  // Phase 1: Apply styles to all nodes
  var results = [];
  var errors = [];
  var succeeded = 0;

  for (var ai = 0; ai < items.length; ai++) {
    var item = items[ai];
    var nodeId = item.nodeId;
    var styleId = item.textStyleId;
    var style = uniqueStyleIds[styleId];

    if (!style) {
      errors.push({ nodeId: nodeId, textStyleId: styleId, error: "Style not found or import failed" });
      continue;
    }

    try {
      var node = await figma.getNodeByIdAsync(nodeId);
      if (!node) {
        errors.push({ nodeId: nodeId, error: "Node not found" });
        continue;
      }
      if (node.type !== "TEXT") {
        errors.push({ nodeId: nodeId, error: "Not a text node (type: " + node.type + ")" });
        continue;
      }
      await node.setTextStyleIdAsync(style.id);
      results.push({ nodeId: node.id, name: node.name, styleName: style.name });
      succeeded++;
    } catch (e) {
      errors.push({ nodeId: nodeId, error: e.message || String(e) });
    }
  }

  return {
    total: items.length,
    succeeded: succeeded,
    failed: errors.length,
    results: results,
    errors: errors
  };
}

// ============================================================
// batch_build_screen — Build entire screen from blueprint tree
// ============================================================

// Collect all unique componentKeys from a blueprint tree
function collectComponentKeys(spec, keys = new Set()) {
  if (spec.componentKey) keys.add(spec.componentKey);
  if (spec.children) spec.children.forEach(child => collectComponentKeys(child, keys));
  return keys;
}

// Batch pre-import components into cache (parallel)
async function preCacheComponents(keys) {
  const uncachedKeys = [...keys].filter(k => !componentCache.has(k));
  if (uncachedKeys.length === 0) {
    console.log(`[cache] All ${keys.size} components already cached`);
    return;
  }

  console.log(`[cache] Pre-importing ${uncachedKeys.length} components (${componentCache.size} already cached)...`);
  const startTime = Date.now();

  const results = await Promise.allSettled(
    uncachedKeys.map(async (key) => {
      try {
        const comp = await figma.importComponentByKeyAsync(key);
        componentCache.set(key, comp);
        return { key, success: true };
      } catch (e) {
        console.warn(`[cache] Import failed for ${key}: ${e.message}`);
        return { key, success: false };
      }
    })
  );

  const succeeded = results.filter(r => r.status === "fulfilled" && r.value.success).length;
  const elapsed = Date.now() - startTime;
  console.log(`[cache] Pre-cached ${succeeded}/${uncachedKeys.length} in ${elapsed}ms (total cache: ${componentCache.size})`);
}

// ★ Clear component cache (called on app restart to pick up DS updates)
function clearComponentCache() {
  const count = componentCache.size;
  componentCache.clear();
  console.log(`[cache] Cleared ${count} cached components`);
  return { success: true, cleared: count };
}

// ★ Pre-cache DS components — sequential to avoid Figma API overload
async function preCacheAllComponents(params) {
  const { keys } = params || {};
  if (!Array.isArray(keys) || keys.length === 0) {
    return { success: true, cached: componentCache.size, message: "No keys provided" };
  }

  const uncachedKeys = keys.filter(k => !componentCache.has(k));
  if (uncachedKeys.length === 0) {
    return { success: true, cached: componentCache.size, newlyCached: 0, failed: 0, skipped: keys.length, failedKeys: [], elapsed: 0, message: "All already cached" };
  }

  console.log(`[pre_cache] Importing ${uncachedKeys.length} components (${keys.length - uncachedKeys.length} already cached)...`);
  const startTime = Date.now();
  let succeeded = 0;
  const failedKeys = [];

  // Sequential import — Figma API doesn't handle massive parallel well
  for (let i = 0; i < uncachedKeys.length; i++) {
    try {
      const comp = await figma.importComponentByKeyAsync(uncachedKeys[i]);
      componentCache.set(uncachedKeys[i], comp);
      succeeded++;
    } catch (e) {
      failedKeys.push(uncachedKeys[i]);
    }
    // Progress log every 50
    if ((i + 1) % 50 === 0) {
      console.log(`[pre_cache] Progress: ${i + 1}/${uncachedKeys.length} (${succeeded} OK, ${failedKeys.length} fail)`);
    }
  }

  const elapsed = Date.now() - startTime;
  console.log(`[pre_cache] Done: ${succeeded} cached, ${failedKeys.length} failed in ${elapsed}ms (total: ${componentCache.size})`);

  return {
    success: true,
    cached: componentCache.size,
    newlyCached: succeeded,
    failed: failedKeys.length,
    failedKeys,
    elapsed,
    message: `Pre-cached ${succeeded} components in ${elapsed}ms`,
  };
}

async function batchBuildScreen(params) {
  const { blueprint, commandId, parentId } = params || {};
  if (!blueprint) throw new Error("Missing blueprint parameter");

  const nodeMap = {}; // name → figma node id
  let totalNodes = 0;
  let processedNodes = 0;

  // Count total nodes for progress
  function countNodes(node) {
    totalNodes++;
    if (node.children) node.children.forEach(countNodes);
  }
  countNodes(blueprint);

  // ★ Pre-cache: batch-import all needed components before building
  const neededKeys = collectComponentKeys(blueprint);
  if (neededKeys.size > 0) {
    await preCacheComponents(neededKeys);
  }

  // Map common font weights to Figma font styles
  function getFontStyle(weight) {
    switch (weight) {
      case 100: return "Thin";
      case 200: return "ExtraLight";
      case 300: return "Light";
      case 400: return "Regular";
      case 500: return "Medium";
      case 600: return "SemiBold";
      case 700: return "Bold";
      case 800: return "ExtraBold";
      case 900: return "Black";
      default: return "Regular";
    }
  }
  // Alternative style names (some fonts use spaces, others don't)
  var FONT_STYLE_ALTS = {
    "SemiBold": "Semi Bold", "Semi Bold": "SemiBold",
    "ExtraLight": "Extra Light", "Extra Light": "ExtraLight",
    "ExtraBold": "Extra Bold", "Extra Bold": "ExtraBold",
  };

  // Preload fonts used in the blueprint
  const fontsToLoad = new Set();
  function collectFonts(node) {
    if (node.type === "text" || (!node.type && node.text)) {
      var family = node.fontFamily || "Pretendard";
      var style = "Regular";
      if (node.fontName && typeof node.fontName === "object") {
        if (node.fontName.family) family = node.fontName.family;
        if (node.fontName.style) style = node.fontName.style;
      } else {
        var weight = node.fontWeight || 400;
        style = getFontStyle(weight);
      }
      fontsToLoad.add(JSON.stringify({ family, style: style }));
    }
    if (node.children) node.children.forEach(collectFonts);
  }
  collectFonts(blueprint);

  // Load all fonts in parallel
  const fontPromises = [];
  for (const fontStr of fontsToLoad) {
    const font = JSON.parse(fontStr);
    fontPromises.push(
      loadFontWithTimeout(font).catch(err => {
        // Try alternative style name (SemiBold vs Semi Bold, etc.)
        var alt = FONT_STYLE_ALTS[font.style];
        if (alt) {
          return loadFontWithTimeout({ family: font.family, style: alt }).catch(err2 => {
            console.warn(`Font load failed: ${font.family} ${font.style}/${alt}`, err2);
            return loadFontWithTimeout({ family: "Inter", style: "Regular" });
          });
        }
        console.warn(`Font load failed: ${font.family} ${font.style}`, err);
        return loadFontWithTimeout({ family: "Inter", style: "Regular" });
      })
    );
  }
  await Promise.all(fontPromises);

  // Recursively build nodes
  async function buildNode(spec, parentNode) {
    const nodeType = spec.type || "frame";
    let node;

    if (nodeType === "frame" || nodeType === "component") {
      node = figma.createFrame();
      node.resize(spec.width || 100, spec.height || 100);

      // Fill color
      if (spec.fill) {
        node.fills = [{
          type: "SOLID",
          color: {
            r: parseFloat(spec.fill.r) || 0,
            g: parseFloat(spec.fill.g) || 0,
            b: parseFloat(spec.fill.b) || 0,
          },
          opacity: spec.fill.a !== undefined ? parseFloat(spec.fill.a) : 1,
        }];
      } else if (!spec.imageFill) {
        // Clear default white fill on container frames (no explicit fill, no image)
        node.fills = [];
      }

      // Stroke
      if (spec.stroke) {
        node.strokes = [{
          type: "SOLID",
          color: {
            r: parseFloat(spec.stroke.r) || 0,
            g: parseFloat(spec.stroke.g) || 0,
            b: parseFloat(spec.stroke.b) || 0,
          },
          opacity: spec.stroke.a !== undefined ? parseFloat(spec.stroke.a) : 1,
        }];
        if (spec.strokeWeight !== undefined) node.strokeWeight = spec.strokeWeight;
        if (spec.strokeAlign) node.strokeAlign = spec.strokeAlign;
        // Individual stroke weights (bottom-only border 등)
        var hasIndividualStroke = spec.strokeTopWeight !== undefined || spec.strokeBottomWeight !== undefined || spec.strokeLeftWeight !== undefined || spec.strokeRightWeight !== undefined;
        if (hasIndividualStroke && "strokeTopWeight" in node) {
          var defaultSW = spec.strokeWeight !== undefined ? spec.strokeWeight : 1;
          node.strokeTopWeight = spec.strokeTopWeight !== undefined ? parseFloat(spec.strokeTopWeight) : defaultSW;
          node.strokeBottomWeight = spec.strokeBottomWeight !== undefined ? parseFloat(spec.strokeBottomWeight) : defaultSW;
          node.strokeLeftWeight = spec.strokeLeftWeight !== undefined ? parseFloat(spec.strokeLeftWeight) : defaultSW;
          node.strokeRightWeight = spec.strokeRightWeight !== undefined ? parseFloat(spec.strokeRightWeight) : defaultSW;
        }
      } else {
        // Clear default strokes (same pattern as fill clearing above)
        node.strokes = [];
      }

      // Corner radius
      if (spec.cornerRadius !== undefined) {
        node.cornerRadius = spec.cornerRadius;
      }
      if (spec.topLeftRadius !== undefined) node.topLeftRadius = spec.topLeftRadius;
      if (spec.topRightRadius !== undefined) node.topRightRadius = spec.topRightRadius;
      if (spec.bottomLeftRadius !== undefined) node.bottomLeftRadius = spec.bottomLeftRadius;
      if (spec.bottomRightRadius !== undefined) node.bottomRightRadius = spec.bottomRightRadius;

      // Auto Layout
      if (spec.autoLayout) {
        const al = spec.autoLayout;
        node.layoutMode = al.layoutMode || al.direction || "VERTICAL";
        if (al.itemSpacing !== undefined) node.itemSpacing = al.itemSpacing;
        if (al.paddingTop !== undefined) node.paddingTop = al.paddingTop;
        if (al.paddingBottom !== undefined) node.paddingBottom = al.paddingBottom;
        if (al.paddingLeft !== undefined) node.paddingLeft = al.paddingLeft;
        if (al.paddingRight !== undefined) node.paddingRight = al.paddingRight;
        // Shorthand padding (number or object {top, bottom, left, right})
        if (al.padding !== undefined) {
          if (typeof al.padding === 'object' && al.padding !== null) {
            if (al.padding.top !== undefined) node.paddingTop = al.padding.top;
            if (al.padding.bottom !== undefined) node.paddingBottom = al.padding.bottom;
            if (al.padding.left !== undefined) node.paddingLeft = al.padding.left;
            if (al.padding.right !== undefined) node.paddingRight = al.padding.right;
          } else {
            node.paddingTop = al.padding;
            node.paddingBottom = al.padding;
            node.paddingLeft = al.padding;
            node.paddingRight = al.padding;
          }
        }
        if (al.paddingHorizontal !== undefined) {
          node.paddingLeft = al.paddingHorizontal;
          node.paddingRight = al.paddingHorizontal;
        }
        if (al.paddingVertical !== undefined) {
          node.paddingTop = al.paddingVertical;
          node.paddingBottom = al.paddingVertical;
        }
        // Validate alignment values before assignment (prevent Figma API errors)
        const validPrimary = ["MIN", "CENTER", "MAX", "SPACE_BETWEEN"];
        const validCounter = ["MIN", "CENTER", "MAX", "BASELINE"];
        if (al.primaryAxisAlignItems) {
          const v = String(al.primaryAxisAlignItems).toUpperCase().replace(/-/g, "_");
          node.primaryAxisAlignItems = validPrimary.includes(v) ? v : "MIN";
        }
        if (al.counterAxisAlignItems) {
          const v = String(al.counterAxisAlignItems).toUpperCase().replace(/-/g, "_");
          node.counterAxisAlignItems = validCounter.includes(v) ? v : "MIN";
        }
        if (al.layoutWrap) node.layoutWrap = al.layoutWrap;
      }

      // Layout sizing — DEFERRED until after appendChild (FILL requires auto-layout parent)
      // See "Apply deferred layoutSizing" block below

      // Clip content
      if (spec.clipsContent !== undefined) node.clipsContent = spec.clipsContent;

      // Effects
      if (spec.effects && Array.isArray(spec.effects)) {
        node.effects = spec.effects;
      }

      // Opacity
      if (spec.opacity !== undefined) node.opacity = spec.opacity;

    } else if (nodeType === "text") {
      node = figma.createText();
      // Support both fontName: {family, style} and fontFamily + fontWeight
      var family = spec.fontFamily || "Pretendard";
      var styleName = "Regular";
      if (spec.fontName && typeof spec.fontName === "object") {
        if (spec.fontName.family) family = spec.fontName.family;
        if (spec.fontName.style) styleName = spec.fontName.style;
      } else {
        var weight = spec.fontWeight || 400;
        styleName = getFontStyle(weight);
      }
      try {
        node.fontName = { family, style: styleName };
        if (spec.fontSize) node.fontSize = parseInt(spec.fontSize);
      } catch (e) {
        // Try alternative style name (SemiBold vs Semi Bold, etc.)
        var altStyle = FONT_STYLE_ALTS[styleName];
        var fontSet = false;
        if (altStyle) {
          try {
            node.fontName = { family, style: altStyle };
            if (spec.fontSize) node.fontSize = parseInt(spec.fontSize);
            fontSet = true;
          } catch (e2) { /* alt also failed */ }
        }
        if (!fontSet) {
          try {
            node.fontName = { family: "Inter", style: "Regular" };
            if (spec.fontSize) node.fontSize = parseInt(spec.fontSize);
          } catch (e3) { /* ignore */ }
        }
      }

      // Convert <br> to soft line break (U+2028) for Figma text
      var rawText = spec.text || spec.characters || "";
      var processedText = rawText.replace(/<br\s*\/?>/gi, "\u2028");
      setCharacters(node, processedText);

      // Text color
      if (spec.fontColor || spec.fill) {
        const c = spec.fontColor || spec.fill;
        node.fills = [{
          type: "SOLID",
          color: { r: parseFloat(c.r) || 0, g: parseFloat(c.g) || 0, b: parseFloat(c.b) || 0 },
          opacity: c.a !== undefined ? parseFloat(c.a) : 1,
        }];
      }

      // Text alignment
      if (spec.textAlignHorizontal) node.textAlignHorizontal = spec.textAlignHorizontal;
      if (spec.textAlignVertical) node.textAlignVertical = spec.textAlignVertical;

      // Text auto resize — default to WIDTH_AND_HEIGHT so text doesn't wrap vertically
      node.textAutoResize = spec.textAutoResize || "WIDTH_AND_HEIGHT";

      // Line height
      if (spec.lineHeight !== undefined) {
        if (typeof spec.lineHeight === "number") {
          node.lineHeight = { value: spec.lineHeight, unit: "PIXELS" };
        }
      }

      // Letter spacing
      if (spec.letterSpacing !== undefined) {
        node.letterSpacing = { value: spec.letterSpacing, unit: "PIXELS" };
      }

      // Layout sizing — DEFERRED until after appendChild

    } else if (nodeType === "rectangle") {
      node = figma.createRectangle();
      node.resize(spec.width || 100, spec.height || 100);

      if (spec.fill) {
        node.fills = [{
          type: "SOLID",
          color: { r: parseFloat(spec.fill.r) || 0, g: parseFloat(spec.fill.g) || 0, b: parseFloat(spec.fill.b) || 0 },
          opacity: spec.fill.a !== undefined ? parseFloat(spec.fill.a) : 1,
        }];
      }
      if (spec.cornerRadius !== undefined) node.cornerRadius = spec.cornerRadius;
      // Layout sizing — DEFERRED until after appendChild

    } else if (nodeType === "ellipse") {
      node = figma.createEllipse();
      node.resize(spec.width || 100, spec.height || 100);
      if (spec.fill) {
        node.fills = [{
          type: "SOLID",
          color: { r: parseFloat(spec.fill.r) || 0, g: parseFloat(spec.fill.g) || 0, b: parseFloat(spec.fill.b) || 0 },
          opacity: spec.fill.a !== undefined ? parseFloat(spec.fill.a) : 1,
        }];
      }

    } else if (nodeType === "instance" && spec.componentKey) {
      let component = null;
      try {
        // ★ Use pre-cached component (O(1) lookup, pre-imported at build start)
        component = await getCachedComponent(spec.componentKey);
        if (!component) throw new Error(`Component not found in cache or import: ${spec.componentKey}`);

        node = component.createInstance();
        if (spec.width && spec.height) node.resize(spec.width, spec.height);

        // Apply textOverrides if provided
        if (spec.textOverrides && typeof spec.textOverrides === "object") {
          for (const [suffix, text] of Object.entries(spec.textOverrides)) {
            try {
              const fullId = `I${node.id};${suffix}`;
              const textNode = figma.getNodeById(fullId);
              if (textNode && textNode.type === "TEXT") {
                await figma.loadFontAsync(textNode.fontName);
                textNode.characters = String(text).replace(/<br\s*\/?>/gi, "\u2028");
              }
            } catch (te) {
              console.warn(`[batch_build] textOverride failed for ${suffix}: ${te.message}`);
            }
          }
        }
        // ★ Auto-text: set primary text if spec.text provided
        if (spec.text && node && node.type === "INSTANCE") {
          try {
            const textNodes = node.findAll(n => n.type === "TEXT");
            if (textNodes.length > 0) {
              // Sort by area (largest first) — primary label is usually the biggest
              textNodes.sort((a, b) => (b.width * b.height) - (a.width * a.height));
              const primaryText = textNodes[0];
              await figma.loadFontAsync(primaryText.fontName);
              primaryText.characters = String(spec.text).replace(/<br\s*\/?>/gi, "\u2028");
            }
          } catch (textErr) {
            console.warn(`[batch_build] Auto-text failed for ${spec.name}: ${textErr.message}`);
          }
        }
      } catch (e) {
        console.error(`[batch_build] Instance creation FAILED for key=${spec.componentKey}: ${e.message}`);
        // Fallback: visible error frame so it's obvious
        node = figma.createFrame();
        node.resize(spec.width || 200, spec.height || 48);
        node.name = (spec.name || "instance") + " [IMPORT FAILED]";
        node.fills = [{ type: "SOLID", color: { r: 1, g: 0.9, b: 0.9 }, opacity: 1 }];
        // Add error text inside
        try {
          const errText = figma.createText();
          await figma.loadFontAsync({ family: "Inter", style: "Regular" });
          errText.characters = `⚠ ${spec.name || spec.componentKey}`;
          errText.fontSize = 12;
          errText.fills = [{ type: "SOLID", color: { r: 0.8, g: 0, b: 0 }, opacity: 1 }];
          node.appendChild(errText);
        } catch (_) {}
      }

      // Layout sizing — DEFERRED until after appendChild

    } else if (nodeType === "svg_icon" && spec.svgData) {
      // Create vector node from SVG string (Untitled UI icons from GitHub)
      try {
        node = figma.createNodeFromSvg(spec.svgData);
        node.name = spec.name || spec.ds1Name || "icon";
        var iconW = spec.width || 24;
        var iconH = spec.height || 24;
        node.resize(iconW, iconH);
        // Apply icon color by changing all vector children's fills/strokes
        if (spec.iconColor) {
          var color = { r: spec.iconColor.r || 0, g: spec.iconColor.g || 0, b: spec.iconColor.b || 0 };
          var opacity = spec.iconColor.a !== undefined ? spec.iconColor.a : 1;
          function colorizeVectors(n) {
            if (n.type === "VECTOR" || n.type === "LINE" || n.type === "STAR" || n.type === "POLYGON" || n.type === "ELLIPSE" || n.type === "RECTANGLE" || n.type === "BOOLEAN_OPERATION") {
              try {
                // Untitled UI SVGs use stroke, not fill
                if (n.strokes && n.strokes.length > 0) {
                  n.strokes = [{ type: "SOLID", color: color, opacity: opacity }];
                }
                if (n.fills && n.fills.length > 0) {
                  n.fills = [{ type: "SOLID", color: color, opacity: opacity }];
                }
              } catch (e) {}
            }
            if (n.children) {
              for (var i = 0; i < n.children.length; i++) {
                colorizeVectors(n.children[i]);
              }
            }
          }
          colorizeVectors(node);
        }
      } catch (e) {
        console.error("[batch_build] SVG icon FAILED:", e.message);
        node = figma.createFrame();
        node.resize(spec.width || 24, spec.height || 24);
        node.name = (spec.name || "icon") + " [SVG FAILED]";
        node.fills = [{ type: "SOLID", color: { r: 1, g: 0.9, b: 0.9 }, opacity: 1 }];
      }

    } else if (nodeType === "clone" && spec.sourceNodeId) {
      // Clone an existing node by ID (e.g. Status Bar, icons from icons page)
      try {
        const sourceNode = await figma.getNodeByIdAsync(spec.sourceNodeId);
        if (!sourceNode) throw new Error(`Source node not found: ${spec.sourceNodeId}`);
        // If source is a Component, create an instance instead of cloning
        // (cloning a Component produces another master component, not an instance)
        if (sourceNode.type === "COMPONENT") {
          node = sourceNode.createInstance();
        } else {
          node = sourceNode.clone();
        }
        if (spec.width && spec.height) node.resize(spec.width, spec.height);
      } catch (e) {
        console.error(`[batch_build] Clone FAILED for sourceNodeId=${spec.sourceNodeId}: ${e.message}`);
        node = figma.createFrame();
        node.resize(spec.width || 393, spec.height || 54);
        node.name = (spec.name || "clone") + " [CLONE FAILED]";
        node.fills = [{ type: "SOLID", color: { r: 1, g: 0.9, b: 0.9 }, opacity: 1 }];
      }
      // Layout sizing — DEFERRED until after appendChild

    } else {
      // Default: frame
      node = figma.createFrame();
      node.resize(spec.width || 100, spec.height || 100);
    }

    // Common properties
    if (spec.name) node.name = spec.name;
    if (spec.x !== undefined) node.x = spec.x;
    if (spec.y !== undefined) node.y = spec.y;
    if (spec.visible === false) node.visible = false;

    // Append to parent FIRST (layoutSizing requires being in an auto-layout parent)
    if (parentNode) {
      parentNode.appendChild(node);
      // Ensure cloned/instanced nodes participate in auto-layout (not float as absolute)
      if ((nodeType === "clone" || nodeType === "icon" || nodeType === "svg_icon") && parentNode.layoutMode && parentNode.layoutMode !== "NONE") {
        try { node.layoutPositioning = "AUTO"; } catch (e) { /* ignore */ }
        try { node.x = 0; node.y = 0; } catch (e) { /* ignore */ }
        try { node.constraints = { horizontal: "STRETCH", vertical: "MIN" }; } catch (e) { /* ignore */ }
      }
    } else {
      figma.currentPage.appendChild(node);
    }

    // Apply deferred layoutSizing AFTER appendChild
    // FILL/HUG only works on children of auto-layout frames
    try {
      var hSizing = spec.layoutSizingHorizontal || (spec.layoutSizing && spec.layoutSizing.horizontal);
      var vSizing = spec.layoutSizingVertical || (spec.layoutSizing && spec.layoutSizing.vertical);

      // Auto-apply HUG/FIXED for auto-layout frames based on explicit dimensions
      // Without this, frames default to 100x100 FIXED which breaks layout
      if ((nodeType === "frame" || nodeType === "component") && spec.autoLayout) {
        if (!hSizing && !spec.layoutSizingHorizontal) {
          hSizing = spec.width ? "FIXED" : "HUG";
        }
        if (!vSizing && !spec.layoutSizingVertical) {
          vSizing = spec.height ? "FIXED" : "HUG";
        }
      }

      // ★ Auto-apply FILL on cross-axis for children of auto-layout parents
      // Mimics CSS flexbox align-items:stretch — the most common mobile layout pattern
      // In Pencil reference: ALL children of VERTICAL parents have layoutSizingHorizontal: "FILL"
      if (parentNode && parentNode.layoutMode === "VERTICAL" && !spec.layoutSizingHorizontal) {
        if (nodeType === "frame" || nodeType === "component" || nodeType === "instance" || nodeType === "rectangle" || nodeType === "clone") {
          hSizing = "FILL";
        }
      }

      // ★ Auto-apply HUG on main-axis for auto-layout children of VERTICAL parents
      // Sections in VERTICAL parents should HUG content height, NOT be FIXED at blueprint height
      // The LLM often copies root height (852) to sections, causing massive empty space
      // Pencil reference: ALL sections use FILL×HUG pattern (never FIXED height)
      // Exception 1: if layoutSizingVertical is explicitly set in the blueprint, that takes priority
      // Exception 2: if height is explicitly set (e.g. CTA Button height:52), respect FIXED
      //   — height-copying issue should be fixed in blueprints, not by silent override
      if (parentNode && parentNode.layoutMode === "VERTICAL" && !spec.layoutSizingVertical && !spec.height) {
        if ((nodeType === "frame" || nodeType === "component") && spec.autoLayout) {
          vSizing = "HUG";
        }
      }

      // Auto-apply FILL to text nodes ONLY in VERTICAL auto-layout parents
      // VERTICAL parents: text fills parent width (standard cross-axis stretch)
      // HORIZONTAL parents: MUST NOT use FILL — multiple FILL texts compete for width
      //   causing each text to shrink to 1-character width → vertical line-break bug
      if (nodeType === "text" && !hSizing && parentNode && parentNode.layoutMode === "VERTICAL") {
        hSizing = "FILL";
      }

      // For text nodes with FILL: must set textAutoResize AFTER layoutSizing
      // so Figma knows the width is determined by layout, not text content
      if (nodeType === "text" && hSizing === "FILL") {
        // First give the text node a wide enough width to avoid character-per-line wrapping
        node.resize(parentNode ? parentNode.width : 393, node.height);
        // Set FILL first
        node.layoutSizingHorizontal = hSizing;
        // Then force textAutoResize to HEIGHT (width from parent, height auto)
        node.textAutoResize = "HEIGHT";
      } else {
        if (hSizing) {
          node.layoutSizingHorizontal = hSizing;
          // Safety: when FILL is applied, also set node width to parent's inner width
          // This ensures width is correct even if parent auto-layout is later removed
          if (hSizing === "FILL" && parentNode && parentNode.layoutMode && parentNode.layoutMode !== "NONE") {
            try {
              var pPadL = parentNode.paddingLeft || 0;
              var pPadR = parentNode.paddingRight || 0;
              var innerW = parentNode.width - pPadL - pPadR;
              if (innerW > 0 && nodeType !== "text") {
                node.resize(innerW, node.height);
              }
            } catch (e) { /* ignore resize errors */ }
          }
        }
      }
      if (vSizing) node.layoutSizingVertical = vSizing;
    } catch (lsErr) {
      // Silently ignore if parent is not auto-layout (FILL not applicable)
      console.warn(`[batch_build] layoutSizing skipped for ${spec.name || nodeType}: ${lsErr.message}`);
    }

    // Track in nodeMap
    if (spec.name) nodeMap[spec.name] = node.id;

    // Progress update
    processedNodes++;
    if (commandId && processedNodes % 5 === 0) {
      sendProgressUpdate(
        commandId, "batch_build_screen", "in_progress",
        Math.round((processedNodes / totalNodes) * 100),
        totalNodes, processedNodes,
        `Building: ${spec.name || nodeType} (${processedNodes}/${totalNodes})`
      );
    }

    // Recursively build children
    if (spec.children && Array.isArray(spec.children) && "appendChild" in node) {
      for (const childSpec of spec.children) {
        await buildNode(childSpec, node);
      }
    }

    return node;
  }

  // ★ parentId support: build section as child of existing parent frame
  let rootNode;
  if (parentId) {
    var existingParent = await figma.getNodeByIdAsync(parentId);
    if (!existingParent) throw new Error("parentId node not found: " + parentId);
    if (!("appendChild" in existingParent)) throw new Error("parentId node cannot have children: " + parentId);

    // Build the entire blueprint (section frame + children) as a child of the existing parent
    // This preserves the section's autoLayout, padding, spacing, etc.
    var sectionNode = await buildNode(blueprint, existingParent);
    rootNode = existingParent;
    console.log("[batch_build] Section build: appended section \"" + (blueprint.name || "unnamed") + "\" (id=" + sectionNode.id + ") to parent " + parentId);
  } else {
    // Full build: create new root frame
    rootNode = await buildNode(blueprint, null);
  }

  // ★ FORCED Status Bar — 모바일 루트 프레임이면 무조건 삽입 (parentId 없는 최초 빌드만)
  var isMobileRoot = rootNode.width >= 360 && rootNode.width <= 430 && rootNode.height >= 700;
  var isFullBuild = !parentId;
  var alreadyHasStatusBar = false;
  if (rootNode.children) {
    for (var si = 0; si < rootNode.children.length; si++) {
      var childName = rootNode.children[si].name || "";
      if (childName.toLowerCase().indexOf("status bar") >= 0) { alreadyHasStatusBar = true; break; }
    }
  }

  console.log("[batch_build] Status Bar check: isMobileRoot=" + isMobileRoot + " isFullBuild=" + isFullBuild + " alreadyHas=" + alreadyHasStatusBar + " layoutMode=" + rootNode.layoutMode + " w=" + rootNode.width + " h=" + rootNode.height);

  if (isMobileRoot && isFullBuild && !alreadyHasStatusBar) {
    try {
      // Find Status Bar component by name across ALL pages (load each page first)
      var statusBarSource = null;
      for (var pi = 0; pi < figma.root.children.length; pi++) {
        var page = figma.root.children[pi];
        try { await page.loadAsync(); } catch (e) { /* ignore load error */ }
        var found = page.findOne(function(n) {
          var nm = (n.name || "").toLowerCase();
          return (nm === "status bar" || nm === "statusbar" || nm === "status_bar") &&
            (n.type === "COMPONENT" || n.type === "INSTANCE" || n.type === "FRAME");
        });
        if (found) {
          statusBarSource = found;
          console.log("[batch_build] Found Status Bar source on page '" + page.name + "': id=" + found.id + " type=" + found.type + " name=" + found.name);
          break;
        }
      }
      if (statusBarSource) {
        var sbNode;
        if (statusBarSource.type === "COMPONENT") {
          sbNode = statusBarSource.createInstance();
        } else {
          sbNode = statusBarSource.clone();
        }
        sbNode.name = "Status Bar";

        // Force position to origin BEFORE insertion
        try { sbNode.x = 0; sbNode.y = 0; } catch (e) { /* ignore */ }

        // Insert as first child (top of auto-layout)
        if (rootNode.children && rootNode.children.length > 0) {
          rootNode.insertChild(0, sbNode);
        } else {
          rootNode.appendChild(sbNode);
        }

        // Force auto-layout participation
        try { sbNode.layoutPositioning = "AUTO"; } catch (e) { console.warn("[batch_build] SB layoutPositioning failed:", e.message); }
        try { sbNode.layoutSizingHorizontal = "FILL"; } catch (e) { console.warn("[batch_build] SB layoutSizingH failed:", e.message); }
        try { sbNode.layoutSizingVertical = "HUG"; } catch (e) { /* ignore */ }

        // Force position after insertion
        try { sbNode.x = 0; sbNode.y = 0; } catch (e) { /* ignore */ }

        // Reset constraints to prevent absolute positioning
        try {
          sbNode.constraints = { horizontal: "STRETCH", vertical: "MIN" };
        } catch (e) { /* ignore */ }

        console.log("[batch_build] FORCED Status Bar INSERTED: layoutPositioning=" + sbNode.layoutPositioning + " x=" + sbNode.x + " y=" + sbNode.y + " w=" + sbNode.width + " h=" + sbNode.height);

        nodeMap["Status Bar"] = sbNode.id;
        totalNodes++;
      } else {
        console.warn("[batch_build] FORCED Status Bar FAILED: no 'Status Bar' component/instance/frame found in ANY page. Pages searched: " + figma.root.children.length);
      }
    } catch (e) {
      console.warn("[batch_build] FORCED Status Bar insert EXCEPTION: " + e.message);
    }
  }

  // Final progress
  if (commandId) {
    sendProgressUpdate(
      commandId, "batch_build_screen", "completed",
      100, totalNodes, totalNodes,
      `Screen built: ${totalNodes} nodes`
    );
  }

  return {
    rootId: rootNode.id,
    rootName: rootNode.name,
    totalNodes,
    nodeMap,
  };
}

// ============================================================
// batch_execute — Execute multiple commands sequentially
// ============================================================

async function batchExecute(params) {
  const { operations, commandId } = params || {};
  if (!operations || !Array.isArray(operations)) {
    throw new Error("Missing operations array");
  }

  const refMap = {};
  const results = [];

  for (let i = 0; i < operations.length; i++) {
    const op = operations[i];
    try {
      // Resolve $ref references in params
      const resolvedParams = Object.assign({}, op.params);
      for (const [key, value] of Object.entries(resolvedParams)) {
        if (typeof value === "string" && value.startsWith("$") && refMap[value]) {
          resolvedParams[key] = refMap[value];
        }
      }
      if (op.parentRef && refMap[op.parentRef]) {
        resolvedParams.parentId = refMap[op.parentRef];
      }

      const result = await handleCommand(op.op, resolvedParams);

      // Extract ID for ref tracking
      if (op.id && result && result.id) {
        refMap[op.id] = result.id;
      }

      results.push({ op: op.op, success: true, id: op.id, figmaId: result && result.id ? result.id : undefined });
    } catch (error) {
      results.push({
        op: op.op, success: false,
        error: error.message || String(error),
      });
    }

    // Progress
    if (commandId && i % 3 === 0) {
      sendProgressUpdate(
        commandId, "batch_execute", "in_progress",
        Math.round(((i + 1) / operations.length) * 100),
        operations.length, i + 1,
        `Executing: ${op.op} (${i + 1}/${operations.length})`
      );
    }
  }

  return { results, refMap };
}
