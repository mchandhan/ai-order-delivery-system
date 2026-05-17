/* ============================================================
   app.js — OrderMind AI frontend logic
   ============================================================ */

// ── Toast System ─────────────────────────────────────────────
function showToast(message, type = "info", duration = 3500) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  const icons = { success: "✅", error: "❌", info: "ℹ️" };
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || "💬"}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast-out");
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Markdown-lite renderer ────────────────────────────────────
function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g,     "<em>$1</em>")
    .replace(/`(.*?)`/g,       "<code>$1</code>")
    .replace(/\n/g,            "<br>");
}

// ── Time format ───────────────────────────────────────────────
function timeNow() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ============================================================
//  CHAT PAGE
// ============================================================

function initChat() {
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const clearBtn = document.getElementById("clear-chat-btn");

  // Welcome message
  appendMessage("ai", "👋 Hi! I'm your **OrderMind Assistant** powered by Qwen3.\n\nYou can:\n- **Create orders** — _\"Create an order for 50 steel bolts due June 30\"_\n- **Update status** — _\"Mark order #3 as accepted\"_\n- **Add quality notes** — _\"Add quality note to order 2: minor surface scratches\"_\n- **Query orders** — _\"Show me order #5\"_ or _\"List all pending orders\"_\n\nWhat would you like to do?");

  // Auto-resize textarea
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  // Enter = send, Shift+Enter = newline
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Clear chat
  clearBtn.addEventListener("click", () => {
    const msgs = document.getElementById("chat-messages");
    msgs.innerHTML = "";
    appendMessage("ai", "Chat cleared. How can I help you with orders today?");
  });
}

function appendMessage(role, text, type = "chat") {
  const container = document.getElementById("chat-messages");
  const wrapper = document.createElement("div");
  const avatarEmoji = role === "user" ? "👤" : role === "error" ? "⚠️" : "🤖";
  const msgRole = (type === "error") ? "error" : role;

  wrapper.className = `message ${msgRole}`;
  wrapper.innerHTML = `
    <div class="msg-avatar">${avatarEmoji}</div>
    <div>
      <div class="msg-bubble">${renderMarkdown(text)}</div>
      <div class="msg-time">${timeNow()}</div>
    </div>`;
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
  return wrapper;
}

function showTypingIndicator() {
  const container = document.getElementById("chat-messages");
  const indicator = document.createElement("div");
  indicator.className = "message ai typing-indicator";
  indicator.id = "typing-indicator";
  indicator.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div>
      <div class="msg-bubble">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>`;
  container.appendChild(indicator);
  container.scrollTop = container.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

async function sendMessage() {
  const input   = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const message = input.value.trim();
  if (!message) return;

  // Append user bubble
  appendMessage("user", message);
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  // Typing indicator
  showTypingIndicator();

  try {
    const res = await fetch("/chat/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });

    const data = await res.json();
    removeTypingIndicator();

    if (!res.ok || data.type === "error") {
      appendMessage("error", data.reply || "An error occurred.", "error");
    } else {
      appendMessage("ai", data.reply, data.type || "chat");

      // Refresh sidebar after successful DB action
      if (["success"].includes(data.type)) {
        refreshChatSidebar();
      }
    }
  } catch (err) {
    removeTypingIndicator();
    appendMessage("error", `⚠️ Network error: ${err.message}`, "error");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

function useChip(btn) {
  const input = document.getElementById("chat-input");
  input.value = btn.dataset.msg;
  sendMessage();
}

function askAboutOrder(orderId) {
  const input = document.getElementById("chat-input");
  input.value = `Show me details for order #${orderId}`;
  sendMessage();
}

async function refreshChatSidebar() {
  try {
    const res  = await fetch("/orders/api?status=all");
    const data = await res.json();
    const orders = data.orders.slice(0, 5);
    const sidebar = document.getElementById("sidebar-orders");
    const count   = document.getElementById("sidebar-count");
    if (!sidebar) return;

    count.textContent = orders.length;
    sidebar.innerHTML = orders.map(o => `
      <div class="sidebar-order-card" onclick="askAboutOrder(${o.order_id})">
        <div class="soc-header">
          <span class="soc-id">#${o.order_id}</span>
          <span class="soc-badge status-${o.status.toLowerCase().replace(" ", "-")}">${o.status}</span>
        </div>
        <div class="soc-part">${o.part}</div>
        <div class="soc-meta">${o.quantity.toLocaleString()} units · ${o.deadline}</div>
      </div>
    `).join("");
  } catch (_) {}
}

// ============================================================
//  DASHBOARD PAGE
// ============================================================

let dashRefreshTimer = null;
let currentSort = { col: "order_id", dir: "DESC" };

function initDashboard() {
  // Initial load
  refreshDashboard();
  dashRefreshTimer = setInterval(refreshDashboard, 15000); // Slower refresh for big data
}

async function refreshDashboard() {
  const filter = document.getElementById("status-filter")?.value || "all";
  const search = document.getElementById("search-input")?.value || "";
  
  try {
    const url = `/orders/api?status=${filter}&q=${encodeURIComponent(search)}&sort=${currentSort.col}&dir=${currentSort.dir}`;
    const res  = await fetch(url);
    const data = await res.json();
    updateStatCards(data.stats);
    updateOrdersTable(data.orders);
  } catch (err) {
    console.error("Dashboard refresh error:", err);
  }
}

function sortBy(column) {
  if (currentSort.col === column) {
    currentSort.dir = currentSort.dir === "ASC" ? "DESC" : "ASC";
  } else {
    currentSort.col = column;
    currentSort.dir = "DESC";
  }
  
  // Update header UI
  document.querySelectorAll(".sort-indicator").forEach(el => el.textContent = "");
  const indicator = document.getElementById(`sort-icon-${column}`);
  if (indicator) {
    indicator.textContent = currentSort.dir === "ASC" ? " 🔼" : " 🔽";
  }
  
  refreshDashboard();
}

function updateStatCards(stats) {
  const map = {
    "stat-val-total":      stats.Total,
    "stat-val-pending":    stats.Received || 0,
    "stat-val-inprogress": stats["In Review"] || 0,
    "stat-val-accepted":   stats.Accepted || 0,
    "stat-val-rejected":   stats.Rejected || 0,
  };
  for (const [id, val] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el && el.textContent !== String(val)) {
      el.textContent = val;
      el.parentElement.style.transform = "scale(1.05)";
      setTimeout(() => el.parentElement.style.transform = "", 300);
    }
  }
}

function updateOrdersTable(orders) {
  const tbody = document.getElementById("orders-tbody");
  const count = document.getElementById("table-count");
  if (!tbody) return;

  count.textContent = `${orders.length} orders`;
  
  // Clear the table to ensure correct sort order and search results are shown
  tbody.innerHTML = "";

  orders.forEach(o => {
    const badge = `<span class="status-badge status-${o.status.toLowerCase().replace(" ", "-")}">${o.status}</span>`;
    
    const tr = document.createElement("tr");
    tr.className = "order-row";
    tr.dataset.id = o.order_id;
    tr.dataset.status = o.status.toLowerCase();
    tr.setAttribute("onclick", `toggleQualityLogs(${o.order_id}, this)`);
    tr.innerHTML = `
      <td class="td-id">#${o.order_id}</td>
      <td class="td-part">${o.part}</td>
      <td class="td-material">${o.material}</td>
      <td class="td-qty">${o.quantity.toLocaleString()}</td>
      <td class="td-deadline">${o.deadline}</td>
      <td class="td-status">${badge}</td>
      <td class="td-note" style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${o.latest_log || ''}">
        ${o.latest_log || '<span style="color:var(--text-muted)">—</span>'}
      </td>
      <td class="td-created">${o.created_at ? o.created_at.slice(0,10) : "—"}</td>
      <td class="td-actions" onclick="event.stopPropagation()">
        <select class="inline-status-select" onchange="quickUpdateStatus(${o.order_id}, this.value)">
          <option value="">Change…</option>
          <option value="Received">Received</option>
          <option value="In Review">In Review</option>
          <option value="Accepted">Accepted</option>
          <option value="Completed">Completed</option>
          <option value="Rejected">Rejected</option>
        </select>
      </td>`;
    tbody.appendChild(tr);

    const qlTr = document.createElement("tr");
    qlTr.className = "ql-row";
    qlTr.id = `ql-row-${o.order_id}`;
    qlTr.style.display = "none";
    qlTr.innerHTML = `<td colspan="8"><div class="ql-panel" id="ql-panel-${o.order_id}"><span class="ql-loading">Loading…</span></div></td>`;
    tbody.appendChild(qlTr);
  });
}

// ── Table search/filter ───────────────────────────────────────
let searchDebounce = null;
function filterTable() {
  // Clear any existing timer to debounce the search
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    refreshDashboard();
  }, 300); // Wait 300ms after last keystroke before querying server
}

// ── Quality Log Expansion ─────────────────────────────────────
async function toggleQualityLogs(orderId, row) {
  const qlRow   = document.getElementById(`ql-row-${orderId}`);
  const qlPanel = document.getElementById(`ql-panel-${orderId}`);
  if (!qlRow) return;

  if (qlRow.style.display !== "none") {
    qlRow.style.display = "none";
    return;
  }

  qlRow.style.display = "";
  qlPanel.innerHTML = `<span class="ql-loading">Loading quality logs…</span>`;

  try {
    const res  = await fetch(`/orders/api/${orderId}`);
    const data = await res.json();
    const logs = data.quality_logs || [];

    if (!logs.length) {
      qlPanel.innerHTML = `
        <div class="ql-header">📋 Quality Logs — Order #${orderId}</div>
        <p class="ql-empty">No quality logs yet. Use the chat to add one.</p>`;
    } else {
      qlPanel.innerHTML = `
        <div class="ql-header">📋 Quality Logs — Order #${orderId} (${logs.length})</div>
        <div class="ql-list">
          ${logs.map(l => `
            <div class="ql-item">
              <div class="ql-item-dot"></div>
              <div>
                <div class="ql-item-note">${l.note}</div>
                <div class="ql-item-time">${l.timestamp?.slice(0,16) || ""}</div>
              </div>
            </div>`).join("")}
        </div>`;
    }
  } catch (err) {
    qlPanel.innerHTML = `<span class="ql-empty">Error loading logs.</span>`;
  }
}

// ── Inline status update ──────────────────────────────────────
async function quickUpdateStatus(orderId, newStatus) {
  if (!newStatus) return;
  try {
    const res = await fetch("/orders/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_id: orderId, status: newStatus })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Order #${orderId} → ${newStatus}`, "success");
      // Update badge immediately
      const row = document.querySelector(`[data-id="${orderId}"]`);
      if (row) {
        row.dataset.status = newStatus.toLowerCase();
        row.querySelector(".td-status").innerHTML =
          `<span class="status-badge status-${newStatus.toLowerCase().replace(" ", "-")}">${newStatus}</span>`;
      }
      refreshDashboard();
    } else {
      showToast(`Failed to update order #${orderId}`, "error");
    }
  } catch (err) {
    showToast("Network error", "error");
  }
}
