(function oneTrade() {
  const boxes = document.querySelectorAll('input[name="trade"][type="checkbox"]');
  if (!boxes.length) return;
  boxes.forEach((box) => {
    box.addEventListener('change', () => {
      if (!box.checked) return;
      boxes.forEach((other) => {
        if (other !== box) other.checked = false;
      });
    });
  });
})();

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

function digits6(el) {
  if (!el) return;
  el.addEventListener('input', () => {
    el.value = el.value.replace(/\D/g, '').slice(0, 6);
    mark(el);
  });
}
document.querySelectorAll('input.qty').forEach((el) => {
  el.addEventListener('input', () => {
    const raw = el.value.replace(/[^\d.]/g, '');
    const parts = raw.split('.');
    el.value = parts[0].slice(0, 9) + (parts.length > 1 ? '.' + parts.slice(1).join('').slice(0, 3) : '');
    mark(el);
  });
});
document.querySelectorAll('form.row-save').forEach((form) => {
  if (form.closest('.stock-table')) return;
  const id = form.id;
  const fields = id
    ? document.querySelectorAll(`[form="${id}"]`)
    : form.querySelectorAll('input,select');
  fields.forEach((el) => {
    const eventName = el.tagName === 'SELECT' ? 'change' : 'blur';
    el.addEventListener(eventName, () => {
      if (typeof form.requestSubmit === 'function') form.requestSubmit();
      else form.submit();
    });
  });
});

function asasaSound(kind) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = asasaSound.ctx || new Ctx();
    asasaSound.ctx = ctx;
    if (ctx.state === 'suspended') ctx.resume();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    if (kind === 'add') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.08);
      gain.gain.setValueAtTime(0.14, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc.start(now);
      osc.stop(now + 0.2);
    } else {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(196, now);
      osc.frequency.exponentialRampToValueAtTime(98, now + 0.16);
      gain.gain.setValueAtTime(0.18, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.24);
      osc.start(now);
      osc.stop(now + 0.24);
    }
  } catch (err) {}
}

(function stockSounds() {
  let pending = null;
  try {
    pending = sessionStorage.getItem('asasa-sound');
    if (pending) sessionStorage.removeItem('asasa-sound');
  } catch (err) {}
  function flush() {
    if (!pending) return;
    asasaSound(pending);
    pending = null;
  }
  flush();
  document.addEventListener('pointerdown', flush, { once: true });
  document.querySelectorAll('form.stock-add-btn').forEach((form) => {
    form.addEventListener('submit', () => {
      try { sessionStorage.setItem('asasa-sound', 'add'); } catch (err) {}
    });
  });
  document.querySelectorAll('form.nb-del-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const ask = form.getAttribute('data-ask') || '';
      if (ask && !window.confirm(ask)) {
        event.preventDefault();
        return;
      }
      try { sessionStorage.setItem('asasa-sound', 'del'); } catch (err) {}
    });
  });
})();

(function stockClock() {
  const box = document.querySelector('.stock-clock');
  if (!box) return;
  const tz = box.getAttribute('data-tz') || 'Asia/Karachi';
  const timeEl = box.querySelector('.stock-clock-time');
  const dateEl = box.querySelector('.stock-clock-date');
  const hourHand = box.querySelector('.watch-hour');
  const minHand = box.querySelector('.watch-min');
  const secHand = box.querySelector('.watch-sec');
  const locale = document.documentElement.lang === 'ur' ? 'ur-PK' : 'en-PK';
  const timeFmt = new Intl.DateTimeFormat(locale, {
    hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true, timeZone: tz,
  });
  const dateFmt = new Intl.DateTimeFormat(locale, {
    weekday: 'long', day: 'numeric', month: 'short', year: 'numeric', timeZone: tz,
  });
  const partsFmt = new Intl.DateTimeFormat('en-GB', {
    hour: 'numeric', minute: 'numeric', second: 'numeric', hour12: false, timeZone: tz,
    hourCycle: 'h23',
  });

  function tick() {
    const now = new Date();
    if (timeEl) {
      timeEl.textContent = timeFmt.format(now);
      timeEl.setAttribute('datetime', now.toISOString());
    }
    if (dateEl) dateEl.textContent = dateFmt.format(now);
    const bits = {};
    partsFmt.formatToParts(now).forEach((part) => {
      if (part.type === 'hour' || part.type === 'minute' || part.type === 'second') {
        bits[part.type] = parseInt(part.value, 10);
      }
    });
    const h = bits.hour || 0;
    const m = bits.minute || 0;
    const s = bits.second || 0;
    if (hourHand) hourHand.style.transform = 'rotate(' + (30 * (h % 12) + m * 0.5) + 'deg)';
    if (minHand) minHand.style.transform = 'rotate(' + (6 * m + s * 0.1) + 'deg)';
    if (secHand) secHand.style.transform = 'rotate(' + (6 * s) + 'deg)';
  }
  tick();
  window.setInterval(tick, 1000);
})();

(function stockGrid() {
  const table = document.querySelector('.stock-table');
  if (!table) return;

  function post(url, data) {
    const body = new FormData();
    Object.keys(data).forEach((key) => body.append(key, data[key]));
    return fetch(url, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' },
    }).then((res) => {
      const type = res.headers.get('content-type') || '';
      if (type.indexOf('application/json') !== -1) return res.json();
      if (res.redirected) {
        window.location.href = res.url;
        return null;
      }
      return { ok: false };
    });
  }

  function fields(tr) {
    const csrf = tr.querySelector('[name="csrf_token"]');
    const name = tr.querySelector('.cell-name');
    const unit = tr.querySelector('[name="unit"]');
    const price = tr.querySelector('.cell-price');
    return {
      csrf_token: csrf ? csrf.value : '',
      quiet: '1',
      name: name ? name.value : '',
      unit: unit ? unit.value : '',
      sell_rs: price ? price.value : '',
    };
  }

  function paint(tr, data) {
    if (!data || !data.ok) return;
    tr.classList.remove('is-ok', 'is-low', 'is-out');
    tr.classList.add('is-' + data.status);
    const qty = tr.querySelector('.cell-qty');
    if (qty) qty.textContent = data.qty;
    const minus = tr.querySelector('.step-btn.minus');
    if (minus) minus.disabled = data.status === 'out';
    const unit = tr.querySelector('[name="unit"]');
    if (unit && data.unit) unit.value = data.unit;
    const price = tr.querySelector('.cell-price');
    if (price && data.price != null) price.value = data.price;
  }

  table.querySelectorAll('.step-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const tr = form.closest('tr');
      const btn = form.querySelector('button');
      if (!tr || (btn && btn.disabled)) return;
      const data = fields(tr);
      data.qty = '1';
      post(form.getAttribute('action'), data).then((res) => paint(tr, res));
    });
  });

  table.querySelectorAll('.cell-name, .cell-price').forEach((input) => {
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        input.blur();
      }
    });
    input.addEventListener('blur', () => {
      const tr = input.closest('tr');
      const form = tr && tr.querySelector('form.row-save');
      if (!form) return;
      post(form.getAttribute('action'), fields(tr)).then((res) => paint(tr, res));
    });
  });
  table.querySelectorAll('.cell-price').forEach((el) => {
    el.addEventListener('input', () => {
      el.value = el.value.replace(/\D/g, '').slice(0, 7);
    });
  });
  table.querySelectorAll('.cell-unit').forEach((sel) => {
    sel.addEventListener('change', () => {
      const tr = sel.closest('tr');
      const form = tr && tr.querySelector('form.row-save');
      if (!form) return;
      post(form.getAttribute('action'), fields(tr)).then((res) => paint(tr, res));
    });
  });
  table.querySelectorAll('.row-del-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const ask = form.getAttribute('data-ask') || '';
      if (ask && !window.confirm(ask)) return;
      const tr = form.closest('tr');
      const csrf = form.querySelector('[name="csrf_token"]');
      post(form.getAttribute('action'), { csrf_token: csrf ? csrf.value : '', quiet: '1' }).then((res) => {
        if (!res || !res.ok || !tr) return;
        asasaSound('del');
        tr.remove();
      });
    });
  });
})();

(function toastOk() {
  document.querySelectorAll('.flash.ok').forEach((el) => {
    window.setTimeout(() => el.classList.add('is-gone'), 5600);
  });
})();

document.querySelectorAll('.qty-chip').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = document.getElementById('qty');
    if (!input) return;
    input.value = btn.getAttribute('data-qty');
    input.dispatchEvent(new Event('input'));
    mark(input);
  });
});

const password = document.getElementById('password');
const confirm = document.getElementById('confirm');
digits6(password);
digits6(confirm);
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

(function urduKeyboard() {
  const kb = document.getElementById('ur-kb');
  if (!kb || document.documentElement.lang !== 'ur') return;

  const LETTERS = [
    ['ق', 'و', 'ع', 'ر', 'ت', 'ے', 'ء', 'ی', 'ہ', 'پ'],
    ['ا', 'س', 'د', 'ف', 'گ', 'ھ', 'ج', 'ک', 'ل'],
    ['shift', 'ز', 'ش', 'چ', 'ط', 'ب', 'ن', 'م', 'back'],
    ['123', 'comma', 'space', 'dot', 'done'],
  ];
  const SHIFT = [
    ['آ', 'ؤ', 'ئ', 'ں', 'ڑ', 'ٹ', 'ڈ', 'ژ', 'ۃ'],
    ['ص', 'ض', 'ث', 'ظ', 'ة', 'ۂ', 'ۓ'],
    ['shift', 'ز', 'ش', 'چ', 'ط', 'ب', 'ن', 'م', 'back'],
    ['123', 'comma', 'space', 'dot', 'done'],
  ];
  const NUMS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['-', '/', ':', '،', '.', '(', ')', '؟', '!'],
    ['abc', 'space', 'back', 'done'],
  ];

  let layer = 'letters';
  let shifted = false;
  let active = null;

  function rows() {
    if (layer === 'nums') return NUMS;
    return shifted ? SHIFT : LETTERS;
  }

  function label(key) {
    if (key === 'shift') return shifted ? 'ا' : 'آ ں';
    if (key === 'back') return '⌫';
    if (key === 'space') return 'خالی جگہ';
    if (key === 'done') return 'ہو گیا';
    if (key === '123') return '123';
    if (key === 'abc') return 'ا ب';
    if (key === 'comma') return '،';
    if (key === 'dot') return '.';
    return key;
  }

  function paint() {
    kb.innerHTML = '';
    rows().forEach((row) => {
      const line = document.createElement('div');
      line.className = 'ur-kb-row';
      row.forEach((key) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = label(key);
        btn.dataset.key = key;
        if (['shift', 'back', '123', 'abc', 'done', 'space'].includes(key)) btn.classList.add('is-act');
        if (key === 'space') btn.classList.add('is-space');
        if (key === 'done') btn.classList.add('is-done');
        if (key === 'shift' && shifted) btn.classList.add('is-on');
        line.appendChild(btn);
      });
      kb.appendChild(line);
    });
  }

  function caret(el) {
    const start = el.selectionStart == null ? el.value.length : el.selectionStart;
    const end = el.selectionEnd == null ? el.value.length : el.selectionEnd;
    return [start, end];
  }

  function write(el, next, pos) {
    el.value = next;
    if (el.setSelectionRange) el.setSelectionRange(pos, pos);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function insert(ch) {
    if (!active) return;
    const [start, end] = caret(active);
    write(active, active.value.slice(0, start) + ch + active.value.slice(end), start + ch.length);
  }

  function backspace() {
    if (!active) return;
    const [start, end] = caret(active);
    if (start !== end) {
      write(active, active.value.slice(0, start) + active.value.slice(end), start);
      return;
    }
    if (start === 0) return;
    write(active, active.value.slice(0, start - 1) + active.value.slice(end), start - 1);
  }

  function open(el) {
    active = el;
    kb.hidden = false;
    document.body.classList.add('kb-open');
    paint();
    requestAnimationFrame(() => {
      document.body.style.setProperty('--kb-pad', kb.offsetHeight + 'px');
      const row = el.closest('tr');
      if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
  }

  function close() {
    kb.hidden = true;
    document.body.classList.remove('kb-open');
    document.body.style.removeProperty('--kb-pad');
    active = null;
    shifted = false;
    layer = 'letters';
  }

  paint();
  kb.addEventListener('pointerdown', (event) => event.preventDefault());
  kb.addEventListener('click', (event) => {
    const btn = event.target.closest('button');
    if (!btn) return;
    const key = btn.dataset.key;
    if (key === 'shift') {
      shifted = !shifted;
      layer = 'letters';
      paint();
      return;
    }
    if (key === '123') {
      layer = 'nums';
      shifted = false;
      paint();
      return;
    }
    if (key === 'abc') {
      layer = 'letters';
      paint();
      return;
    }
    if (key === 'back') {
      backspace();
      return;
    }
    if (key === 'done') {
      close();
      return;
    }
    insert(key === 'space' ? ' ' : key === 'comma' ? '،' : key === 'dot' ? '.' : key);
    if (shifted && layer === 'letters') {
      shifted = false;
      paint();
    }
  });

  document.addEventListener('focusin', (event) => {
    if (event.target.matches && event.target.matches('[data-kb="ur"]')) open(event.target);
    else if (!kb.contains(event.target)) close();
  });
  document.addEventListener('pointerdown', (event) => {
    if (event.target.closest && event.target.closest('[data-kb="ur"]')) {
      const field = event.target.closest('[data-kb="ur"]');
      if (kb.hidden) open(field);
      return;
    }
    if (kb.hidden) return;
    if (kb.contains(event.target)) return;
    const field = active;
    close();
    if (field && event.target !== field) {
      window.setTimeout(() => { if (document.activeElement === field) field.blur(); }, 0);
    }
  }, true);
})();
