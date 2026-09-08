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

function buildMessageEl(msg) {
  const el = document.createElement('div');
  el.className = `message ${msg.role}`;
  const label = msg.role === 'user' ? 'OPERATOR' : 'AI UNIT';
  let body = '';
  if (msg.thinking) {
    body += `<details class="message-thinking"><summary>REASONING LOG</summary>${esc(msg.thinking)}</details>`;
  }
  body += formatContent(msg.content || '');
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

  const apiMessages = messages.map(m => ({ role: m.role, content: m.content }));

  try {
    const res = await fetch(`${API}/api/chat/completions`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        model_endpoint: activeModel,
        model: 'default',
        messages: apiMessages,
        stream: true,
      }),
    });

    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let assistantMsg = { role: 'assistant', content: '', thinking: '' };
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
          const delta = chunk.choices?.[0]?.delta;
          if (!delta) continue;

          if (delta.reasoning_content) {
            assistantMsg.thinking += delta.reasoning_content;
          }
          if (delta.content) {
            assistantMsg.content += delta.content;
          }
          updateStreamingMessage(assistantMsg);
        } catch {}
      }
    }
  } catch (err) {
    messages.push({ role: 'assistant', content: `[TRANSMISSION ERROR: ${err.message}]` });
  }

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
