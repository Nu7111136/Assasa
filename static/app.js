const cnic = document.getElementById('cnic');
if (cnic) cnic.addEventListener('input', () => {
  const digits = cnic.value.replace(/\D/g, '').slice(0,13);
  cnic.value = digits.slice(0,5) + (digits.length > 5 ? '-' + digits.slice(5,12) : '') + (digits.length > 12 ? '-' + digits.slice(12) : '');
});
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
