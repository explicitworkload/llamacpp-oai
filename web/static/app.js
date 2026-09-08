const API = '';
let token = localStorage.getItem('cmd_token');
let activeModel = null;
let messages = [];
let generating = false;

// Auth
async function login() {
  const pwd = document.getElementById('login-password').value;
  const status = document.getElementById('login-status');
  const btn = document.getElementById('login-btn');

  if (!pwd) return;
  btn.disabled = true;
  status.className = 'login-status';
  status.textContent = 'AUTHENTICATING...';

  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd }),
    });

    if (!res.ok) {
      status.className = 'login-status error';
      status.textContent = 'ACCESS DENIED';
      btn.disabled = false;
      return;
    }

    const data = await res.json();
    token = data.token;
    localStorage.setItem('cmd_token', token);

    status.className = 'login-status success';
    status.textContent = 'ACCESS GRANTED';

    setTimeout(() => showApp(), 600);
  } catch {
    status.className = 'login-status error';
    status.textContent = 'CONNECTION FAILED';
    btn.disabled = false;
  }
}

function logout() {
  token = null;
  localStorage.removeItem('cmd_token');
  activeModel = null;
  messages = [];
  document.querySelector('.app-screen').classList.remove('active');
  document.querySelector('.login-screen').classList.remove('hidden');
  document.getElementById('login-password').value = '';
  document.getElementById('login-status').textContent = '';
  document.getElementById('login-btn').disabled = false;
}

function authHeaders() {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// App
async function showApp() {
  document.querySelector('.login-screen').classList.add('hidden');
  document.querySelector('.app-screen').classList.add('active');
  await loadModels();
}

async function loadModels() {
  const list = document.getElementById('model-list');
  try {
    const res = await fetch(`${API}/api/models`, { headers: authHeaders() });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();

    list.innerHTML = '';
    const count = document.getElementById('model-count');
    const online = data.models.filter(m => m.ready).length;
    count.textContent = `${online}/${data.models.length} ONLINE`;

    data.models.forEach(m => {
      const el = document.createElement('div');
      el.className = `model-item${m.ready ? '' : ' offline'}${activeModel === m.name ? ' active' : ''}`;
      el.innerHTML = `
        <div class="model-dot ${m.ready ? 'online' : 'offline'}"></div>
        <div class="model-info">
          <div class="model-name">${esc(m.display || m.name)}</div>
          <div class="model-id">${esc(m.name)}</div>
        </div>`;
      if (m.ready) {
        el.addEventListener('click', () => selectModel(m));
      }
      list.appendChild(el);
    });
  } catch {
    list.innerHTML = '<div style="padding:16px;color:var(--red);font-size:11px">FAILED TO LOAD UNITS</div>';
  }
}

function selectModel(m) {
  activeModel = m.name;
  document.querySelectorAll('.model-item').forEach(el => {
    el.classList.toggle('active', el.querySelector('.model-id').textContent === m.name);
  });
  document.getElementById('chat-target').textContent = `CHANNEL: ${(m.display || m.name).toUpperCase()}`;
  document.getElementById('chat-input').focus();
  renderMessages();
}

// Chat
let streamingEl = null;
let streamStats = null;

function formatStatsHtml(stats, streaming) {
  const now = streaming ? performance.now() : stats.endTime;
  const elapsed = ((now - stats.startTime) / 1000).toFixed(1);
  const parts = [];

  if (stats.firstTokenTime) {
    parts.push(`TTFT ${((stats.firstTokenTime - stats.startTime) / 1000).toFixed(2)}s`);
  }
  if (stats.firstContentTime && stats.firstTokenTime &&
      stats.firstContentTime - stats.firstTokenTime > 50) {
    parts.push(`TTFO ${((stats.firstContentTime - stats.startTime) / 1000).toFixed(2)}s`);
  }

  const tokens = stats.completionTokens || stats.tokenCount;
  if (tokens > 0) {
    parts.push(`${tokens} TOKENS`);
    const genTime = stats.firstTokenTime ? (now - stats.firstTokenTime) / 1000 : 0;
    if (genTime > 0.1) {
      parts.push(`${(tokens / genTime).toFixed(1)} T/s`);
    }
  }
  if (stats.promptTokens != null) {
    parts.push(`${stats.promptTokens} PROMPT`);
  }
  parts.push(`${elapsed}s`);
  if (streaming) parts.push('<span class="stats-live">LIVE</span>');

  return parts.join(' <span class="stats-sep">|</span> ');
}

function buildMessageEl(msg) {
  const el = document.createElement('div');
  el.className = `message ${msg.role}`;
  const label = msg.role === 'user' ? 'OPERATOR' : 'AI UNIT';
  let body = '';
  if (msg.thinking) {
    body += `<details class="message-thinking"><summary>REASONING LOG</summary>${esc(msg.thinking)}</details>`;
  }
  body += formatContent(msg.content || '');
  if (msg.stats) {
    body += `<div class="message-stats">${formatStatsHtml(msg.stats, false)}</div>`;
  }
  el.innerHTML = `<div class="message-label">${label}</div><div class="message-body">${body}</div>`;
  return el;
}

function renderMessages() {
  const container = document.getElementById('chat-messages');
  streamingEl = null;

  if (!activeModel) {
    container.innerHTML = '<div class="no-model-selected">SELECT A UNIT TO BEGIN</div>';
    return;
  }

  if (messages.length === 0 && !generating) {
    container.innerHTML = `
      <div class="chat-empty">
        <div class="chat-empty-icon">&gt;_</div>
        <div class="chat-empty-text">AWAITING TRANSMISSION</div>
      </div>`;
    return;
  }

  container.innerHTML = '';
  messages.forEach(msg => container.appendChild(buildMessageEl(msg)));

  if (generating) {
    const el = document.createElement('div');
    el.className = 'message assistant';
    el.innerHTML = `
      <div class="message-label">AI UNIT</div>
      <div class="message-body">
        <span class="typing-indicator">
          <span>PROCESSING</span>
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </span>
      </div>`;
    container.appendChild(el);
  }

  container.scrollTop = container.scrollHeight;
}

function updateStreamingMessage(msg) {
  const container = document.getElementById('chat-messages');

  if (!streamingEl) {
    const loading = container.querySelector('.typing-indicator');
    if (loading) loading.closest('.message').remove();
    streamingEl = document.createElement('div');
    streamingEl.className = 'message assistant';
    streamingEl.innerHTML = '<div class="message-label">AI UNIT</div><div class="message-body"></div>';
    container.appendChild(streamingEl);
  }

  const body = streamingEl.querySelector('.message-body');
  let thinkingEl = body.querySelector('.message-thinking');

  if (msg.thinking) {
    if (!thinkingEl) {
      thinkingEl = document.createElement('details');
      thinkingEl.className = 'message-thinking';
      thinkingEl.open = true;
      thinkingEl.innerHTML = '<summary>REASONING LOG</summary><div class="thinking-content"></div>';
      body.prepend(thinkingEl);
    }
    thinkingEl.querySelector('.thinking-content').textContent = msg.thinking;
  }

  let contentEl = body.querySelector('.content-area');
  if (!contentEl) {
    contentEl = document.createElement('span');
    contentEl.className = 'content-area';
    body.appendChild(contentEl);
  }
  contentEl.innerHTML = formatContent(msg.content || '');

  if (streamStats) {
    let statsEl = body.querySelector('.message-stats');
    if (!statsEl) {
      statsEl = document.createElement('div');
      statsEl.className = 'message-stats';
      body.appendChild(statsEl);
    }
    statsEl.innerHTML = formatStatsHtml(streamStats, true);
  }

  container.scrollTop = container.scrollHeight;
}

function formatContent(text) {
  if (!text) return '';
  let html = esc(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !activeModel || generating) return;

  input.value = '';
  input.style.height = 'auto';

  messages.push({ role: 'user', content: text });
  generating = true;
  renderMessages();

  const apiMessages = messages
    .filter(m => m.content && !m.content.includes('[TRANSMISSION ERROR:'))
    .map(m => ({ role: m.role, content: m.content }));

  const stats = {
    startTime: performance.now(),
    firstTokenTime: null,
    firstContentTime: null,
    endTime: null,
    tokenCount: 0,
    promptTokens: null,
    completionTokens: null,
  };
  streamStats = stats;
  let assistantMsg = null;

  try {
    const res = await fetch(`${API}/api/chat/completions`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        model_endpoint: activeModel,
        model: 'default',
        messages: apiMessages,
        stream: true,
        stream_options: { include_usage: true },
      }),
    });

    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    assistantMsg = { role: 'assistant', content: '', thinking: '', stats: null };
    messages.push(assistantMsg);

    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') break;

        try {
          const chunk = JSON.parse(data);

          if (chunk.error) {
            throw new Error(chunk.error.message || 'upstream error');
          }

          const delta = chunk.choices?.[0]?.delta;
          if (delta) {
            if (delta.reasoning_content) {
              assistantMsg.thinking += delta.reasoning_content;
              stats.tokenCount++;
              if (!stats.firstTokenTime) stats.firstTokenTime = performance.now();
            }
            if (delta.content) {
              assistantMsg.content += delta.content;
              stats.tokenCount++;
              if (!stats.firstTokenTime) stats.firstTokenTime = performance.now();
              if (!stats.firstContentTime) stats.firstContentTime = performance.now();
            }
            updateStreamingMessage(assistantMsg);
          }

          if (chunk.usage) {
            stats.promptTokens = chunk.usage.prompt_tokens;
            stats.completionTokens = chunk.usage.completion_tokens;
          }
        } catch (e) {
          if (e instanceof SyntaxError) continue;
          throw e;
        }
      }
    }
  } catch (err) {
    if (assistantMsg) {
      assistantMsg.content += (assistantMsg.content ? '\n\n' : '') + `[TRANSMISSION ERROR: ${err.message}]`;
    } else {
      messages.push({ role: 'assistant', content: `[TRANSMISSION ERROR: ${err.message}]` });
    }
  }

  stats.endTime = performance.now();
  if (assistantMsg) assistantMsg.stats = stats;
  streamStats = null;
  generating = false;
  renderMessages();
}

function clearChat() {
  messages = [];
  renderMessages();
}

// Input handling
function handleInput(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('login-btn').addEventListener('click', login);
  document.getElementById('login-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') login();
  });
  document.getElementById('btn-send').addEventListener('click', sendMessage);
  document.getElementById('chat-input').addEventListener('keydown', handleInput);
  document.getElementById('chat-input').addEventListener('input', function () { autoResize(this); });
  document.getElementById('btn-refresh').addEventListener('click', loadModels);
  document.getElementById('btn-clear').addEventListener('click', clearChat);
  document.getElementById('btn-logout').addEventListener('click', logout);

  if (token) {
    fetch(`${API}/api/models`, { headers: authHeaders() })
      .then(r => { if (r.ok) showApp(); else logout(); })
      .catch(() => logout());
  }

  setInterval(() => { if (token) loadModels(); }, 30000);
});
