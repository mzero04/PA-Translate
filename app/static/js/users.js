'use strict';
(() => {
  const body = document.getElementById('urows'), dlg = document.getElementById('dlg'), form = document.getElementById('uform');
  let me = null, editId = null;

  function render(items) {
    body.replaceChildren();
    for (const u of items) body.append(el('tr', {},
      el('td', { textContent: u.username }), el('td', { textContent: u.full_name }), el('td', { textContent: u.role }),
      el('td', {}, el('span', { className: 'tag' + (u.is_active ? '' : ' off'), textContent: u.is_active ? 'aktif' : 'nonaktif' })),
      el('td', { textContent: fmtDate(u.last_login) }),
      el('td', { className: 'act' },
        el('button', { textContent: 'Ubah', onclick: () => open(u) }), ' ',
        el('button', { className: 'danger', textContent: 'Hapus', disabled: u.id === me, onclick: () => remove(u) }))));
  }
  const load = () => api('/api/users').then(d => { me = d.me; render(d.items); }).catch(e => toast(e.message, true));

  function open(u) {
    editId = u ? u.id : null;
    form.reset();
    document.getElementById('dlg-title').textContent = u ? 'Ubah pengguna' : 'Pengguna baru';
    form.username.value = u ? u.username : ''; form.username.disabled = !!u;
    form.full_name.value = u ? u.full_name : ''; form.role.value = u ? u.role : 'user';
    form.is_active.checked = u ? !!u.is_active : true; form.is_active.disabled = !!u && u.id === me;
    form.password.required = !u;
    document.getElementById('pw-note').textContent = u ? '(kosongkan bila tidak diganti)' : '(min. 8 karakter)';
    dlg.showModal();
  }
  async function remove(u) {
    if (!confirm(`Hapus pengguna “${u.username}” beserta riwayatnya?`)) return;
    try { render((await api('/api/users/' + u.id, { method: 'DELETE' })).items); toast('Pengguna dihapus'); } catch (e) { toast(e.message, true); }
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const payload = { full_name: form.full_name.value, role: form.role.value, is_active: form.is_active.checked };
    if (form.password.value) payload.password = form.password.value;
    try {
      let d;
      if (editId) d = await api('/api/users/' + editId, { method: 'PUT', json: payload });
      else d = await api('/api/users', { method: 'POST', json: { ...payload, username: form.username.value } });
      render(d.items); dlg.close(); toast('Tersimpan');
    } catch (err) { toast(err.message, true); }
  });
  document.getElementById('dlg-cancel').onclick = () => dlg.close();
  document.getElementById('btn-new').onclick = () => open(null);
  load();
})();
