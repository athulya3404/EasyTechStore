/**
 * EasyTech Store - Site Manager Dashboard JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    initAlerts();
    initImagePreviews();
    initQuickStockCounters();
    initClientSearch();
});

// ===== SIDEBAR NAVIGATION & MOBILE TOGGLE =====
function initSidebar() {
    const mobileToggle = document.getElementById('mobileSidebarToggle');
    const sidebar = document.querySelector('.manager-sidebar');
    
    if (mobileToggle && sidebar) {
        mobileToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('show');
        });

        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 768 && sidebar.classList.contains('show')) {
                if (!sidebar.contains(e.target) && e.target !== mobileToggle) {
                    sidebar.classList.remove('show');
                }
            }
        });
    }

    // Auto highlight active nav link based on current path
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar-link');
    
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href && href !== '#' && (currentPath === href || (href.length > 10 && currentPath.startsWith(href)))) {
            link.classList.add('active');
        }
    });
}

// ===== ALERTS AUTO-DISMISS =====
function initAlerts() {
    const alerts = document.querySelectorAll('.manager-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 400);
        }, 5000);
    });
}

// ===== IMAGE UPLOAD PREVIEW =====
function initImagePreviews() {
    const imageInput = document.getElementById('productImageInput');
    const imagePreview = document.getElementById('productImagePreview');

    if (imageInput && imagePreview) {
        imageInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.innerHTML = `<img src="${e.target.result}" alt="Preview" style="width:100%;height:100%;object-fit:cover;">`;
                };
                reader.readAsDataURL(file);
            }
        });
    }
}

// ===== QUICK STOCK COUNTERS =====
function initQuickStockCounters() {
    document.querySelectorAll('.stock-quick-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const input = this.closest('form').querySelector('input[name="new_stock"]');
            if (input) {
                let val = parseInt(input.value) || 0;
                const delta = parseInt(this.dataset.delta) || 0;
                val = Math.max(0, val + delta);
                input.value = val;
            }
        });
    });
}

// ===== CLIENT-SIDE TABLE SEARCH HELPER =====
function initClientSearch() {
    const clientSearchInput = document.getElementById('clientTableSearch');
    if (clientSearchInput) {
        clientSearchInput.addEventListener('input', function() {
            const term = this.value.toLowerCase().trim();
            const rows = document.querySelectorAll('.manager-table tbody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(term)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }
}

// ===== UTILITIES =====
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this item? This action cannot be undone.');
}

window.ManagerApp = {
    confirmDelete
};
