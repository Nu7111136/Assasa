const cnic = document.getElementById('cnic');
if (cnic) cnic.addEventListener('input', () => {
  const digits = cnic.value.replace(/\D/g, '').slice(0,13);
  cnic.value = digits.slice(0,5) + (digits.length > 5 ? '-' + digits.slice(5,12) : '') + (digits.length > 12 ? '-' + digits.slice(12) : '');
  mark(cnic);
});

const phone = document.getElementById('phone');
if (phone) phone.addEventListener('input', () => {
  phone.value = phone.value.replace(/\D/g, '').slice(0, 11);
  mark(phone);
});

function mark(el) {
  const field = el.closest('.field');
  if (!field) return;
  if (!el.value) {
    field.classList.remove('ok', 'bad');
    return;
  }
  const ok = el.checkValidity();
  field.classList.toggle('ok', ok);
  field.classList.toggle('bad', !ok);
}

document.querySelectorAll('input,textarea').forEach((el) => {
  el.addEventListener('input', () => mark(el));
  el.addEventListener('blur', () => { if (el.value) mark(el); });
});

const password = document.getElementById('password');
const confirm = document.getElementById('confirm');
if (password && confirm) {
  const sync = () => {
    confirm.setCustomValidity(confirm.value && confirm.value !== password.value ? 'mismatch' : '');
    if (confirm.value) mark(confirm);
  };
  password.addEventListener('input', sync);
  confirm.addEventListener('input', sync);
}

document.querySelectorAll('[data-toggle]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = document.getElementById(btn.getAttribute('data-toggle'));
    if (!input) return;
    const hide = input.type === 'text';
    input.type = hide ? 'password' : 'text';
    btn.textContent = hide ? (btn.dataset.show || btn.textContent) : (btn.dataset.hide || btn.textContent);
  });
});

const back = document.getElementById('back-btn');
if (back) {
  back.addEventListener('click', (event) => {
    try {
      const ref = document.referrer;
      if (ref && new URL(ref).origin === location.origin && history.length > 1) {
        event.preventDefault();
        history.back();
      }
    } catch (err) {}
  });
}

document.querySelectorAll('[data-copy]').forEach((box) => {
  const btn = box.querySelector('.copy-btn');
  const src = box.querySelector('#jazz-number, bdi, strong');
  if (!btn || !src) return;
  btn.addEventListener('click', async () => {
    const text = (src.textContent || '').replace(/\s/g, '');
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      const helper = document.createElement('textarea');
      helper.value = text;
      document.body.appendChild(helper);
      helper.select();
      document.execCommand('copy');
      helper.remove();
    }
    const old = btn.textContent;
    btn.textContent = btn.dataset.copied || old;
    setTimeout(() => { btn.textContent = old; }, 1600);
  });
});

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
