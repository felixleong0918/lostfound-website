const appState = {
  session: null,
  externalItems: [],
  reports: [],
  matches: [],
  notifications: []
};

const authScreen = document.getElementById('authScreen');
const appScreen = document.getElementById('appScreen');
const authAlert = document.getElementById('authAlert');
const viewTitle = document.getElementById('viewTitle');
const viewSubtitle = document.getElementById('viewSubtitle');
const navItems = document.querySelectorAll('.nav-item');
const views = document.querySelectorAll('.view');
const authTabs = document.querySelectorAll('.auth-tab');
const authForms = document.querySelectorAll('.auth-form');

const titleMap = {
  dashboard: ['首頁', '查看最新招領、你的通報與通知。'],
  sources: ['招領清單', '找到疑似物品後，請依來源資訊前往認領。'],
  report: ['通報遺失物', '留下物品特徵、時間與地點，方便後續比對。'],
  matches: ['可能符合的物品', '這裡會列出和你的通報相近的招領物。'],
  notifications: ['通知紀錄', '查看近期通知與處理狀態。']
};

function showBanner(message, kind = 'info') {
  authAlert.className = `status-banner ${kind}`;
  authAlert.textContent = message;
}

function hideBanner() {
  authAlert.className = 'status-banner hidden';
  authAlert.textContent = '';
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || 'Request failed');
  }
  return payload;
}

function switchAuthTab(tab) {
  authTabs.forEach((button) => button.classList.toggle('active', button.dataset.authTab === tab));
  authForms.forEach((form) => form.classList.toggle('active', form.id === `${tab}Form`));
  hideBanner();
}

function switchView(viewId) {
  navItems.forEach((button) => button.classList.toggle('active', button.dataset.view === viewId));
  views.forEach((view) => view.classList.toggle('active', view.id === viewId));
  viewTitle.textContent = titleMap[viewId][0];
  viewSubtitle.textContent = titleMap[viewId][1];
}

function formatTime(value) {
  return new Date(value).toLocaleString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function sourceMeta(item) {
  if (item.source_type === 'facebook') {
    return `<a href="${item.source_url}" target="_blank" rel="noreferrer">FB交流版連結</a>`;
  }
  return item.source_name;
}

function renderExternalItem(item) {
  return `
    <article class="item-card">
      <div class="card-badge">${item.category}</div>
      <h4>${item.title}</h4>
      <div class="item-meta">${item.location} ・ ${formatTime(item.found_at)}</div>
      <p>${item.description}</p>
      <div class="source-line">
        <span>來源</span>
        <strong>${item.source_name}</strong>
      </div>
      <div class="item-meta">${sourceMeta(item)}</div>
    </article>
  `;
}

function renderReport(report) {
  return `
    <div class="feed-item">
      <div class="feed-head">
        <strong>${report.title}</strong>
        <span class="chip">已通報</span>
      </div>
      <div class="item-meta">${report.category} ・ ${report.location} ・ ${formatTime(report.lost_at)}</div>
      <p>${report.description}</p>
    </div>
  `;
}

function renderMatch(match) {
  const reasonList = JSON.parse(match.reasons_json || '[]');
  return `
    <div class="match-item">
      <div class="feed-head">
        <div>
          <strong>${match.report_title}</strong>
          <div class="item-meta">對應招領物：${match.external_title}</div>
        </div>
        <span class="score">${match.score}%</span>
      </div>
      <div class="item-meta">${match.external_location} ・ ${match.external_source_name}</div>
      <ul class="match-reasons">
        ${reasonList.map((reason) => `<li>${reason}</li>`).join('')}
      </ul>
      <div class="match-link">${match.external_source_type === 'facebook' ? `<a href="${match.external_source_url}" target="_blank" rel="noreferrer">查看原始貼文</a>` : `來源：${match.external_source_name}`}</div>
    </div>
  `;
}

function renderNotification(notification) {
  return `
    <div class="notify-item ${notification.is_read ? 'read' : 'unread'}">
      <strong>${notification.subject}</strong>
      <div class="notify-meta">${notification.message}</div>
      <div class="notify-meta">${formatTime(notification.created_at)}</div>
    </div>
  `;
}

function applyFilters() {
  const keyword = document.getElementById('globalSearch').value.trim().toLowerCase();
  const source = document.getElementById('sourceFilter')?.value || 'all';
  const category = document.getElementById('categoryFilter')?.value || 'all';

  const filtered = appState.externalItems.filter((item) => {
    const matchesKeyword = !keyword || [item.title, item.location, item.description, item.source_name, item.category]
      .join(' ')
      .toLowerCase()
      .includes(keyword);
    const matchesSource = source === 'all' || item.source_name === source;
    const matchesCategory = category === 'all' || item.category === category;
    return matchesKeyword && matchesSource && matchesCategory;
  });

  document.getElementById('externalList').innerHTML = filtered.map(renderExternalItem).join('') || '<div class="empty-state">目前沒有符合條件的招領資料。</div>';
  document.getElementById('recentExternalList').innerHTML = filtered.slice(0, 4).map(renderExternalItem).join('') || '<div class="empty-state">目前沒有資料。</div>';
}

function renderSummary() {
  const summaryMap = appState.externalItems.reduce((accumulator, item) => {
    accumulator[item.source_name] = (accumulator[item.source_name] || 0) + 1;
    return accumulator;
  }, {});

  document.getElementById('sourceSummary').innerHTML = Object.entries(summaryMap).map(([name, count]) => `
    <div class="summary-card">
      <span>${name}</span>
      <strong>${count}</strong>
    </div>
  `).join('');
}

function renderReports() {
  document.getElementById('reportList').innerHTML = appState.reports.map(renderReport).join('') || '<div class="empty-state">你還沒有遺失通報。</div>';
}

function renderMatches() {
  document.getElementById('matchList').innerHTML = appState.matches.map(renderMatch).join('') || '<div class="empty-state">目前還沒有媒合結果。</div>';
  document.getElementById('recentMatchList').innerHTML = appState.matches.slice(0, 3).map(renderMatch).join('') || '<div class="empty-state">目前沒有最新媒合。</div>';
}

function renderNotifications() {
  document.getElementById('notificationList').innerHTML = appState.notifications.map(renderNotification).join('') || '<div class="empty-state">目前沒有通知。</div>';
}

function renderMetrics() {
  document.getElementById('externalCount').textContent = appState.externalItems.length;
  document.getElementById('reportCount').textContent = appState.reports.length;
  document.getElementById('matchCount').textContent = appState.matches.length;
  document.getElementById('notificationCount').textContent = appState.notifications.filter((item) => !item.is_read).length;
  document.getElementById('userGreeting').textContent = `${appState.session.name}，${appState.session.email}`;
}

function renderAll() {
  renderMetrics();
  renderSummary();
  applyFilters();
  renderReports();
  renderMatches();
  renderNotifications();
}

async function loadBundle() {
  const payload = await api('/api/bootstrap');
  appState.externalItems = payload.external_items;
  appState.reports = payload.reports;
  appState.matches = payload.matches;
  appState.notifications = payload.notifications;
  renderAll();
}

async function enterApp(sessionUser) {
  appState.session = sessionUser;
  authScreen.classList.add('hidden');
  appScreen.classList.remove('hidden');
  await loadBundle();
}

async function restoreSession() {
  try {
    const sessionPayload = await api('/api/session');
    await enterApp(sessionPayload.user);
  } catch (_error) {
    authScreen.classList.remove('hidden');
    appScreen.classList.add('hidden');
  }
}

authTabs.forEach((button) => {
  button.addEventListener('click', () => switchAuthTab(button.dataset.authTab));
});

navItems.forEach((button) => {
  button.addEventListener('click', () => switchView(button.dataset.view));
});

document.querySelectorAll('[data-jump]').forEach((button) => {
  button.addEventListener('click', () => switchView(button.dataset.jump));
});

document.getElementById('jumpReportBtn').addEventListener('click', () => switchView('report'));

document.getElementById('loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = Object.fromEntries(new FormData(event.target).entries());
  try {
    const payload = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify(formData)
    });
    await enterApp(payload.user);
  } catch (error) {
    showBanner(error.message, 'error');
  }
});

document.getElementById('registerForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = Object.fromEntries(new FormData(event.target).entries());
  try {
    const payload = await api('/api/register', {
      method: 'POST',
      body: JSON.stringify(formData)
    });
    await enterApp(payload.user);
  } catch (error) {
    showBanner(error.message, 'error');
  }
});

document.getElementById('reportForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = Object.fromEntries(new FormData(event.target).entries());
  try {
    const payload = await api('/api/report-lost', {
      method: 'POST',
      body: JSON.stringify(formData)
    });
    appState.reports = payload.reports;
    appState.matches = payload.matches;
    appState.notifications = payload.notifications;
    renderAll();
    event.target.reset();
    switchView('matches');
  } catch (error) {
    window.alert(error.message);
  }
});

document.getElementById('fillSuggestedBtn').addEventListener('click', () => {
  const form = document.getElementById('reportForm');
  form.title.value = '黑色 AirPods Pro';
  form.category.value = '電子產品';
  form.location.value = '總圖 2F 靠窗座位';
  form.lost_at.value = '2026-05-25T14:10';
  form.description.value = '黑色保護殼，殼上有白色貼紙，應該是放在插座附近。';
});

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' });
  window.location.reload();
});

document.getElementById('markReadBtn').addEventListener('click', async () => {
  const payload = await api('/api/notifications/read-all', { method: 'POST' });
  appState.notifications = payload.notifications;
  renderAll();
});

document.getElementById('globalSearch').addEventListener('input', applyFilters);
document.addEventListener('change', (event) => {
  if (event.target.id === 'sourceFilter' || event.target.id === 'categoryFilter') {
    applyFilters();
  }
});

restoreSession();
