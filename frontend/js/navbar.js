document.addEventListener("DOMContentLoaded", () => {
    const currentPath = window.location.pathname;
    
    // Check authentication status
    const studentData = localStorage.getItem("current_student");
    const adminToken = localStorage.getItem("admin_token");
    
    const isLoginPage = currentPath.includes("login.html") || currentPath.includes("admin_login.html") || currentPath === "/login" || currentPath === "/admin_login";
    
    // Protect routes
    if (!studentData && !adminToken && !isLoginPage) {
        window.location.href = "login.html";
        return;
    }
    
    // If on admin pages, make sure adminToken exists
    const isAdminPage = currentPath.includes("admin.html") || currentPath === "/admin";
    if (isAdminPage && !adminToken) {
        window.location.href = "admin_login.html";
        return;
    }
    
    // Build and inject navbar
    const navbarContainer = document.getElementById("navbar-container");
    if (navbarContainer) {
        let greeting = "";
        let rightNavHtml = "";
        
        if (adminToken) {
            greeting = "Welcome back, Admin";
            rightNavHtml = `
                <div class="d-flex align-items-center gap-3">
                    <span class="text-secondary-custom fs-7 fw-semibold"><i class="bi bi-shield-lock-fill me-1 text-info"></i>${greeting}</span>
                    <a href="#" id="logoutBtn" class="btn btn-sm btn-outline-danger rounded-pill px-3">Logout</a>
                </div>
            `;
        } else if (studentData) {
            const student = JSON.parse(studentData);
            greeting = `Hi, ${student.name} (${student.department}-${student.academic_year})`;
            rightNavHtml = `
                <div class="d-flex align-items-center gap-3">
                    <span class="text-secondary-custom fs-7 fw-semibold"><i class="bi bi-person-circle me-1 text-easy"></i>${greeting}</span>
                    <a href="#" id="logoutBtn" class="btn btn-sm btn-outline-danger rounded-pill px-3">Logout</a>
                </div>
            `;
        }
        
        const activeClass = (path) => currentPath.endsWith(path) || (path === 'index.html' && (currentPath === '/' || currentPath === '')) ? 'active' : '';
        
        navbarContainer.innerHTML = `
            <nav class="navbar navbar-expand-lg navbar-light navbar-custom py-3 mb-4 sticky-top">
                <div class="container">
                    <a class="navbar-brand fw-extrabold fs-4 text-easy d-flex align-items-center" href="${adminToken ? 'admin.html' : 'index.html'}">
                        <i class="bi bi-code-slash me-2"></i>LeetCode Classroom
                    </a>
                    
                    ${!isLoginPage ? `
                    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                        <span class="navbar-toggler-icon"></span>
                    </button>
                    <div class="collapse navbar-collapse" id="navbarNav">
                        <ul class="navbar-nav me-auto mb-2 mb-lg-0 ms-lg-4">
                            ${adminToken ? `
                                <li class="nav-item">
                                    <a class="nav-link fw-semibold px-3 ${activeClass('admin.html')}" href="admin.html">
                                        <i class="bi bi-folder-fill me-1"></i>Database Scanner
                                    </a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link fw-semibold px-3 ${activeClass('leaderboard.html')}" href="leaderboard.html">
                                        <i class="bi bi-trophy-fill me-1"></i>Leaderboard
                                    </a>
                                </li>
                            ` : `
                                <li class="nav-item">
                                    <a class="nav-link fw-semibold px-3 ${activeClass('index.html')}" href="index.html">
                                        <i class="bi bi-grid-1x2-fill me-1"></i>Dashboard
                                    </a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link fw-semibold px-3 ${activeClass('leaderboard.html')}" href="leaderboard.html">
                                        <i class="bi bi-trophy-fill me-1"></i>Leaderboard
                                    </a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link fw-semibold px-3 ${activeClass('compare.html')}" href="compare.html">
                                        <i class="bi bi-bar-chart-fill me-1"></i>Compare
                                    </a>
                                </li>
                                <li class="nav-item">
                                    <a class="nav-link fw-semibold px-3 ${activeClass('attendance.html')}" href="attendance.html">
                                        <i class="bi bi-calendar-check-fill me-1"></i>Attendance
                                    </a>
                                </li>
                            `}
                        </ul>
                        <div class="d-flex align-items-center mt-3 mt-lg-0">
                            ${rightNavHtml}
                        </div>
                    </div>
                    ` : ''}
                </div>
            </nav>
        `;
        
        // Wire up logout button
        const logoutBtn = document.getElementById("logoutBtn");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", (e) => {
                e.preventDefault();
                localStorage.clear();
                window.location.href = adminToken ? "admin_login.html" : "login.html";
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
});
