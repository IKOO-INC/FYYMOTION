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
        b.innerHTML = '<i class="fa-solid fa-check"></i> Tersalin!';
        setTimeout(function () { b.innerHTML = old; }, 1600);
      }).catch(function () {
        if (target && target.select) { target.focus(); target.select(); document.execCommand('copy'); }
      });
    });
  });

  // Animasi reveal ala landing agency: elemen naik halus saat masuk viewport.
  var revealTargets = document.querySelectorAll('[data-reveal], .card, .analytics-card, .stat-card');
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (revealTargets.length && 'IntersectionObserver' in window && !reduceMotion) {
    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var target = entry.target;
          target.classList.add('is-visible');
          window.setTimeout(function () {
            target.style.transitionDelay = '';
            target.classList.remove('reveal-init', 'is-visible');
          }, 950);
          revealObserver.unobserve(target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -36px 0px' });
    revealTargets.forEach(function (el, index) {
      el.classList.add('reveal-init');
      el.style.transitionDelay = Math.min((index % 5) * 55, 220) + 'ms';
      revealObserver.observe(el);
    });
  }

  // Navigasi publik mendapat bayangan setelah halaman mulai digulir.
  var publicNav = document.querySelector('.public-nav');
  function syncPublicNav() {
    if (publicNav) publicNav.classList.toggle('is-scrolled', window.scrollY > 18);
  }
  window.addEventListener('scroll', syncPublicNav, { passive: true });
  syncPublicNav();

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
