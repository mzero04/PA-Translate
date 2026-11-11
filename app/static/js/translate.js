'use strict';
(() => {
  const src = document.getElementById('src'), out = document.getElementById('out'), count = document.getElementById('count');
  let seq = 0;

  const run = async () => {
    const mine = ++seq;
    if (!src.value.trim()) { out.value = ''; count.textContent = ''; return; }
    try {
      const { result } = await api('/api/translate', { method: 'POST', json: { text: src.value } });
      if (mine !== seq) return;
      out.value = result;
      count.textContent = `${src.value.split('\n').filter(l => l.trim()).length} baris`;
    } catch (e) { toast(e.message, true); }
  };
  const runSoon = debounce(run, 250);

  src.addEventListener('input', runSoon);
  // sinkronkan scroll agar baris sejajar
  let lock = false;
  const sync = (a, b) => a.addEventListener('scroll', () => {
    if (lock) return; lock = true; b.scrollTop = a.scrollTop; b.scrollLeft = a.scrollLeft; lock = false;
  });
  sync(src, out); sync(out, src);

  document.getElementById('btn-clear').onclick = () => { src.value = ''; run(); src.focus(); };
  document.getElementById('btn-sample').onclick = async () => {
    try { src.value = (await api('/api/sample')).text; run(); } catch (e) { toast(e.message, true); }
  };
  document.getElementById('btn-copy').onclick = () => out.value ? copyText(out.value) : toast('Belum ada hasil', true);
  document.getElementById('btn-xlsx').onclick = async () => {
    if (!src.value.trim()) return toast('Belum ada teks', true);
    try { download(await api('/api/export', { method: 'POST', json: { text: src.value }, blob: true }), 'translate-form.xlsx'); }
    catch (e) { toast(e.message, true); }
  };
  document.getElementById('btn-save').onclick = async () => {
    if (!src.value.trim()) return toast('Belum ada teks', true);
    const first = src.value.split('\n').find(l => l.trim()) || '';
    const title = prompt('Judul riwayat:', first.slice(0, 60));
    if (title === null) return;
    try { await api('/api/history', { method: 'POST', json: { text: src.value, title } }); toast('Tersimpan di Riwayat'); }
    catch (e) { toast(e.message, true); }
  };

  const hid = new URLSearchParams(location.search).get('riwayat');
  if (hid) api('/api/history/' + encodeURIComponent(hid)).then(h => { src.value = h.source; run(); }).catch(e => toast(e.message, true));
})();
