'use strict';
(() => {
  const body = document.getElementById('crows');
  const rowsData = Array.from({ length: 12 }, () => ({ a: '', b: '' }));

  const joined = r => (r.a || r.b) ? `${r.a} ${r.b}` : '';

  function render() {
    body.replaceChildren();
    rowsData.forEach((r, i) => {
      const res = el('td', { className: 'res copy', title: 'Klik untuk menyalin', textContent: joined(r) });
      res.onclick = () => { if (joined(r)) copyText(joined(r)); };
      const mk = k => { const inp = el('input', { value: r[k], maxLength: 200, ariaLabel: k === 'a' ? 'Kata pertama' : 'Kata kedua' });
        inp.oninput = () => { r[k] = inp.value; res.textContent = joined(r); }; return el('td', {}, inp); };
      body.append(el('tr', {}, el('td', { className: 'num', textContent: i + 1 }), mk('a'), mk('b'), res));
    });
  }

  document.getElementById('btn-fill').onclick = () => { const v = document.getElementById('fill').value; rowsData.forEach(r => { r.a = v; }); render(); };
  document.getElementById('btn-add').onclick = () => { if (rowsData.length < 500) { rowsData.push({ a: '', b: '' }); render(); } };
  document.getElementById('btn-clear').onclick = () => { rowsData.forEach(r => { r.a = r.b = ''; }); render(); };
  document.getElementById('btn-copy').onclick = () => {
    const t = rowsData.map(joined).filter(Boolean).join('\n');
    t ? copyText(t) : toast('Belum ada hasil', true);
  };
  // tempel banyak baris dari Excel (dua kolom dipisah tab) ke kolom mana pun
  body.addEventListener('paste', e => {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!/[\t\n]/.test(text.trim())) return;
    e.preventDefault();
    const lines = text.replace(/\r/g, '').split('\n').filter((l, i, a) => l !== '' || i < a.length - 1);
    const start = Array.from(body.children).indexOf(e.target.closest('tr'));
    const col = e.target.closest('td').cellIndex === 2 ? 'b' : 'a';
    lines.forEach((l, k) => {
      while (rowsData.length <= start + k && rowsData.length < 500) rowsData.push({ a: '', b: '' });
      const r = rowsData[start + k]; if (!r) return;
      const [x, y] = l.split('\t');
      if (col === 'a') { r.a = x ?? ''; if (y !== undefined) r.b = y; } else r.b = x ?? '';
    });
    render();
  });
  render();
})();
