'use strict';
(() => {
  const rows = document.getElementById('rows'), q = document.getElementById('q'), dcount = document.getElementById('dcount');
  const nRm = document.getElementById('n-rm'), nRp = document.getElementById('n-rp'), nPos = document.getElementById('n-pos');
  let items = [], editing = null;

  const save = async (fn) => { try { const d = await fn(); items = d.items; render(); return d; } catch (e) { toast(e.message, true); } };

  function render() {
    const term = q.value.trim().toLowerCase();
    const list = term ? items.filter(i => i.remove_text.toLowerCase().includes(term) || i.replace_text.toLowerCase().includes(term)) : items;
    dcount.textContent = term ? `${list.length} dari ${items.length}` : `${items.length} aturan`;
    rows.replaceChildren();
    if (!list.length) rows.append(el('tr', {}, el('td', { colSpan: 4, className: 'empty', textContent: 'Tidak ada data.' })));
    for (const it of list) {
      const tr = el('tr');
      if (editing === it.id) {
        const pos = el('input', { type: 'number', min: 1, value: it.position });
        const rm = el('input', { value: it.remove_text, maxLength: 200 });
        const rp = el('input', { value: it.replace_text, maxLength: 200 });
        const commit = () => save(() => api('/api/dictionary/' + it.id, { method: 'PUT', json: { remove_text: rm.value, replace_text: rp.value, position: parseInt(pos.value, 10) || it.position } })).then(d => { if (d) { editing = null; render(); } });
        [rm, rp, pos].forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { editing = null; render(); } }));
        tr.append(el('td', { className: 'num' }, pos), el('td', {}, rm), el('td', {}, rp),
          el('td', { className: 'act' }, el('button', { className: 'primary', textContent: 'Simpan', onclick: commit }), ' ',
            el('button', { textContent: 'Batal', onclick: () => { editing = null; render(); } })));
      } else {
        const canMove = !term;
        tr.append(el('td', { className: 'num', textContent: it.position }), el('td', { textContent: it.remove_text }), el('td', { textContent: it.replace_text }),
          el('td', { className: 'act' },
            el('button', { className: 'icon', textContent: '▲', title: 'Naikkan', disabled: !canMove || it.position === 1, onclick: () => save(() => api('/api/dictionary/' + it.id, { method: 'PUT', json: { position: it.position - 1 } })) }), ' ',
            el('button', { className: 'icon', textContent: '▼', title: 'Turunkan', disabled: !canMove || it.position === items.length, onclick: () => save(() => api('/api/dictionary/' + it.id, { method: 'PUT', json: { position: it.position + 1 } })) }), ' ',
            el('button', { textContent: 'Ubah', onclick: () => { editing = it.id; render(); } }), ' ',
            el('button', { className: 'danger', textContent: 'Hapus', onclick: () => { if (confirm(`Hapus aturan “${it.remove_text} → ${it.replace_text}”?`)) save(() => api('/api/dictionary/' + it.id, { method: 'DELETE' })); } })));
      }
      rows.append(tr);
    }
  }

  const add = async () => {
    const pos = parseInt(nPos.value, 10);
    const d = await save(() => api('/api/dictionary', { method: 'POST', json: { remove_text: nRm.value, replace_text: nRp.value, ...(pos ? { position: pos } : {}) } }));
    if (d) { nRm.value = nRp.value = nPos.value = ''; nRm.focus(); toast('Aturan ditambahkan'); }
  };
  document.getElementById('n-add').onclick = add;
  [nRm, nRp, nPos].forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') add(); }));
  q.addEventListener('input', render);

  const imp = document.getElementById('btn-import'), file = document.getElementById('file');
  if (imp) {
    imp.onclick = () => file.click();
    file.onchange = async () => {
      if (!file.files[0]) return;
      const replace = confirm('Ganti SELURUH kamus dengan isi file?\n\nOK = ganti semua\nBatal = tambahkan ke akhir kamus');
      const form = new FormData(); form.append('file', file.files[0]); form.append('mode', replace ? 'replace' : 'append');
      const d = await save(() => api('/api/dictionary/import', { method: 'POST', form }));
      if (d) toast(`${d.imported} aturan diimpor`);
      file.value = '';
    };
  }

  save(() => api('/api/dictionary'));
})();
