'use strict';
(() => {
  const body = document.getElementById('hrows'), empty = document.getElementById('hempty');
  async function load() {
    try {
      const { items } = await api('/api/history');
      body.replaceChildren(); empty.hidden = items.length > 0;
      for (const h of items) body.append(el('tr', {},
        el('td', { textContent: fmtDate(h.created_at) }), el('td', { textContent: h.title }), el('td', { className: 'num', textContent: h.line_count }),
        el('td', { className: 'act' },
          el('a', { className: 'btn', href: '/?riwayat=' + h.id, textContent: 'Buka' }), ' ',
          el('button', { className: 'danger', textContent: 'Hapus', onclick: async () => {
            if (!confirm(`Hapus “${h.title}”?`)) return;
            try { await api('/api/history/' + h.id, { method: 'DELETE' }); load(); } catch (e) { toast(e.message, true); }
          } })));
    } catch (e) { toast(e.message, true); }
  }
  load();
})();
