'use strict';
document.getElementById('pwform').addEventListener('submit', async e => {
  e.preventDefault();
  const f = e.target, d = Object.fromEntries(new FormData(f));
  if (d.new !== d.again) return toast('Password baru tidak sama', true);
  try { await api('/api/account/password', { method: 'POST', json: { current: d.current, new: d.new } }); f.reset(); toast('Password diganti'); }
  catch (err) { toast(err.message, true); }
});
