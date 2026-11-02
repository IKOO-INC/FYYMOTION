// FYY MOTION Portal - JS ringan
document.addEventListener('DOMContentLoaded', function () {
  // Sidebar mobile
  var sidebar = document.getElementById('sidebar');
  var backdrop = document.getElementById('sidebarBackdrop');
  var btn = document.getElementById('btnSidebar');
  function toggle(show) {
    if (!sidebar) return;
    sidebar.classList.toggle('show', show);
    backdrop && backdrop.classList.toggle('show', show);
  }
  btn && btn.addEventListener('click', function () { toggle(!sidebar.classList.contains('show')); });
  backdrop && backdrop.addEventListener('click', function () { toggle(false); });

  // Tombol salin (copy) teks pesanan / WA / JSON
  document.querySelectorAll('.btn-copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var target = document.querySelector(b.getAttribute('data-copy-target'));
      var text = b.getAttribute('data-copy-text') || (target ? (target.value || target.innerText) : '');
      navigator.clipboard.writeText(text).then(function () {
        var old = b.innerHTML;
        b.innerHTML = '<i class="bi bi-check-lg"></i> Tersalin!';
        setTimeout(function () { b.innerHTML = old; }, 1600);
      }).catch(function () {
        if (target && target.select) { target.focus(); target.select(); document.execCommand('copy'); }
      });
    });
  });

  // Preset Jurnal pada form transaksi: pilih jenis -> akun Debit/Kredit terisi otomatis
  var jenis = document.getElementById('jenisTransaksi');
  var dSel = document.getElementById('akunDebit');
  var kSel = document.getElementById('akunKredit');
  if (jenis && dSel && kSel && window.JENIS_PRESET) {
    jenis.addEventListener('change', function () {
      var p = window.JENIS_PRESET[jenis.value];
      if (p && p[0]) dSel.value = p[0];
      if (p && p[1]) kSel.value = p[1];
    });
  }

  // Pratinjau format Rupiah di bawah input angka
  document.querySelectorAll('.rupiah-input').forEach(function (input) {
    var hint = input.parentElement.querySelector('.rupiah-hint');
    function render() {
      if (!hint) return;
      var n = parseInt((input.value || '').replace(/[^0-9-]/g, ''), 10);
      hint.textContent = isNaN(n) ? '' : '= Rp' + n.toLocaleString('id-ID');
    }
    input.addEventListener('input', render);
    render();
  });

  // Otomatis hitung sisa bayar pada form order
  var harga = document.getElementById('harga'), dp = document.getElementById('dp'), sisa = document.getElementById('sisaBayar');
  function hitungSisa() {
    if (!harga || !dp || !sisa) return;
    var v = (parseInt(harga.value, 10) || 0) - (parseInt(dp.value, 10) || 0);
    sisa.value = Math.max(v, 0);
  }
  harga && harga.addEventListener('input', hitungSisa);
  dp && dp.addEventListener('input', hitungSisa);
  hitungSisa();
});
