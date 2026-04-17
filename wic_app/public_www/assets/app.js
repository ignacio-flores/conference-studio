const state = {
  payload: null,
  view: 'programme',
  activeDay: '',
  expandedSessionId: '',
  pinnedAbstractId: '',
  hoveredAbstractId: '',
  paperQuery: '',
};

async function loadProgramme() {
  const response = await fetch('data/programme.json');
  if (!response.ok) {
    throw new Error(`Unable to load programme.json (${response.status})`);
  }
  return response.json();
}

function byId(id) {
  return document.getElementById(id);
}

function sortByDay(a, b) {
  return (a.day_num || 0) - (b.day_num || 0) || String(a.day_label || '').localeCompare(String(b.day_label || ''));
}

function setTitle(conference) {
  byId('site-title').textContent = conference?.title || 'Conference Programme';
  byId('site-subtitle').textContent = conference?.subtitle || '';
  byId('generated-at').textContent = conference?.generated_at ? `Updated: ${conference.generated_at}` : '';
}

function uniqueDays(payload) {
  return [...(payload?.filters?.days || [])]
    .map((day) => {
      const match = payload.sessions.find((session) => session.day_label === day) || {};
      return { day_label: day, day_num: match.day_num || 0 };
    })
    .sort(sortByDay);
}

function setView(view) {
  state.view = view;
  document.querySelectorAll('.nav-link').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.view === view);
  });
  byId('programme-view').hidden = view !== 'programme';
  byId('papers-view').hidden = view !== 'papers';
}

function renderDaySwitcher() {
  const host = byId('day-switcher');
  const days = uniqueDays(state.payload);
  host.innerHTML = '';

  days.forEach((day) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `day-pill${day.day_label === state.activeDay ? ' is-active' : ''}`;
    button.textContent = day.day_label;
    button.addEventListener('click', () => {
      state.activeDay = day.day_label;
      state.expandedSessionId = '';
      state.pinnedAbstractId = '';
      state.hoveredAbstractId = '';
      renderDaySwitcher();
      renderProgramme();
    });
    host.appendChild(button);
  });
}

function groupSessionsForDay(dayLabel) {
  const sessions = (state.payload?.sessions || []).filter((session) => session.day_label === dayLabel);
  const grouped = new Map();

  sessions.forEach((session) => {
    const key = `${session.block_num}|${session.start_min}|${session.block_label}|${session.time}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        block_num: session.block_num,
        start_min: session.start_min,
        block_label: session.block_label,
        time: session.time,
        sessions: [],
      });
    }
    grouped.get(key).sessions.push(session);
  });

  return [...grouped.values()].sort((a, b) => (a.start_min || 0) - (b.start_min || 0));
}

function getActiveAbstractId() {
  return state.pinnedAbstractId || state.hoveredAbstractId;
}

function toggleSession(sessionId) {
  state.expandedSessionId = state.expandedSessionId === sessionId ? '' : sessionId;
  state.pinnedAbstractId = '';
  state.hoveredAbstractId = '';
  renderProgramme();
}

function toggleAbstract(submissionId) {
  state.pinnedAbstractId = state.pinnedAbstractId === submissionId ? '' : submissionId;
  renderProgramme();
}

function renderTalk(talk) {
  const template = byId('talk-row-template');
  const fragment = template.content.cloneNode(true);
  const row = fragment.querySelector('.talk-row');
  const toggle = fragment.querySelector('.talk-toggle');
  const title = fragment.querySelector('.talk-title');
  const authors = fragment.querySelector('.talk-authors');
  const abstractPanel = fragment.querySelector('.abstract-panel');
  const isActive = getActiveAbstractId() === talk.submission_id;

  title.textContent = talk.title;
  authors.textContent = talk.authors;
  row.classList.toggle('is-expanded', isActive);
  abstractPanel.hidden = !isActive;
  abstractPanel.textContent = talk.abstract || 'Abstract not available.';

  toggle.addEventListener('click', () => toggleAbstract(talk.submission_id));
  row.addEventListener('mouseover', () => {
    if (window.matchMedia('(hover: hover)').matches) {
      state.hoveredAbstractId = talk.submission_id;
      row.classList.add('is-hovering');
      renderProgramme();
    }
  });
  row.addEventListener('mouseleave', () => {
    if (window.matchMedia('(hover: hover)').matches && !state.pinnedAbstractId) {
      state.hoveredAbstractId = '';
      renderProgramme();
    }
  });
  return fragment;
}

function renderSession(session) {
  const template = byId('session-detail-template');
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector('.session-card');
  const summary = fragment.querySelector('.session-summary');
  const room = fragment.querySelector('.session-room');
  const time = fragment.querySelector('.session-time');
  const title = fragment.querySelector('.session-title');
  const meta = fragment.querySelector('.session-meta');
  const detail = fragment.querySelector('.session-detail');
  const expanded = state.expandedSessionId === session.session_id;

  card.classList.toggle('is-expanded', expanded);
  room.textContent = session.room;
  time.textContent = session.time;
  title.textContent = session.session_title;
  meta.textContent = `${session.block_label} · ${session.talks.length} talk${session.talks.length === 1 ? '' : 's'}`;
  summary.addEventListener('click', () => toggleSession(session.session_id));
  detail.hidden = !expanded;

  if (expanded) {
    session.talks.forEach((talk) => detail.appendChild(renderTalk(talk)));
  }

  return fragment;
}

function renderProgramme() {
  const host = byId('programme-view');
  const blocks = groupSessionsForDay(state.activeDay);
  host.innerHTML = '';

  if (!blocks.length) {
    host.innerHTML = '<p class="empty-state">No sessions available for this day.</p>';
    return;
  }

  blocks.forEach((block) => {
    const section = document.createElement('section');
    section.className = 'programme-block';
    section.innerHTML = `
      <header class="programme-block-header">
        <div>
          <p class="programme-block-label">${block.block_label}</p>
          <h2 class="programme-block-time">${block.time}</h2>
        </div>
      </header>
      <div class="programme-block-grid"></div>
    `;

    const grid = section.querySelector('.programme-block-grid');
    block.sessions
      .slice()
      .sort((a, b) => String(a.room || '').localeCompare(String(b.room || '')))
      .forEach((session) => grid.appendChild(renderSession(session)));
    host.appendChild(section);
  });
}

function renderPapers() {
  const host = byId('papers-results');
  const query = state.paperQuery.trim().toLowerCase();
  const papers = (state.payload?.papers || []).filter((paper) => {
    if (!query) return true;
    const haystack = `${paper.title} ${paper.authors} ${paper.session_title}`.toLowerCase();
    return haystack.includes(query);
  });

  host.innerHTML = '';
  if (!papers.length) {
    host.innerHTML = '<p class="empty-state">No papers match the current search.</p>';
    return;
  }

  papers.forEach((paper) => {
    const row = document.createElement('article');
    row.className = 'paper-row';
    row.innerHTML = `
      <div class="paper-row-meta">
        <span>${paper.day_label}</span>
        <span>${paper.time} · ${paper.room}</span>
      </div>
      <h3 class="paper-row-title">${paper.title}</h3>
      <p class="session-meta">${paper.authors}</p>
      <p class="session-meta">${paper.session_title}</p>
    `;
    row.addEventListener('click', () => {
      state.activeDay = paper.day_label;
      state.expandedSessionId = paper.session_id;
      state.pinnedAbstractId = paper.submission_id;
      state.hoveredAbstractId = '';
      setView('programme');
      renderDaySwitcher();
      renderProgramme();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    host.appendChild(row);
  });
}

function wireControls() {
  document.querySelectorAll('.nav-link').forEach((button) => {
    button.addEventListener('click', () => {
      setView(button.dataset.view);
    });
  });

  byId('paper-search').addEventListener('input', (event) => {
    state.paperQuery = event.target.value || '';
    renderPapers();
  });
}

async function boot() {
  state.payload = await loadProgramme();
  const days = uniqueDays(state.payload);
  state.activeDay = days[0]?.day_label || '';
  setTitle(state.payload.conference || {});
  wireControls();
  renderDaySwitcher();
  renderProgramme();
  renderPapers();
}

window.addEventListener('DOMContentLoaded', boot);
