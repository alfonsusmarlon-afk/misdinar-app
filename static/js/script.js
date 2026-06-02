/**
 * Fungsi untuk membuka/menutup Sidebar Menu di Layar Mobile (HP)
 * Dipicu oleh tombol Hamburger di Topbar.
 */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    
    // Tambah atau Hapus class 'open' & 'show'
    sidebar.classList.toggle('open');
    overlay.classList.toggle('show');
    
    // Mencegah body bisa di-scroll saat menu samping sedang terbuka
    if (sidebar.classList.contains('open')) {
        document.body.style.overflow = 'hidden';
    } else {
        document.body.style.overflow = 'auto';
    }
}