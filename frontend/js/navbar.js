document.addEventListener("DOMContentLoaded", () => {
    const currentPath = window.location.pathname;
    
    // Check authentication status
    const adminToken = sessionStorage.getItem("admin_token");
    
    const isLocal = window.location.hostname === 'localhost' || 
                    window.location.hostname === '127.0.0.1' || 
                    window.location.protocol === 'file:';
    
    const getPageUrl = (page) => {
        return isLocal ? page : page.replace('.html', '');
    };
    window.getPageUrl = getPageUrl;
    
    // If a user tries to access the old login page, redirect them to the dashboard
    if (currentPath.includes("login.html") || currentPath === "/login") {
        window.location.href = getPageUrl("index.html");
        return;
    }
    
    // Protect admin route (Scanner)
    const isAdminPage = currentPath.includes("admin.html") || currentPath === "/admin";
    if (isAdminPage && !adminToken) {
        window.location.href = getPageUrl("admin_login.html");
        return;
    }
    
    // Helper to extract role details from admin email
    const getAdminRoleDetails = (email) => {
        if (!email) return { title: "Admin", dept: "ALL" };
        const e = email.toLowerCase().trim();
        if (e === 'test456@gmail.com') return { title: "Admin", dept: "ALL" };
        
        // HODs
        if (e === 'nitithod@nehrucolleges.com') return { title: "IT HOD", dept: "IT" };
        if (e === 'nitcsehod@nehrucolleges.com') return { title: "CSE HOD", dept: "CSE" };
        if (e === 'nitccehod@nehrucolleges.com') return { title: "CCE HOD", dept: "CCE" };
        if (e === 'nitaimlhod@nehrucolleges.com') return { title: "AIML HOD", dept: "AIML" };
        if (e === 'nitcshod@nehrucolleges.com') return { title: "CS HOD", dept: "CS" };
        
        // Coordinators
        if (e === 'nititiv@nehrucolleges.com') return { title: "IT IV Yr Coordinator", dept: "IT" };
        if (e === 'nitcseiv@nehrucolleges.com') return { title: "CSE IV Yr Coordinator", dept: "CSE" };
        
        // Placements
        if (e === 'nitplacements@nehrucolleges.com') return { title: "Placements Team", dept: "ALL" };
        if (e === 'nitarunpatrick@nehrucolleges.com') return { title: "Placement Trainer (Arun)", dept: "ALL" };
        if (e === 'nitjasonp@nehrucolleges.com') return { title: "Placement Trainer (Jason)", dept: "ALL" };
        
        return { title: "Coordinator", dept: "ALL" };
    };

    // Build and inject navbar
    const navbarContainer = document.getElementById("navbar-container");
    if (navbarContainer) {
        let rightNavHtml = "";
        
        if (adminToken) {
            const adminEmail = sessionStorage.getItem("admin_email") || "test456@gmail.com";
            const role = getAdminRoleDetails(adminEmail);
            sessionStorage.setItem("admin_dept", role.dept);
            
            rightNavHtml = `
                <div class="d-flex align-items-center gap-3">
                    <span class="text-secondary-custom fs-7 fw-semibold">
                        <i class="bi bi-shield-lock-fill me-1 text-info"></i>Welcome, ${role.title}
                    </span>
                    <a href="#" id="logoutBtn" class="btn btn-sm btn-outline-danger rounded-pill px-3">Logout</a>
                </div>
            `;
        } else {
            sessionStorage.removeItem("admin_dept");
            rightNavHtml = `
                <div class="d-flex align-items-center gap-3">
                    <a href="${getPageUrl('admin_login.html')}" class="btn btn-sm btn-outline-easy rounded-pill px-3">
                        <i class="bi bi-shield-lock-fill me-1"></i>Admin
                    </a>
                </div>
            `;
        }
        
        const activeClass = (path) => {
            const cleanPath = path.replace('.html', '');
            const isMatch = currentPath.endsWith(path) || 
                            currentPath.endsWith('/' + cleanPath) || 
                            (cleanPath === 'index' && (currentPath === '/' || currentPath === '' || currentPath.endsWith('/index')));
            return isMatch ? 'active' : '';
        };
        
        navbarContainer.innerHTML = `
            <nav class="navbar navbar-expand-lg navbar-light navbar-custom py-3 mb-4 sticky-top">
                <div class="container">
                    <a class="navbar-brand fw-extrabold fs-4 text-easy d-flex align-items-center" href="${getPageUrl('index.html')}">
                        <i class="bi bi-code-slash me-2"></i>LeetCode Classroom
                    </a>
                    
                    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                        <span class="navbar-toggler-icon"></span>
                    </button>
                    <div class="collapse navbar-collapse" id="navbarNav">
                        <ul class="navbar-nav me-auto mb-2 mb-lg-0 ms-lg-4">
                            <li class="nav-item">
                                <a class="nav-link fw-semibold px-3 ${activeClass('index.html')}" href="${getPageUrl('index.html')}">
                                    <i class="bi bi-grid-1x2-fill me-1"></i>Dashboard
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link fw-semibold px-3 ${activeClass('leaderboard.html')}" href="${getPageUrl('leaderboard.html')}">
                                    <i class="bi bi-trophy-fill me-1"></i>Leaderboard
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link fw-semibold px-3 ${activeClass('compare.html')}" href="${getPageUrl('compare.html')}">
                                    <i class="bi bi-bar-chart-fill me-1"></i>Compare
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link fw-semibold px-3 ${activeClass('attendance.html')}" href="${getPageUrl('attendance.html')}">
                                    <i class="bi bi-calendar-check-fill me-1"></i>Attendance
                                </a>
                            </li>
                            ${adminToken ? `
                            <li class="nav-item">
                                <a class="nav-link fw-semibold px-3 ${activeClass('admin.html')}" href="${getPageUrl('admin.html')}">
                                    <i class="bi bi-folder-fill me-1"></i>Database Scanner
                                </a>
                            </li>
                            ` : ''}
                        </ul>
                        <div class="d-flex align-items-center mt-3 mt-lg-0">
                            ${rightNavHtml}
                        </div>
                    </div>
                </div>
            </nav>
        `;
        
        // Wire up logout button
        const logoutBtn = document.getElementById("logoutBtn");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", (e) => {
                e.preventDefault();
                sessionStorage.removeItem("admin_token");
                sessionStorage.removeItem("admin_email");
                sessionStorage.removeItem("admin_dept");
                window.location.href = getPageUrl("index.html");
            });
        }
    }
    
    // Inject footer
    const footerContainer = document.getElementById("footer-container");
    if (footerContainer) {
        footerContainer.innerHTML = `
            <footer class="footer mt-auto py-4 border-top border-secondary border-opacity-10 bg-dark-custom">
                <div class="container text-center">
                    <span class="text-secondary-custom fs-7">
                        &copy; 2026 LeetCode Classroom Tracker. All Rights Reserved. Permanent Light Theme Mode enabled.
                    </span>
                </div>
            </footer>
        `;
    }

    // Inject watermark
    const watermark = document.createElement("div");
    watermark.id = "dev-watermark";
    watermark.style.cssText = `
        position: fixed;
        bottom: 12px;
        right: 12px;
        z-index: 9999;
        font-size: 0.7rem;
        font-weight: 600;
        color: rgba(100, 116, 139, 0.7);
        background: rgba(248, 250, 252, 0.85);
        backdrop-filter: blur(4px);
        -webkit-backdrop-filter: blur(4px);
        border: 1px solid rgba(226, 232, 240, 0.8);
        padding: 4px 10px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.03);
        pointer-events: none;
        letter-spacing: 0.02em;
        font-family: 'Outfit', 'Inter', sans-serif;
    `;
    watermark.innerText = "Developed by Mohamed Halid P, Shai Prathap R (IT-23 Batch)";
    document.body.appendChild(watermark);
});
