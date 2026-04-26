const state = {
  items: [
    {
      id: 1,
      type: 'lost',
      title: '黑色 AirPods Pro',
      category: '電子產品',
      location: '總圖 2F',
      datetime: '2026-03-23T10:20',
      contact: 'b11902001@ntu.edu.tw',
      description: '黑色保護殼，外殼有白色貼紙，可能掉在座位附近。',
      emoji: '🎧'
    },
    {
      id: 2,
      type: 'found',
      title: 'AirPods Pro 耳機',
      category: '電子產品',
      location: '總圖 1F 服務台附近',
      datetime: '2026-03-23T11:05',
      contact: 'library-desk@ntu.edu.tw',
      description: '拾獲一副耳機，黑色殼，外側有貼紙。',
      emoji: '🎧'
    },
    {
      id: 3,
      type: 'lost',
      title: '學生證',
      category: '證件',
      location: '管理學院',
      datetime: '2026-03-22T16:10',
      contact: 'r12922033@ntu.edu.tw',
      description: '台大學生證，姓名可現場核對。',
      emoji: '🪪'
    },
    {
      id: 4,
      type: 'found',
      title: '學生證（管院）',
      category: '證件',
      location: '管理學院 1F',
      datetime: '2026-03-22T17:10',
      contact: 'mba-office@ntu.edu.tw',
      description: '在管理學院一樓撿到學生證一張。',
      emoji: '🪪'
    },
    {
      id: 5,
      type: 'found',
      title: '藍色水壺',
      category: '日用品',
      location: '活大前草地',
      datetime: '2026-03-23T12:05',
      contact: 'student-a@ntu.edu.tw',
      description: '藍色金屬水壺，外觀有些刮痕。',
      emoji: '🍼'
    },
    {
      id: 6,
      type: 'lost',
      title: '灰色雨傘',
      category: '日用品',
      location: '普通教學館',
      datetime: '2026-03-21T18:40',
      contact: 'student-b@ntu.edu.tw',
      description: '灰色長傘，木頭握把。',
      emoji: '☂️'
    }
  ],
  notifications: [
    { id: 1, text: '你的「黑色 AirPods Pro」有新的可能匹配項目。', unread: true },
    { id: 2, text: '管理學院附近新增一筆學生證拾獲通報。', unread: true },
    { id: 3, text: '系統已完成今日自動媒合更新。', unread: true }
  ]
};

const views = document.querySelectorAll('.view');
const navItems = document.querySelectorAll('.nav-item');
const titleMap = {
  dashboard: ['產品原型總覽'],
  lost: ['遺失物管理', '查看遺失通報、搜尋與篩選。'],
  found: ['拾獲物管理', '查看拾獲通報與待認領物品。'],
  publish: ['發布物品', '模擬使用者新增失物 / 拾獲資料。'],
  matching: ['智慧媒合', '自動比對遺失與拾獲紀錄。'],
  notifications: ['通知中心', '集中顯示媒合提醒與系統通知。']
};

function switchView(viewId) {
  views.forEach(v => v.classList.toggle('active', v.id === viewId));
  navItems.forEach(btn => btn.classList.toggle('active', btn.dataset.view === viewId));
  document.getElementById('view-title').textContent = titleMap[viewId][0];
  document.getElementById('view-subtitle').textContent = titleMap[viewId][1];
}

navItems.forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
document.querySelectorAll('[data-jump]').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.jump)));
document.getElementById('quickPublishBtn').addEventListener('click', () => switchView('publish'));

function formatTime(value) {
  return new Date(value).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function typeLabel(type) {
  return type === 'lost' ? '遺失物' : '拾獲物';
}

function itemCard(item) {
  return `
    <article class="item-card">
      <div class="emoji-box">${item.emoji}</div>
      <div class="item-content">
        <div class="item-title-row">
          <h4>${item.title}</h4>
          <span class="tag ${item.type}">${typeLabel(item.type)}</span>
        </div>
        <div class="item-meta">${item.category} ・ ${item.location} ・ ${formatTime(item.datetime)}</div>
        <p>${item.description}</p>
        <div class="item-meta">聯絡方式：${item.contact}</div>
      </div>
    </article>
  `;
}

function renderLists() {
  const lostFilter = document.getElementById('lostCategoryFilter').value;
  const foundFilter = document.getElementById('foundCategoryFilter').value;
  const keyword = document.getElementById('globalSearch').value.trim().toLowerCase();

  const matchesKeyword = (item) => {
    if (!keyword) return true;
    return [item.title, item.location, item.description, item.category].join(' ').toLowerCase().includes(keyword);
  };

  const lostItems = state.items.filter(i => i.type === 'lost' && (lostFilter === 'all' || i.category === lostFilter) && matchesKeyword(i));
  const foundItems = state.items.filter(i => i.type === 'found' && (foundFilter === 'all' || i.category === foundFilter) && matchesKeyword(i));

  document.getElementById('lostList').innerHTML = lostItems.map(itemCard).join('') || '<div class="panel">查無資料</div>';
  document.getElementById('foundList').innerHTML = foundItems.map(itemCard).join('') || '<div class="panel">查無資料</div>';

  const recent = [...state.items].sort((a, b) => new Date(b.datetime) - new Date(a.datetime)).slice(0, 5);
  document.getElementById('recentFeed').innerHTML = recent.map(item => `
    <div class="feed-item">
      <div class="feed-head">
        <strong>${item.title}</strong>
        <span class="tag ${item.type}">${typeLabel(item.type)}</span>
      </div>
      <div class="feed-meta">${item.location} ・ ${formatTime(item.datetime)}</div>
    </div>
  `).join('');

  document.getElementById('lostCount').textContent = state.items.filter(i => i.type === 'lost').length;
  document.getElementById('foundCount').textContent = state.items.filter(i => i.type === 'found').length;
  document.getElementById('metric-total').textContent = state.items.length;
}

function similarityScore(a, b) {
  let score = 0;
  const reasons = [];

  if (a.category === b.category) {
    score += 35;
    reasons.push('類型相符');
  }

  const locA = a.location.toLowerCase();
  const locB = b.location.toLowerCase();
  if (locA.includes(locB.slice(0, 2)) || locB.includes(locA.slice(0, 2))) {
    score += 20;
    reasons.push('地點接近');
  }

  const timeDiff = Math.abs(new Date(a.datetime) - new Date(b.datetime)) / (1000 * 60 * 60);
  if (timeDiff <= 4) {
    score += 20;
    reasons.push('時間接近');
  } else if (timeDiff <= 24) {
    score += 10;
    reasons.push('時間合理');
  }

  const keywordsA = (a.title + ' ' + a.description).toLowerCase();
  const keywordsB = (b.title + ' ' + b.description).toLowerCase();
  const shared = ['airpods', '黑色', '學生證', '水壺', '雨傘', '貼紙', '背包'].filter(k => keywordsA.includes(k) && keywordsB.includes(k));
  if (shared.length) {
    score += Math.min(25, shared.length * 8);
    reasons.push(`關鍵字相似：${shared.join('、')}`);
  }

  return { score: Math.min(score, 99), reasons };
}

function buildMatches() {
  const lost = state.items.filter(i => i.type === 'lost');
  const found = state.items.filter(i => i.type === 'found');
  const result = [];

  lost.forEach(l => {
    found.forEach(f => {
      const match = similarityScore(l, f);
      if (match.score >= 45) {
        result.push({ lost: l, found: f, ...match });
      }
    });
  });

  return result.sort((a, b) => b.score - a.score);
}

function renderMatches() {
  const matches = buildMatches();
  document.getElementById('matchCount').textContent = matches.length;
  document.getElementById('metric-match').textContent = matches.length;

  const html = matches.map(match => `
    <div class="match-item">
      <div class="match-head">
        <strong>${match.lost.title}</strong>
        <span class="score">${match.score}% Match</span>
      </div>
      <div class="feed-meta">遺失：${match.lost.location} ・ 拾獲：${match.found.location}</div>
      <div class="feed-meta">可能對應拾獲物：${match.found.title}</div>
      <ul class="match-reasons">
        ${match.reasons.map(r => `<li>${r}</li>`).join('')}
      </ul>
    </div>
  `).join('');

  document.getElementById('matchingList').innerHTML = html || '<div class="feed-item">目前沒有可顯示的媒合結果。</div>';
  document.getElementById('topMatches').innerHTML = matches.slice(0, 3).map(match => `
    <div class="match-item">
      <div class="match-head">
        <strong>${match.lost.title}</strong>
        <span class="score">${match.score}%</span>
      </div>
      <div class="feed-meta">${match.found.title} ・ ${match.found.location}</div>
    </div>
  `).join('') || '<div class="feed-item">暫無媒合</div>';
}

function renderNotifications() {
  document.getElementById('notificationCount').textContent = state.notifications.filter(n => n.unread).length;
  document.getElementById('notificationList').innerHTML = state.notifications.map(n => `
    <div class="notify-item ${n.unread ? 'unread' : 'read'}">
      <strong>${n.unread ? '新通知' : '已讀通知'}</strong>
      <div class="notify-meta">${n.text}</div>
    </div>
  `).join('');
}

function updatePreview(formData) {
  const preview = document.getElementById('previewCard');
  preview.classList.remove('empty');
  preview.innerHTML = itemCard(formData);
}

const form = document.getElementById('publishForm');
form.addEventListener('input', () => {
  const formData = Object.fromEntries(new FormData(form).entries());
  if (formData.title && formData.location && formData.description) updatePreview(formData);
});

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const formData = Object.fromEntries(new FormData(form).entries());
  const newItem = { ...formData, id: Date.now() };
  state.items.unshift(newItem);
  state.notifications.unshift({
    id: Date.now() + 1,
    text: `已新增一筆${newItem.type === 'lost' ? '遺失' : '拾獲'}通報：「${newItem.title}」。系統已開始媒合。`,
    unread: true
  });
  renderAll();
  updatePreview(newItem);
  form.reset();
  switchView('matching');
});

document.getElementById('fillDemoBtn').addEventListener('click', () => {
  form.type.value = 'lost';
  form.title.value = '黑色皮夾';
  form.category.value = '配件';
  form.location.value = '小福 2F';
  form.datetime.value = '2026-03-23T13:30';
  form.contact.value = 'demo@ntu.edu.tw';
  form.description.value = '黑色短夾，裡面有學生證與悠遊卡。';
  form.emoji.value = '🎒';
  updatePreview(Object.fromEntries(new FormData(form).entries()));
});

document.getElementById('markAllReadBtn').addEventListener('click', () => {
  state.notifications = state.notifications.map(n => ({ ...n, unread: false }));
  renderNotifications();
});

document.getElementById('lostCategoryFilter').addEventListener('change', renderLists);
document.getElementById('foundCategoryFilter').addEventListener('change', renderLists);
document.getElementById('globalSearch').addEventListener('input', renderLists);

function renderAll() {
  renderLists();
  renderMatches();
  renderNotifications();
}

renderAll();
