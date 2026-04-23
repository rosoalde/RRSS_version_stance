document.addEventListener("DOMContentLoaded", () => {

    /* =========================================
       1. ENVÍO DEL FORMULARIO DE ANÁLISIS
       ========================================= */
    const analysisForm = document.getElementById("analysisForm");

    if (analysisForm) {
        analysisForm.addEventListener("submit", async function(e) {
            e.preventDefault();
            
            // Recoger datos del formulario (suponiendo que usas FormData o recoges inputs manual)
            // Aquí hago una recolección genérica basada en tu HTML anterior
            const formData = {
                project_name: document.getElementById("projectName")?.value || "Sin nombre",
                tema: document.getElementById("temaAnalisis")?.value || "",
                keywords: document.getElementById("keywords")?.value || "",
                desc_tema: document.getElementById("desc_tema")?.value || "",
                start_date: document.getElementById("startDate")?.value || "",
                end_date: document.getElementById("endDate")?.value || "",
                sources: [], // Rellena esto con tus checkboxes seleccionados
                population_scope: document.getElementById("popScope")?.value || "",
                languages: [], // Rellena esto con tus checkboxes
                results: [] // Inicialmente vacío
            };

            // Recoger Checkboxes de Fuentes
            document.querySelectorAll('input[name="sources"]:checked').forEach(chk => {
                formData.sources.push(chk.value);
            });
             // Recoger Checkboxes de Idiomas
             document.querySelectorAll('input[name="languages"]:checked').forEach(chk => {
                formData.languages.push(chk.value);
            });

            // Feedback visual
            const btnSubmit = analysisForm.querySelector('button[type="submit"]');
            const originalText = btnSubmit.innerHTML;
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analizando...';

            try {
                const response = await fetch("/ejecutar-analisis", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(formData)
                });

                const result = await response.json();

                if (result.status === "ok") {
                    //alert("✅ Análisis completado. Redirigiendo a resultados...");
                    
                    // 🚀 REDIRECCIÓN CLAVE:
                    // Enviamos al usuario a la pantalla de gráficas con el ID del proyecto
                    // Nota: Tu backend devuelve 'user_id' como el ID del análisis en el JSON
                    window.location.href = `/analizar-datasets?project_id=${result.user_id}`;
                    
                } else {
                    alert("❌ Error: " + result.message);
                    btnSubmit.disabled = false;
                    btnSubmit.innerHTML = originalText;
                }

            } catch (error) {
                console.error("Error:", error);
                alert("Error de conexión");
                btnSubmit.disabled = false;
                btnSubmit.innerHTML = originalText;
            }
        });

        
    }

    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", (e) => {
            e.preventDefault();
            fetch("/logout", { method: "POST" })
                .then(() => window.location.href = "/login");
        });
    }
    
    /* =========================================
       2. LÓGICA EXISTENTE (Progress Bars, etc)
       ========================================= */

    /* ===== PROGRESS BARS ===== */
    document.querySelectorAll(".progress-bar").forEach(bar => {
        const progress = parseFloat(bar.dataset.progress);
        if (isNaN(progress)) return;

        const percent = Math.round(progress * 100);

        bar.style.width = percent + "%";
        bar.textContent = percent + "%";
        bar.setAttribute("aria-valuenow", percent);

        if (percent >= 100) {
            bar.classList.remove("progress-bar-striped", "progress-bar-animated");
            bar.classList.add("bg-success");
            bar.textContent = "Completado";
        }
    });

    /* ===== ABORTAR ANALISIS ===== */
    document.querySelectorAll(".abort-analysis-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.dataset.id;
            if (!confirm("¿Seguro que quieres abortar este análisis?")) return;

            fetch(`/analisis/${id}/abort`, { method: "POST" })
            .then(res => { if (!res.ok) throw new Error(); location.reload(); })
            .catch(() => alert("No se pudo abortar el análisis"));
        });
    });

    /* ===== ELIMINAR ANALISIS ===== */
    document.querySelectorAll(".delete-analysis-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.dataset.id;
            if (!confirm("⚠️ Esto eliminará el análisis definitivamente. ¿Continuar?")) return;

            fetch(`/analisis/${id}/delete`, { method: "DELETE" })
            .then(res => { if (!res.ok) throw new Error(); location.reload(); })
            .catch(() => alert("No se pudo eliminar el análisis"));
        });
    });

});