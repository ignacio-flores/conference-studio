const state = {
  payload: null,
  view: 'programme',
  activeDay: '',
  expandedSessionId: '',
  pinnedAbstractId: '',
  paperQuery: '',
  pendingProgrammeFocus: null,
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

function cleanText(value) {
  return String(value ?? '').trim();
}

function hasOwn(record, key) {
  return Boolean(record) && Object.prototype.hasOwnProperty.call(record, key);
}

function payloadSettings() {
  const settings = state.payload?.settings || state.payload?.public_settings;
  return settings && typeof settings === 'object' ? settings : {};
}

function normalizeDisplayMode(value) {
  return cleanText(value).toLowerCase() === 'public_safe' ? 'public_safe' : 'full';
}

function shouldShowRawRooms() {
  const settings = payloadSettings();
  if (typeof settings.show_room_numbers === 'boolean') {
    return settings.show_room_numbers;
  }
  if (typeof settings.show_rooms === 'boolean') {
    return settings.show_rooms;
  }
  return normalizeDisplayMode(settings.publish_display) !== 'public_safe';
}

function resolveRoomLabel(record) {
  if (hasOwn(record, 'display_room')) {
    return cleanText(record.display_room);
  }
  return shouldShowRawRooms() ? cleanText(record.room) : '';
}

function resolveRoomKey(record) {
  return cleanText(record.room) || cleanText(record.display_room) || cleanText(record.session_id);
}

function resolveRoomIndex(record) {
  const value = Number(record?.room_index || 0);
  return Number.isFinite(value) ? value : 0;
}

function resolvePresenterDisplay(record) {
  if (hasOwn(record, 'display_presenter')) {
    return cleanText(record.display_presenter);
  }
  if (hasOwn(record, 'presenter_display')) {
    return cleanText(record.presenter_display);
  }
  return cleanText(record.authors) || '[No presenter]';
}

function resolvePaperUrl(record) {
  return cleanText(record.paper_url);
}

function sortByDay(a, b) {
  return (a.day_num || 0) - (b.day_num || 0) || String(a.day_label || '').localeCompare(String(b.day_label || ''));
}

function sortBySessionPosition(a, b) {
  return (a.start_min || 0) - (b.start_min || 0)
    || resolveRoomIndex(a) - resolveRoomIndex(b)
    || resolveRoomLabel(a).localeCompare(resolveRoomLabel(b))
    || cleanText(a.room).localeCompare(cleanText(b.room))
    || cleanText(a.session_code).localeCompare(cleanText(b.session_code))
    || cleanText(a.session_title).localeCompare(cleanText(b.session_title));
}

function setTitle(conference) {
  byId('site-title').textContent = conference?.title || 'Conference Programme';
  byId('site-subtitle').textContent = conference?.subtitle || '';
  byId('generated-at').textContent = conference?.generated_at ? `Updated: ${conference.generated_at}` : '';
}

function uniqueDays(payload) {
  return [...(payload?.filters?.days || [])]
    .map((day) => {
      const match = (payload.sessions || []).find((session) => session.day_label === day) || {};
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
      state.pendingProgrammeFocus = null;
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

  return [...grouped.values()]
    .sort((a, b) => (a.start_min || 0) - (b.start_min || 0))
    .map((block) => ({ ...block, sessions: block.sessions.slice().sort(sortBySessionPosition) }));
}

function toggleSession(sessionId) {
  state.expandedSessionId = state.expandedSessionId === sessionId ? '' : sessionId;
  state.pinnedAbstractId = '';
  renderProgramme();
}

function toggleAbstract(submissionId) {
  state.pinnedAbstractId = state.pinnedAbstractId === submissionId ? '' : submissionId;
  renderProgramme();
}

function buildPaperTitleLink(url, text, className) {
  if (!url) {
    return null;
  }
  const link = document.createElement('a');
  link.className = className;
  link.href = url;
  link.target = '_blank';
  link.rel = 'noreferrer noopener';
  link.textContent = text;
  link.addEventListener('click', (event) => event.stopPropagation());
  link.addEventListener('keydown', (event) => event.stopPropagation());
  return link;
}

function renderTalk(talk) {
  const template = byId('talk-row-template');
  const fragment = template.content.cloneNode(true);
  const row = fragment.querySelector('.talk-row');
  const titleLink = fragment.querySelector('.talk-title-link');
  const titleText = fragment.querySelector('.talk-title-text');
  const authors = fragment.querySelector('.talk-authors');
  const abstractToggle = fragment.querySelector('.abstract-toggle');
  const abstractPanel = fragment.querySelector('.abstract-panel');
  const isActive = state.pinnedAbstractId === talk.submission_id;
  const paperUrl = resolvePaperUrl(talk);
  const paperTitle = cleanText(talk.title) || '[Untitled]';

  row.dataset.submissionId = cleanText(talk.submission_id);
  if (paperUrl) {
    titleLink.hidden = false;
    titleLink.replaceChildren();
    titleLink.textContent = paperTitle;
    titleLink.href = paperUrl;
    titleText.hidden = true;
  } else {
    titleText.textContent = paperTitle;
    titleText.hidden = false;
    titleLink.hidden = true;
  }
  authors.textContent = resolvePresenterDisplay(talk);
  row.classList.toggle('is-expanded', isActive);
  abstractPanel.hidden = !isActive;
  abstractPanel.textContent = cleanText(talk.abstract) || 'Abstract not available.';
  abstractToggle.textContent = isActive ? 'Hide abstract' : 'Show abstract';
  abstractToggle.setAttribute('aria-expanded', String(isActive));
  abstractToggle.addEventListener('click', () => toggleAbstract(talk.submission_id));
  return fragment;
}

function renderSession(session) {
  const template = byId('session-detail-template');
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector('.session-card');
  const summary = fragment.querySelector('.session-summary');
  const room = fragment.querySelector('.session-room');
  const title = fragment.querySelector('.session-title');
  const meta = fragment.querySelector('.session-meta');
  const detail = fragment.querySelector('.session-detail');
  const expanded = state.expandedSessionId === session.session_id;
  const talks = session.talks || [];
  const visibleRoom = resolveRoomLabel(session);
  const theme = cleanText(session.primary_theme);
  const metaParts = [theme, `${talks.length} talk${talks.length === 1 ? '' : 's'}`].filter(Boolean);

  card.dataset.sessionId = cleanText(session.session_id);
  card.classList.toggle('is-expanded', expanded);
  room.textContent = visibleRoom;
  room.hidden = !visibleRoom;
  title.textContent = cleanText(session.session_title) || '[Untitled session]';
  meta.textContent = metaParts.join(' · ') || cleanText(session.block_label);
  summary.setAttribute('aria-expanded', String(expanded));
  summary.addEventListener('click', () => toggleSession(session.session_id));
  detail.hidden = !expanded;

  if (expanded) {
    talks.forEach((talk) => detail.appendChild(renderTalk(talk)));
  }

  return fragment;
}

function roomsForBlocks(blocks) {
  const rooms = new Map();

  blocks.forEach((block) => {
    block.sessions.forEach((session) => {
      const key = resolveRoomKey(session);
      if (!key) {
        return;
      }
      const label = resolveRoomLabel(session);
      if (!rooms.has(key)) {
        rooms.set(key, { key, label });
        return;
      }
      if (!rooms.get(key).label && label) {
        rooms.get(key).label = label;
      }
    });
  });

  return [...rooms.values()].sort(
    (a, b) => {
      const aRecord = (state.payload?.sessions || []).find((session) => resolveRoomKey(session) === a.key) || {};
      const bRecord = (state.payload?.sessions || []).find((session) => resolveRoomKey(session) === b.key) || {};
      return resolveRoomIndex(aRecord) - resolveRoomIndex(bRecord)
        || (a.label || a.key).localeCompare(b.label || b.key)
        || a.key.localeCompare(b.key);
    },
  );
}

function groupSessionsByRoom(sessions) {
  const grouped = new Map();
  sessions.forEach((session) => {
    const key = resolveRoomKey(session) || cleanText(session.session_id);
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key).push(session);
  });
  return grouped;
}

function renderStructureBlock(block, rooms) {
  const section = document.createElement('section');
  const wrapper = document.createElement('div');
  const grid = document.createElement('div');
  const sessionsByRoom = groupSessionsByRoom(block.sessions);

  section.className = 'programme-block';
  section.innerHTML = `
    <header class="programme-block-header">
      <div>
        <p class="programme-block-label">${cleanText(block.block_label)}</p>
        <h2 class="programme-block-time">${cleanText(block.time)}</h2>
      </div>
    </header>
  `;

  wrapper.className = 'programme-room-grid-wrapper';
  grid.className = 'programme-room-grid';
  grid.style.gridTemplateColumns = `repeat(${rooms.length}, minmax(220px, 1fr))`;

  rooms.forEach((room) => {
    const header = document.createElement('div');
    header.className = 'programme-room-header';
    header.textContent = room.label;
    grid.appendChild(header);
  });

  rooms.forEach((room) => {
    const cell = document.createElement('div');
    const sessions = sessionsByRoom.get(room.key) || [];
    cell.className = 'programme-room-cell';

    if (!sessions.length) {
      cell.classList.add('is-empty');
      cell.innerHTML = '<p class="empty-room">No session</p>';
    } else {
      sessions.forEach((session) => cell.appendChild(renderSession(session)));
    }
    grid.appendChild(cell);
  });

  wrapper.appendChild(grid);
  section.appendChild(wrapper);
  return section;
}

function renderFallbackBlock(block) {
  const section = document.createElement('section');
  section.className = 'programme-block';
  section.innerHTML = `
    <header class="programme-block-header">
      <div>
        <p class="programme-block-label">${cleanText(block.block_label)}</p>
        <h2 class="programme-block-time">${cleanText(block.time)}</h2>
      </div>
    </header>
    <div class="programme-block-grid is-fallback"></div>
  `;

  const grid = section.querySelector('.programme-block-grid');
  block.sessions.forEach((session) => grid.appendChild(renderSession(session)));
  return section;
}

function findProgrammeNode(attribute, value) {
  if (!value) {
    return null;
  }
  return [...document.querySelectorAll(`[${attribute}]`)].find((node) => node.getAttribute(attribute) === value) || null;
}

function focusProgrammeLocation() {
  if (!state.pendingProgrammeFocus || state.view !== 'programme') {
    return;
  }
  const focus = state.pendingProgrammeFocus;
  state.pendingProgrammeFocus = null;

  window.requestAnimationFrame(() => {
    const target = findProgrammeNode('data-submission-id', focus.submissionId)
      || findProgrammeNode('data-session-id', focus.sessionId);
    if (!target) {
      return;
    }
    target.classList.add('is-focus-target');
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => target.classList.remove('is-focus-target'), 1800);
  });
}

function renderProgramme() {
  const host = byId('programme-view');
  const blocks = groupSessionsForDay(state.activeDay);
  const rooms = roomsForBlocks(blocks);
  const hasVisibleRooms = rooms.some((room) => room.label);
  host.innerHTML = '';

  if (!blocks.length) {
    host.innerHTML = '<p class="empty-state">No sessions available for this day.</p>';
    return;
  }

  blocks.forEach((block) => {
    host.appendChild(hasVisibleRooms ? renderStructureBlock(block, rooms) : renderFallbackBlock(block));
  });

  focusProgrammeLocation();
}

function navigateToPaper(paper) {
  state.activeDay = cleanText(paper.day_label);
  state.expandedSessionId = cleanText(paper.session_id);
  state.pinnedAbstractId = cleanText(paper.submission_id);
  state.pendingProgrammeFocus = {
    sessionId: cleanText(paper.session_id),
    submissionId: cleanText(paper.submission_id),
  };
  setView('programme');
  renderDaySwitcher();
  renderProgramme();
}

function paperMatchesQuery(paper, query) {
  if (!query) {
    return true;
  }
  const haystack = [
    cleanText(paper.title),
    cleanText(paper.authors),
    resolvePresenterDisplay(paper),
    cleanText(paper.session_title),
    resolveRoomLabel(paper),
    cleanText(paper.day_label),
  ].join(' ').toLowerCase();
  return haystack.includes(query);
}

function renderPapers() {
  const host = byId('papers-results');
  const query = state.paperQuery.trim().toLowerCase();
  const papers = (state.payload?.papers || []).filter((paper) => paperMatchesQuery(paper, query));

  host.innerHTML = '';
  if (!papers.length) {
    host.innerHTML = '<p class="empty-state">No papers match the current search.</p>';
    return;
  }

  papers.forEach((paper) => {
    const row = document.createElement('article');
    const presenter = resolvePresenterDisplay(paper);
    const paperUrl = resolvePaperUrl(paper);
    const paperTitle = cleanText(paper.title) || '[Untitled]';
    const titleHeading = document.createElement('h3');
    const titleLink = buildPaperTitleLink(paperUrl, paperTitle, 'paper-row-title paper-row-title-link');

    row.className = 'paper-row';
    row.tabIndex = 0;
    row.setAttribute('role', 'button');
    row.innerHTML = `
      <div class="paper-row-meta">
        <span>${cleanText(paper.day_label)}</span>
        <span>${cleanText(paper.time)}</span>
      </div>
      <p class="session-meta">${presenter}</p>
      <p class="session-meta">${cleanText(paper.session_title)}</p>
    `;

    titleHeading.className = 'paper-row-title';
    if (titleLink) {
      titleHeading.appendChild(titleLink);
    } else {
      titleHeading.textContent = paperTitle;
    }
    row.insertBefore(titleHeading, row.querySelector('.session-meta'));

    row.addEventListener('click', () => navigateToPaper(paper));
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        navigateToPaper(paper);
      }
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
