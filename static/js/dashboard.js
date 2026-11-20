document.addEventListener('DOMContentLoaded', () => {
  const csrfToken = document.body.dataset.csrf || '';

  document.querySelectorAll('.emoji-avatar[data-tint]').forEach((el) => {
    el.style.setProperty('--avatar-tint', el.dataset.tint);
  });

  document.querySelectorAll('.js-confirm-form').forEach((form) => {
    if (form.dataset.confirmBound === 'true') return;
    form.dataset.confirmBound = 'true';
    form.addEventListener('submit', (e) => {
      const msg = form.dataset.confirm || 'Вы уверены?';
      if (!confirm(msg)) {
        e.preventDefault();
      }
    });
  });

  const searchInput = document.getElementById('searchInput');
  const clearBtn = document.getElementById('clearBtn');

  if (searchInput && clearBtn) {
    const syncSearchState = () => {
      const hasText = searchInput.value.length > 0;
      clearBtn.classList.toggle('is-visible', hasText);
      searchInput.closest('.search-box')?.classList.toggle('has-value', hasText);
    };

    syncSearchState();

    searchInput.addEventListener('input', () => {
      syncSearchState();
      applyFilters();
    });

    clearBtn.addEventListener('click', () => {
      searchInput.value = '';
      syncSearchState();
      applyFilters();
      searchInput.focus();
    });
  }

  const msgSearchInput = document.getElementById('msgSearchInput');
  const msgSortSelect = document.getElementById('msgSortSelect');

  if (msgSearchInput) {
    msgSearchInput.addEventListener('input', filterAndSortMessages);
  }
  if (msgSortSelect) {
    msgSortSelect.addEventListener('change', filterAndSortMessages);
  }

  ['monthSelect', 'statusSelect', 'typeSelect', 'sortSelect'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', applyFilters);
  });

  document.querySelectorAll('[data-open-modal]').forEach((btn) => {
    btn.addEventListener('click', () => openModal(btn.dataset.openModal));
  });

  document.querySelectorAll('[data-close-modal]').forEach((btn) => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });

  document.querySelectorAll('.modal-backdrop').forEach((backdrop) => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        backdrop.classList.remove('open');
        if (!document.querySelector('.modal-backdrop.open')) {
          document.body.classList.remove('modal-open');
        }
      }
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const openModals = document.querySelectorAll('.modal-backdrop.open');
      const topModal = openModals[openModals.length - 1];
      if (topModal && topModal.id) {
        closeModal(topModal.id);
      }
    }
  });

  document.querySelectorAll('.js-toggle-status').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (btn.disabled) return;
      const id = btn.dataset.id;
      if (!id) return;

      btn.disabled = true;
      try {
        const res = await fetch(`/admin/toggle/${encodeURIComponent(id)}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRF-Token': csrfToken,
          },
          body: '_csrf_token=' + encodeURIComponent(csrfToken),
        });

        if (res.ok) {
          const row = btn.closest('tr');
          if (row) {
            const isCurrentlyActive = row.getAttribute('data-active') === '1';
            const nextActive = isCurrentlyActive ? '0' : '1';
            row.setAttribute('data-active', nextActive);
            btn.className = isCurrentlyActive ? 'status-btn status-off' : 'status-btn status-on';
            btn.textContent = isCurrentlyActive ? '○ Скрыт' : '● Активен';
            syncStatusCounts(isCurrentlyActive ? -1 : 1);
            applyFilters();
          }
        }
      } catch (_) {
        // Игнорируем сетевую ошибку при фоновом переключении
      } finally {
        btn.disabled = false;
      }
    });
  });

  document.querySelectorAll('.js-edit-msg').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const textEl = document.getElementById(`msg-text-${id}`);
      const currentText = textEl ? textEl.textContent : (btn.dataset.text || '');
      startEditMessage(id, currentText);
    });
  });

  const cancelEditBtn = document.getElementById('messageFormCancel');
  if (cancelEditBtn) {
    cancelEditBtn.addEventListener('click', cancelEditMessage);
  }

  const msgForm = document.getElementById('messageForm');
  if (msgForm) {
    msgForm.addEventListener('submit', async (e) => {
      const actionUrl = msgForm.getAttribute('action') || '';
      const isAddAction = actionUrl.endsWith('/admin/messages/add');
      const editMatch = actionUrl.match(/\/admin\/messages\/edit\/(\d+)$/);

      if (!isAddAction && !editMatch) return;

      e.preventDefault();
      if (msgForm.dataset.submitting === 'true') return;

      const input = document.getElementById('messageInputText');
      const submitBtn = document.getElementById('messageFormBtn');
      const text = input?.value.trim();
      if (!text) return;

      msgForm.dataset.submitting = 'true';
      if (submitBtn) submitBtn.disabled = true;

      try {
        const res = await fetch(actionUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRF-Token': csrfToken,
          },
          body: new URLSearchParams({
            text,
            _csrf_token: csrfToken,
          }).toString(),
        });

        if (!res.ok) {
          msgForm.dataset.submitting = 'false';
          if (submitBtn) submitBtn.disabled = false;
          msgForm.submit();
          return;
        }

        if (isAddAction) {
          let createdId = null;
          const contentType = res.headers.get('content-type') || '';
          if (contentType.includes('application/json')) {
            const payload = await res.json();
            createdId = payload.id ?? null;
          }
          appendMessageRow(createdId || Date.now(), text);
          input.value = '';
          updateMessagesCountLabel(1);
          filterAndSortMessages();
        } else if (editMatch) {
          const editedId = editMatch[1];
          const row = document.getElementById(`msg-item-${editedId}`);
          const textSpan = document.getElementById(`msg-text-${editedId}`);
          if (textSpan) textSpan.textContent = text;
          if (row) row.dataset.text = text.toLowerCase();
          cancelEditMessage();
          filterAndSortMessages();
        }
      } catch (_) {
        msgForm.dataset.submitting = 'false';
        if (submitBtn) submitBtn.disabled = false;
        msgForm.submit();
      } finally {
        msgForm.dataset.submitting = 'false';
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  document.querySelectorAll('.js-delete-msg-form').forEach((form) => {
    attachDeleteMessageHandler(form);
  });

  const csvInput = document.getElementById('csvFileInput');
  if (csvInput) {
    csvInput.addEventListener('change', function () {
      if (!this.files || this.files.length === 0) return;
      const file = this.files[0];
      if (!file.name.toLowerCase().endsWith('.csv')) {
        alert('Выберите файл в формате .csv');
        this.value = '';
        return;
      }
      if (confirm('ВНИМАНИЕ! Текущая база данных будет полностью заменена данными из файла. Продолжить?')) {
        this.form?.submit();
      } else {
        this.value = '';
      }
    });
  }

  document.querySelectorAll('#toastStack .toast-item').forEach((toast) => {
    if (toast.dataset.toastBound === 'true') return;
    toast.dataset.toastBound = 'true';

    const closeBtn = toast.querySelector('.toast-close');
    const hideToast = () => {
      toast.classList.add('is-hiding');
      setTimeout(() => toast.remove(), 300);
    };

    const timer = setTimeout(hideToast, 3500);

    closeBtn?.addEventListener('click', () => {
      clearTimeout(timer);
      hideToast();
    });
  });
});

function syncStatusCounts(activeDelta) {
  const activeEl = document.querySelector('.stats-strip [data-stat="active"] strong, .stats-strip [data-stat="active"]')
    || document.querySelectorAll('.stats-strip .stat-chip strong')[1];
  const inactiveEl = document.querySelector('.stats-strip [data-stat="inactive"] strong, .stats-strip [data-stat="inactive"]')
    || document.querySelectorAll('.stats-strip .stat-chip strong')[2];
  if (!activeEl || !inactiveEl) return;

  const curActive = parseInt(activeEl.textContent, 10) || 0;
  const curInactive = parseInt(inactiveEl.textContent, 10) || 0;
  activeEl.textContent = String(Math.max(0, curActive + activeDelta));
  inactiveEl.textContent = String(Math.max(0, curInactive - activeDelta));
}

function updateMessagesCountLabel(delta) {
  const label = document.querySelector('.section-label');
  if (!label) return;
  const match = label.textContent.match(/(\d+)/);
  if (!match) return;
  const nextCount = Math.max(0, parseInt(match[1], 10) + delta);
  label.textContent = label.textContent.replace(/\d+/, String(nextCount));
}

function attachDeleteMessageHandler(form) {
  if (form.dataset.deleteBound === 'true') return;
  form.dataset.deleteBound = 'true';

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (form.dataset.submitting === 'true') return;

    const confirmText = form.dataset.confirm || 'Удалить эту фразу из базы?';
    if (!confirm(confirmText)) return;

    const submitBtn = form.querySelector('button[type="submit"]');
    const row = form.closest('.msg-row');
    const token = csrfTokenFromBody();

    form.dataset.submitting = 'true';
    if (submitBtn) submitBtn.disabled = true;

    try {
      const res = await fetch(form.getAttribute('action'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRF-Token': token,
        },
        body: '_csrf_token=' + encodeURIComponent(token),
      });

      if (res.ok) {
        row?.remove();
        updateMessagesCountLabel(-1);
      } else {
        form.dataset.submitting = 'false';
        if (submitBtn) submitBtn.disabled = false;
        form.submit();
      }
    } catch (_) {
      form.dataset.submitting = 'false';
      if (submitBtn) submitBtn.disabled = false;
      form.submit();
    } finally {
      form.dataset.submitting = 'false';
      if (submitBtn) submitBtn.disabled = false;
    }
  });
}

function csrfTokenFromBody() {
  return document.body.dataset.csrf || '';
}

function appendMessageRow(id, text) {
  const container = document.getElementById('msgListContainer');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'msg-row';
  row.id = `msg-item-${id}`;
  row.dataset.id = String(id);
  row.dataset.text = text.toLowerCase();

  const span = document.createElement('span');
  span.id = `msg-text-${id}`;
  span.textContent = text;

  const actions = document.createElement('div');
  actions.className = 'msg-row-actions';

  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'icon-only-btn js-edit-msg';
  editBtn.dataset.id = String(id);
  editBtn.title = 'Редактировать';
  editBtn.textContent = '✏️';
  editBtn.addEventListener('click', () => {
    const latestText = document.getElementById(`msg-text-${id}`)?.textContent ?? text;
    startEditMessage(String(id), latestText);
  });

  const delForm = document.createElement('form');
  delForm.method = 'POST';
  delForm.action = `/admin/messages/delete/${encodeURIComponent(id)}`;
  delForm.className = 'm-0 js-delete-msg-form';
  delForm.dataset.confirm = 'Удалить эту фразу из базы?';

  const hiddenCsrf = document.createElement('input');
  hiddenCsrf.type = 'hidden';
  hiddenCsrf.name = '_csrf_token';
  hiddenCsrf.value = csrfTokenFromBody();

  const delBtn = document.createElement('button');
  delBtn.type = 'submit';
  delBtn.className = 'del-msg-btn';
  delBtn.title = 'Удалить';
  delBtn.textContent = '✕';

  delForm.appendChild(hiddenCsrf);
  delForm.appendChild(delBtn);
  attachDeleteMessageHandler(delForm);

  actions.appendChild(editBtn);
  actions.appendChild(delForm);
  row.appendChild(span);
  row.appendChild(actions);
  container.prepend(row);
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    const scrollBarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.documentElement.style.setProperty('--scrollbar-width', `${Math.max(0, scrollBarWidth)}px`);

    document.body.classList.add('modal-open');
    modal.classList.add('open');
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('open');
    if (!document.querySelector('.modal-backdrop.open')) {
      document.body.classList.remove('modal-open');
    }
  }
}

function formatLocalDateTimeInput(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toggleCustomTime(type) {
  const select = document.getElementById(type === 'promo' ? 'promoDurationSelect' : 'msgDurationSelect');
  const wrap = document.getElementById(type === 'promo' ? 'promoCustomTimeWrap' : 'msgCustomTimeWrap');
  if (!select || !wrap) return;

  if (select.value === 'custom') {
    wrap.classList.remove('hidden');
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const input = wrap.querySelector('input');
    if (input && !input.value) input.value = formatLocalDateTimeInput(tomorrow);
  } else {
    wrap.classList.add('hidden');
  }
}

function filterAndSortMessages() {
  const searchEl = document.getElementById('msgSearchInput');
  const sortEl = document.getElementById('msgSortSelect');
  const container = document.getElementById('msgListContainer');
  if (!searchEl || !sortEl || !container) return;

  const query = searchEl.value.toLowerCase().trim();
  const sortMode = sortEl.value;
  const rows = Array.from(container.querySelectorAll('.msg-row'));

  rows.forEach((row) => {
    const text = row.dataset.text || '';
    row.style.display = text.includes(query) ? '' : 'none';
  });

  rows.sort((a, b) => {
    const idA = parseInt(a.dataset.id, 10) || 0;
    const idB = parseInt(b.dataset.id, 10) || 0;
    const textA = a.dataset.text || '';
    const textB = b.dataset.text || '';

    if (sortMode === 'newest') {
      return idB - idA;
    }
    if (sortMode === 'oldest') {
      return idA - idB;
    }
    if (sortMode === 'alpha') {
      return textA.localeCompare(textB, 'ru');
    }
    return 0;
  });

  rows.forEach((row) => container.appendChild(row));
}

function startEditMessage(id, text) {
  const form = document.getElementById('messageForm');
  const input = document.getElementById('messageInputText');
  const btn = document.getElementById('messageFormBtn');
  const cancelBtn = document.getElementById('messageFormCancel');
  if (!form || !input || !btn || !cancelBtn) return;

  document.querySelectorAll('.msg-row.is-editing').forEach((el) => el.classList.remove('is-editing'));
  const currentRow = document.getElementById(`msg-item-${id}`);
  if (currentRow) currentRow.classList.add('is-editing');

  form.action = `/admin/messages/edit/${encodeURIComponent(id)}`;
  input.value = text;
  btn.textContent = '💾 Сохранить';
  btn.classList.add('is-editing-save');
  cancelBtn.classList.remove('hidden');
  input.focus();
}

function cancelEditMessage() {
  const form = document.getElementById('messageForm');
  const input = document.getElementById('messageInputText');
  const btn = document.getElementById('messageFormBtn');
  const cancelBtn = document.getElementById('messageFormCancel');
  if (!form || !input || !btn || !cancelBtn) return;

  document.querySelectorAll('.msg-row.is-editing').forEach((el) => el.classList.remove('is-editing'));

  form.action = '/admin/messages/add';
  input.value = '';
  btn.textContent = '+ В базу';
  btn.classList.remove('is-editing-save');
  cancelBtn.classList.add('hidden');
}

function applyFilters() {
  const month = document.getElementById('monthSelect')?.value ?? 'all';
  const status = document.getElementById('statusSelect')?.value ?? 'all';
  const type = document.getElementById('typeSelect')?.value ?? 'all';
  const sort = document.getElementById('sortSelect')?.value ?? '';
  const q = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();

  const tbody = document.getElementById('holidaysTableBody');
  if (!tbody) return;

  const rows = Array.from(tbody.querySelectorAll('.holiday-row'));

  rows.forEach((row) => {
    const m = row.getAttribute('data-month') ?? '';
    const st = row.getAttribute('data-active') ?? '';
    const tp = row.getAttribute('data-type') ?? '';
    const title = (row.querySelector('.h-title')?.textContent || '').toLowerCase();
    const desc = (row.querySelector('.h-desc')?.textContent || '').toLowerCase();

    let show = true;
    if (month !== 'all' && m !== month) show = false;
    if (status !== 'all' && st !== status) show = false;
    if (type !== 'all' && tp !== type) show = false;
    if (q && !title.includes(q) && !desc.includes(q)) show = false;

    row.style.display = show ? '' : 'none';
  });

  if (sort === 'date_asc' || sort === 'title_asc' || sort === 'status_desc') {
    rows.sort((a, b) => {
      if (sort === 'date_asc') {
        return (parseInt(a.getAttribute('data-day'), 10) || 0) - (parseInt(b.getAttribute('data-day'), 10) || 0);
      }
      if (sort === 'title_asc') {
        return (a.getAttribute('data-title') || '').localeCompare(b.getAttribute('data-title') || '', 'ru');
      }
      if (sort === 'status_desc') {
        return (parseInt(b.getAttribute('data-active'), 10) || 0) - (parseInt(a.getAttribute('data-active'), 10) || 0);
      }
      return 0;
    });

    rows.forEach((r) => tbody.appendChild(r));
  }
}