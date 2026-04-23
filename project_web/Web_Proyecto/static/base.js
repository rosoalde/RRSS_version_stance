document.addEventListener("DOMContentLoaded", () => {
    // Logout Logic
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", (e) => {
            e.preventDefault();
            fetch("/logout", { method: "POST" })
                .then(() => window.location.href = "/login");
        });
    }

    // Sidebar Toggle (Protegido)
    const toggleBtn = document.querySelector("#sidebarToggle");
    const sidebar = document.querySelector("#sidebarMenu"); // Asegúrate que este ID coincida con tu HTML base

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", () => {
            sidebar.classList.toggle("collapse");
        });
    }
    const sidebarList = document.getElementById("sidebarProjectList");
    
    if (sidebarList) {
        fetch("/api/proyectos-sidebar")
            .then(response => response.json())
            .then(projects => {
                if (!projects || projects.length === 0) {
                    sidebarList.innerHTML = '<div class="py-2 px-3 small text-muted fst-italic">No hay proyectos aún</div>';
                    return;
                }

                // Limpiar el "Cargando..."
                sidebarList.innerHTML = ""; 

                // Crear un enlace por cada proyecto
                projects.forEach(proj => {
                    const a = document.createElement("a")
                    const urlParams = new URLSearchParams(window.location.search);
                    if (urlParams.get("project_id") === proj.id) {
                        a.classList.add("active", "bg-primary", "text-white"); // Resalta el proyecto seleccionado
                    }
                    ;
                    // Importante: redirigimos pasando el ID por la URL
                    a.href = `/analizar-datasets?project_id=${proj.id}`;
                    a.className = "list-group-item list-group-item-action small border-0 py-2 ps-4";
                    
                    // Usamos el nombre del proyecto y un icono
                    a.innerHTML = `
                        <div class="d-flex align-items-center">
                            <i class="bi bi-file-earmark-bar-graph me-2 text-secondary"></i>
                            <span class="text-truncate">${proj.project_name}</span>
                        </div>
                    `;
                    
                    sidebarList.appendChild(a);
                });
            })
            .catch(err => {
                console.error("Error cargando proyectos del sidebar:", err);
                sidebarList.innerHTML = '<div class="py-2 px-3 small text-danger">Error al cargar</div>';
            });
    }
});