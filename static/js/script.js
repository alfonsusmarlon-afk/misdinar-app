/**
 * MISDINAR — script.js
 * Berisi semua logika JavaScript untuk interaktivitas UI.
 */

/* ============================================================
   1. TOGGLE SIDEBAR (HAMBURGER MENU)
   ============================================================ */
function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');

    if (!sidebar || !overlay) return;

    var isOpen = sidebar.classList.contains('open');

    if (isOpen) {
        // Tutup sidebar
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        document.body.style.overflow = '';
    } else {
        // Buka sidebar
        sidebar.classList.add('open');
        overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
}

/* ============================================================
   2. TUTUP SIDEBAR SAAT KLIK LINK NAVIGASI (MOBILE)
   ============================================================ */
document.addEventListener('DOMContentLoaded', function () {

    // Tutup sidebar ketika salah satu item menu di-klik (hanya efektif di mobile)
    var navLinks = document.querySelectorAll('.sidebar-menu a');
    navLinks.forEach(function (link) {
        link.addEventListener('click', function () {
            var sidebar = document.getElementById('sidebar');
            var overlay = document.getElementById('sidebarOverlay');
            if (sidebar && sidebar.classList.contains('open')) {
                sidebar.classList.remove('open');
                overlay.classList.remove('show');
                document.body.style.overflow = '';
            }
        });
    });

    /* ============================================================
       3. TUTUP SIDEBAR SAAT RESIZE KE LAYAR BESAR
       ============================================================ */
    window.addEventListener('resize', function () {
        if (window.innerWidth > 900) {
            var sidebar = document.getElementById('sidebar');
            var overlay = document.getElementById('sidebarOverlay');
            if (sidebar) sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('show');
            document.body.style.overflow = '';
        }
    });

    /* ============================================================
       4. AUTO-DISMISS FLASH MESSAGES (setelah 5 detik)
       ============================================================ */
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.style.transition = 'opacity 0.4s ease';
            alert.style.opacity   = '0';
            setTimeout(function () { alert.remove(); }, 400);
        }, 5000);
    });

});