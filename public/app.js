/**
 * Persistent Priority Queue - Interactive Dashboard Controller
 */

// State tracking
let currentState = null;
let currentView = 'tree'; // 'tree' or 'array'

// DOM Elements
const serverStatusBadge = document.getElementById('statusText');
const queueSizeVal = document.getElementById('queueSizeVal');
const emptyBadge = document.getElementById('emptyBadge');
const peekMinVal = document.getElementById('peekMinVal');
const peekMinMeta = document.getElementById('peekMinMeta');
const peekMaxVal = document.getElementById('peekMaxVal');
const peekMaxMeta = document.getElementById('peekMaxMeta');
const walCountVal = document.getElementById('walCountVal');
const snapshotMeta = document.getElementById('snapshotMeta');
const btnExtractMin = document.getElementById('btnExtractMin');
const btnExtractMax = document.getElementById('btnExtractMax');

const treeViewport = document.getElementById('treeViewport');
const treeSvg = document.getElementById('treeSvg');
const treeNodesContainer = document.getElementById('treeNodesContainer');
const emptyTreePlaceholder = document.getElementById('emptyTreePlaceholder');

const arrayViewport = document.getElementById('arrayViewport');
const arrayStrip = document.getElementById('arrayStrip');
const posmapGrid = document.getElementById('posmapGrid');

const walLogStream = document.getElementById('walLogStream');
const walFilePath = document.getElementById('walFilePath');

const updateItemSelect = document.getElementById('updateItemSelect');
const deleteItemSelect = document.getElementById('deleteItemSelect');

// Toast notifications
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Fetch live state from backend
async function fetchState() {
  try {
    const res = await fetch('/api/state');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const state = await res.json();
    currentState = state;
    renderDashboard(state);
  } catch (err) {
    console.error('Failed to fetch queue state:', err);
    if (serverStatusBadge) {
      serverStatusBadge.textContent = 'Disconnected from Server';
      serverStatusBadge.parentElement.querySelector('.status-dot').classList.remove('online');
    }
  }
}

// Main Render Method
function renderDashboard(state) {
  if (!state) return;

  // Header & Stats
  queueSizeVal.textContent = state.size;
  emptyBadge.textContent = state.is_empty ? 'Empty' : `${state.size} Items`;
  emptyBadge.className = `badge ${state.is_empty ? '' : 'badge-success'}`;

  // Peek Min
  if (state.peek_min) {
    peekMinVal.textContent = state.peek_min.item_id;
    peekMinMeta.textContent = `Priority: ${state.peek_min.priority.toFixed(2)} | Seq: #${state.peek_min.seq}`;
    btnExtractMin.disabled = false;
  } else {
    peekMinVal.textContent = 'None';
    peekMinMeta.textContent = 'Priority: - | Seq: -';
    btnExtractMin.disabled = true;
  }

  // Peek Max
  if (state.peek_max) {
    peekMaxVal.textContent = state.peek_max.item_id;
    peekMaxMeta.textContent = `Priority: ${state.peek_max.priority.toFixed(2)} | Seq: #${state.peek_max.seq}`;
    btnExtractMax.disabled = false;
  } else {
    peekMaxVal.textContent = 'None';
    peekMaxMeta.textContent = 'Priority: - | Seq: -';
    btnExtractMax.disabled = true;
  }

  // WAL Persistence info
  const walLen = state.wal_records ? state.wal_records.length : 0;
  walCountVal.innerHTML = `${walLen} <span class="stat-unit">recent ops</span>`;
  if (state.snapshot_info && state.snapshot_info.exists) {
    snapshotMeta.textContent = `Snapshot: ${state.snapshot_info.item_count} items (${(state.snapshot_info.size_bytes / 1024).toFixed(1)} KB)`;
  } else {
    snapshotMeta.textContent = `Snapshot: None (Clean WAL replay)`;
  }
  walFilePath.textContent = `Storage Directory: ${state.storage_dir}`;

  // Populate Item Select Dropdowns
  populateDropdowns(state.nodes);

  // Render Visual Tree & Array Views
  renderTree(state.nodes);
  renderArrayAndMap(state.nodes);

  // Render WAL Log Stream
  renderWalLog(state.wal_records);
}

// Populate Select Dropdowns for Update and Delete
function populateDropdowns(nodes) {
  const currentUpdateVal = updateItemSelect.value;
  const currentDeleteVal = deleteItemSelect.value;

  updateItemSelect.innerHTML = '<option value="">-- Choose an item to update --</option>';
  deleteItemSelect.innerHTML = '<option value="">-- Choose an item to delete --</option>';

  nodes.forEach(node => {
    const desc = node.data && node.data.name ? ` (${node.data.name})` : '';
    const optText = `${node.item_id} [Prio: ${node.priority}]${desc}`;

    const opt1 = document.createElement('option');
    opt1.value = node.item_id;
    opt1.textContent = optText;
    updateItemSelect.appendChild(opt1);

    const opt2 = document.createElement('option');
    opt2.value = node.item_id;
    opt2.textContent = optText;
    deleteItemSelect.appendChild(opt2);
  });

  if (currentUpdateVal) updateItemSelect.value = currentUpdateVal;
  if (currentDeleteVal) deleteItemSelect.value = currentDeleteVal;
}

// Binary Tree Visualizer Layout Algorithm
function renderTree(nodes) {
  treeNodesContainer.innerHTML = '';
  treeSvg.innerHTML = '';

  if (!nodes || nodes.length === 0) {
    emptyTreePlaceholder.style.display = 'flex';
    return;
  }
  emptyTreePlaceholder.style.display = 'none';

  const n = nodes.length;
  const maxLevel = Math.floor(Math.log2(n));

  // Determine dimensions
  const containerWidth = Math.max(treeViewport.clientWidth - 40, Math.pow(2, Math.min(maxLevel, 4)) * 140);
  const containerHeight = Math.max(460, (maxLevel + 1) * 110 + 60);

  treeNodesContainer.style.width = `${containerWidth}px`;
  treeNodesContainer.style.height = `${containerHeight}px`;
  treeSvg.setAttribute('width', containerWidth);
  treeSvg.setAttribute('height', containerHeight);

  // Calculate coordinates for each node index
  const positions = {};

  nodes.forEach(node => {
    const idx = node.index;
    const level = node.level;
    const itemsInLevel = Math.pow(2, level);
    const indexInLevel = idx - (itemsInLevel - 1);

    // Slot spacing
    const slotWidth = containerWidth / (itemsInLevel + 1);
    const x = slotWidth * (indexInLevel + 1);
    const y = 50 + level * 95;

    positions[idx] = { x, y };
  });

  // Draw connecting edges in SVG
  nodes.forEach(node => {
    const idx = node.index;
    const pos = positions[idx];

    // Left child edge
    if (node.left_child !== null && positions[node.left_child]) {
      const leftPos = positions[node.left_child];
      drawSvgLine(pos.x, pos.y, leftPos.x, leftPos.y);
    }
    // Right child edge
    if (node.right_child !== null && positions[node.right_child]) {
      const rightPos = positions[node.right_child];
      drawSvgLine(pos.x, pos.y, rightPos.x, rightPos.y);
    }
  });

  // Render Node DOM elements
  nodes.forEach(node => {
    const idx = node.index;
    const pos = positions[idx];

    const wrapper = document.createElement('div');
    wrapper.className = 'tree-node-wrapper';
    wrapper.style.left = `${pos.x}px`;
    wrapper.style.top = `${pos.y}px`;

    const isMin = node.is_min_level;
    const levelClass = isMin ? 'min-level' : 'max-level';
    const rootClass = idx === 0 ? 'root-min' : '';

    const label = isMin ? `MIN LVL ${node.level}` : `MAX LVL ${node.level}`;
    const payloadTitle = node.data ? (node.data.name || node.data.description || node.data.type || '') : '';

    wrapper.innerHTML = `
      <div class="tree-node-card ${levelClass} ${rootClass}" title="${payloadTitle}">
        <span class="node-level-tag">${label}</span>
        <div class="node-id">${escapeHtml(node.item_id)}</div>
        <div class="node-priority">P: ${node.priority.toFixed(1)}</div>
        <div class="node-seq">[idx: ${idx} | seq: #${node.seq}]</div>
      </div>
    `;

    // Click on node to quick-select for update
    wrapper.addEventListener('click', () => {
      updateItemSelect.value = node.item_id;
      deleteItemSelect.value = node.item_id;
      const tabUpdate = document.querySelector('[data-tab="update-tab"]');
      if (tabUpdate) tabUpdate.click();
      showToast(`Selected "${node.item_id}" in form`, 'info');
    });

    treeNodesContainer.appendChild(wrapper);
  });
}

function drawSvgLine(x1, y1, x2, y2) {
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', x1);
  line.setAttribute('y1', y1);
  line.setAttribute('x2', x2);
  line.setAttribute('y2', y2);
  line.setAttribute('class', 'tree-edge');
  treeSvg.appendChild(line);
}

// Flat Array & PosMap View
function renderArrayAndMap(nodes) {
  arrayStrip.innerHTML = '';
  posmapGrid.innerHTML = '';

  if (!nodes || nodes.length === 0) {
    arrayStrip.innerHTML = '<div class="text-muted text-sm">Empty Array</div>';
    posmapGrid.innerHTML = '<div class="text-muted text-sm">Empty Hash Map</div>';
    return;
  }

  nodes.forEach(node => {
    // Array cell
    const cell = document.createElement('div');
    cell.className = `array-cell ${node.is_min_level ? 'min-cell' : 'max-cell'}`;
    cell.innerHTML = `
      <div class="array-index">[${node.index}]</div>
      <div class="node-id">${escapeHtml(node.item_id)}</div>
      <div class="text-xs font-bold">P: ${node.priority.toFixed(1)}</div>
    `;
    arrayStrip.appendChild(cell);

    // PosMap card
    const mapCard = document.createElement('div');
    mapCard.className = 'posmap-card';
    mapCard.innerHTML = `
      <span class="text-cyan">${escapeHtml(node.item_id)}</span>
      <span class="text-muted">➔ idx: <strong>${node.index}</strong></span>
    `;
    posmapGrid.appendChild(mapCard);
  });
}

// Write-Ahead Log (WAL) Console
function renderWalLog(records) {
  walLogStream.innerHTML = '';
  if (!records || records.length === 0) {
    walLogStream.innerHTML = '<div class="text-muted text-xs p-2">WAL is currently empty. Mutations will stream here live.</div>';
    return;
  }

  records.forEach(rec => {
    const entry = document.createElement('div');
    entry.className = `wal-entry op-${rec.op}`;

    const payloadSummary = JSON.stringify(rec.payload);
    entry.innerHTML = `
      <span class="wal-checksum">${rec.checksum}</span>
      <span class="wal-op">${rec.op}</span>
      <span class="wal-payload">${escapeHtml(payloadSummary)}</span>
    `;
    walLogStream.appendChild(entry);
  });
}

// Helper: Escape HTML
function escapeHtml(str) {
  if (typeof str !== 'string') return String(str);
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// --------------------------------------------------------------------------
// Event Handlers & API Calls
// --------------------------------------------------------------------------

// 1. Insert Form
document.getElementById('insertForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const itemId = document.getElementById('insertItemId').value.trim();
  const priority = parseFloat(document.getElementById('insertPriority').value);
  const payloadRaw = document.getElementById('insertPayload').value.trim();

  let payload = null;
  if (payloadRaw) {
    try {
      payload = JSON.parse(payloadRaw);
    } catch {
      payload = { description: payloadRaw };
    }
  }

  try {
    const res = await fetch('/api/insert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId || null, priority, data: payload })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to insert');
    
    showToast(`Inserted item "${data.item.item_id}" with priority ${data.item.priority}`, 'success');
    document.getElementById('insertItemId').value = '';
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// Quick priority presets buttons
document.querySelectorAll('.btn-micro[data-prio]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById('insertPriority').value = btn.getAttribute('data-prio');
  });
});

// 2. Extract Min & Max
btnExtractMin.addEventListener('click', async () => {
  try {
    const res = await fetch('/api/extract_min', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to extract min');
    showToast(`⚡ Extracted Min: "${data.extracted.item_id}" (Priority: ${data.extracted.priority})`, 'info');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

btnExtractMax.addEventListener('click', async () => {
  try {
    const res = await fetch('/api/extract_max', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to extract max');
    showToast(`🔥 Extracted Max: "${data.extracted.item_id}" (Priority: ${data.extracted.priority})`, 'info');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 3. Update Form
document.getElementById('updateForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const itemId = updateItemSelect.value;
  if (!itemId) {
    showToast('Please select an item to update', 'error');
    return;
  }
  const prioRaw = document.getElementById('updateNewPriority').value;
  const newPriority = prioRaw !== '' ? parseFloat(prioRaw) : null;
  const payloadRaw = document.getElementById('updateNewPayload').value.trim();

  let newPayload = null;
  if (payloadRaw) {
    try {
      newPayload = JSON.parse(payloadRaw);
    } catch {
      newPayload = { description: payloadRaw };
    }
  }

  try {
    const res = await fetch('/api/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, new_priority: newPriority, new_data: newPayload })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to update');
    showToast(`Updated "${itemId}" (New Priority: ${data.item.priority})`, 'success');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 4. Delete Form
document.getElementById('deleteForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const itemId = deleteItemSelect.value;
  if (!itemId) {
    showToast('Please select an item to delete', 'error');
    return;
  }

  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to delete');
    showToast(`Deleted item "${itemId}" in O(log N)`, 'info');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 5. Clear Queue
document.getElementById('btnClearQueue').addEventListener('click', async () => {
  if (!confirm('Are you sure you want to clear the entire queue?')) return;
  try {
    const res = await fetch('/api/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    showToast('Queue cleared', 'info');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 6. Save Snapshot
document.getElementById('btnSnapshot').addEventListener('click', async () => {
  try {
    const res = await fetch('/api/checkpoint', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    showToast('Snapshot checkpoint saved & WAL compacted!', 'success');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 7. Simulate Crash & Reload
document.getElementById('btnCrashReload').addEventListener('click', async () => {
  try {
    const res = await fetch('/api/crash_reload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    showToast(`💥 Crash Simulated! Reconstructed ${data.result.recovered_items_count} items from disk WAL!`, 'success');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 8. Scenario Presets
document.querySelectorAll('[data-scenario]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const scenario = btn.getAttribute('data-scenario');
    try {
      const res = await fetch('/api/scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario })
      });
      const data = await res.json();
      showToast(data.result.message, 'success');
      renderDashboard(data.state);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
});

// 9. Interactive Triage Simulation Actions
document.getElementById('btnAnaphylaxisAlert').addEventListener('click', async () => {
  try {
    const res = await fetch('/api/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: 'P_005',
        new_priority: 0.1,
        new_data: { name: 'Jane Smith', acuity: 'CRITICAL ANAPHYLAXIS', condition: 'Airway constriction / emergency epinephrine' }
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Please load Hospital ER Triage scenario first');
    showToast('🚨 Critical Alert: Jane Smith priority escalated to 0.1 (Top of Min-Heap)!', 'warning');
    renderDashboard(data.state);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

document.getElementById('btnAgingTick').addEventListener('click', async () => {
  if (!currentState || !currentState.nodes || currentState.nodes.length === 0) {
    showToast('Queue is empty. Load a scenario first.', 'error');
    return;
  }
  try {
    for (const node of currentState.nodes) {
      if (node.priority > 1.0) {
        await fetch('/api/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: node.item_id, new_priority: Math.max(0.1, node.priority - 0.5) })
        });
      }
    }
    showToast('⏳ Priority Aging applied: boosted waiting tasks by -0.5!', 'info');
    await fetchState();
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// 10. Refresh WAL Log Button
document.getElementById('btnRefreshWal').addEventListener('click', () => {
  fetchState();
  showToast('WAL log refreshed', 'info');
});

// 11. Tab Switching
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    btn.classList.add('active');
    const tabId = btn.getAttribute('data-tab');
    document.getElementById(tabId).classList.add('active');
  });
});

// 12. Tree vs Array View Toggle
const btnViewTree = document.getElementById('btnViewTree');
const btnViewArray = document.getElementById('btnViewArray');

btnViewTree.addEventListener('click', () => {
  btnViewTree.classList.add('active');
  btnViewArray.classList.remove('active');
  treeViewport.style.display = 'block';
  arrayViewport.classList.add('hidden');
});

btnViewArray.addEventListener('click', () => {
  btnViewArray.classList.add('active');
  btnViewTree.classList.remove('active');
  treeViewport.style.display = 'none';
  arrayViewport.classList.remove('hidden');
});

// Auto-refresh polling every 3 seconds to catch external mutations
setInterval(fetchState, 3000);

// Initial Load
fetchState();
