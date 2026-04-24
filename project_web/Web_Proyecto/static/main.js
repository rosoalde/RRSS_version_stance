document.addEventListener("DOMContentLoaded", () => {
    
    console.log("🚀 JS Principal cargado.");

    // 1. Inicializar lógica de "Seleccionar todos"
    setupSelectAll("selectAllSources", 'input[name="sources[]"]');
    setupSelectAll("selectAllLanguages", 'input[name="languages[]"]');

    // 2. Inicializar Generador de Keywords IA
    initKeywordGenerator();

    // 3. Manejo del Formulario Principal
    const form = document.getElementById("projectForm");
    if (form) {
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            if (!isRunning) runAnalysis();
        });
    }

    // 4. Logout
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", (e) => {
            e.preventDefault();
            fetch("/logout", { method: "POST" })
                .then(() => window.location.href = "/login");
        });
    }
});

// Estado global del análisis
let isRunning = false;
let currentBriefDescription = "";
/*************************************************
 * LÓGICA DE KEYWORDS (IA) - VERSIÓN CORREGIDA
 *************************************************/
/*************************************************
 * LÓGICA DE KEYWORDS (IA) - VERSIÓN ROBUSTA
 *************************************************/
function initKeywordGenerator() {
    const generateBtn = document.getElementById("generateKeywordsBtn");
    const container = document.getElementById("generatedKeywordsContainer");
    const addBtn = document.getElementById("addSelectedKeywordsBtn");
    const themeInput = document.getElementById("temaInput");
    const finalInput = document.getElementById("keywordsInput"); // Input real (oculto)
    const previewSpan = document.getElementById("keywordsPreview"); // Texto visual
    const toggleBtn = document.getElementById("toggleKeywordsBtn");

    if (!generateBtn) return;
    
    // LISTENER GLOBAL PARA CAMBIOS EN CHECKBOXES
    if (container && toggleBtn) {
        container.addEventListener("change", () => {
            const checkboxes = container.querySelectorAll(".keyword-check");
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            toggleBtn.innerText = allChecked ? "Desmarcar todo" : "Marcar todo";
        });
    }
    // --- A. GENERAR KEYWORDS ---
    // --- A. GENERAR KEYWORDS ---
    generateBtn.addEventListener("click", async () => {
        const context = themeInput.value.trim();
        const selectedLangs = Array.from(document.querySelectorAll('input[name="languages[]"]:checked')).map(cb => cb.value);
        
        // 1. Captura del input de población
        const popInput = document.getElementById("populationInput");
        if (popInput) popInput.blur(); // Forzar actualización
        
        let rawPopulation = popInput ? popInput.value.trim() : "";
        let populationList = [];

        if (!rawPopulation) {
            // Informamos al usuario de la consecuencia de dejarlo vacío
            const confirmarGlobal = confirm(
                "⚠️ No has especificado un contexto geográfico.\n\n" +
                "El sistema NO filtrará los datos por ubicación y recogerá menciones de cualquier lugar del mundo.\n\n" +
                "¿Deseas continuar con un análisis GLOBAL?"
            );
            
            if (!confirmarGlobal) {
                popInput.focus();
                return; // Detiene la ejecución para que el usuario corrija
            }
            // Si acepta, enviamos un marcador especial
            populationList = ["GLOBAL"]; 
        } else {
            popInput.classList.remove("is-invalid");
            populationList = rawPopulation.split(",").map(s => s.trim()).filter(s => s !== "");
        }

        console.log("📤 Enviando a IA:", { context, selectedLangs, population: populationList });

        if (!context) { alert("⚠️ Introduce un tema."); themeInput.focus(); return; }
        if (selectedLangs.length === 0) { alert("⚠️ Selecciona al menos un idioma."); return; }
        

        const originalText = generateBtn.innerHTML;
        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generando...';
        
        try {
            const response = await fetch("/generate_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    context: context, 
                    languages: selectedLangs, population: populationList // <--- AHORA ENVIAMOS UN ARRAY
                })
            });

            const data = await response.json();

            if (data.success) {
                currentBriefDescription = data.desc_tema || ""; // 💾 GUARDAMOS LA DESCRIPCIÓN
                console.log("✅ Descripción recibida:", currentBriefDescription);
            }

            if (data.keywords && Array.isArray(data.keywords)) {
                container.innerHTML = ""; 
                // ... (El resto del código de renderizado de chips sigue igual) ...
                data.keywords.forEach(item => {
                    let kwObject;
                    let displayText;
                    if (typeof item === 'object' && item.keyword) {
                        kwObject = item;
                        displayText = item.keyword;
                    } else {
                        kwObject = { keyword: item, languages: selectedLangs };
                        displayText = item;
                    }
                    const chip = document.createElement("div");
                    chip.className = "form-check form-check-inline bg-white border rounded-pill px-3 py-2 m-1 shadow-sm user-select-none";
                    const cb = document.createElement("input");
                    cb.type = "checkbox";
                    cb.className = "form-check-input keyword-check";
                    cb.value = JSON.stringify(kwObject); 
                    cb.id = "kw_" + Math.random().toString(36).substr(2, 9);
                    cb.checked = true; 
                    const lbl = document.createElement("label");
                    lbl.className = "form-check-label ms-2 cursor-pointer";
                    lbl.htmlFor = cb.id;
                    lbl.innerText = displayText;
                    chip.appendChild(cb);
                    chip.appendChild(lbl);
                    container.appendChild(chip);
                });
                container.classList.remove("d-none");
                addBtn.classList.remove("d-none");
                addBtn.innerText = "Confirmar selección";
                toggleBtn.classList.remove("d-none");
                toggleBtn.innerText = "Desmarcar todo";
            } else {
                alert("No se pudieron generar keywords.");
            }

        } catch (err) {
            console.error(err);
            alert("Error de conexión con la IA.");
        } finally {
            generateBtn.disabled = false;
            generateBtn.innerHTML = originalText;
        }
    });

    // --- B. CONFIRMAR SELECCIÓN ---
    if (addBtn) {
        addBtn.addEventListener("click", () => {
            const selectedChecks = document.querySelectorAll(".keyword-check:checked");
            
            if (selectedChecks.length === 0) {
                alert("⚠️ No hay ninguna palabra seleccionada.");
                finalInput.value = "";
                previewSpan.innerText = "Ninguna seleccionada";
                return;
            }

            const selectedObjects = Array.from(selectedChecks).map(cb => JSON.parse(cb.value));
            finalInput.value = JSON.stringify(selectedObjects);

            const textSummary = selectedObjects.map(o => o.keyword).join(", ");
            previewSpan.innerText = `${selectedObjects.length} términos seleccionados.`;
            previewSpan.title = textSummary;
            
            previewSpan.parentElement.classList.remove("text-muted");
            previewSpan.parentElement.classList.add("text-success", "fw-bold", "border-success");
            
            addBtn.className = "btn btn-success btn-sm mb-3";
            addBtn.innerHTML = '<i class="bi bi-check-lg"></i> ¡Guardado!';
            setTimeout(() => {
                addBtn.innerText = "Actualizar selección";
                addBtn.className = "btn btn-outline-success btn-sm mb-3";
            }, 2000);
        });
    }
    // --- C. MARCAR / DESMARCAR TODO ---
    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            const checkboxes = document.querySelectorAll(".keyword-check");
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);

            checkboxes.forEach(cb => {
                cb.checked = !allChecked;
            });

            toggleBtn.innerText = allChecked ? "Marcar todo" : "Desmarcar todo";
        });
    }
}

/*************************************************
 * EJECUCIÓN DEL ANÁLISIS
 *************************************************/
async function runAnalysis2() {
    const form = document.getElementById("projectForm");
    const formData = new FormData(form);

    const sources = formData.getAll("sources[]");
    const languages = formData.getAll("languages[]");
    const keywords = formData.get("keywords");

    if (!formData.get("project_name")) { alert("Falta el nombre del proyecto"); return; }
    if (sources.length === 0) { alert("Selecciona al menos una fuente."); return; }
    if (languages.length === 0) { alert("Selecciona al menos un idioma."); return; }
    if (!keywords) { alert("Debes generar y confirmar los términos de búsqueda primero."); return; }

    // Preparar UI
    isRunning = true;
    const btnRun = document.querySelector(".btn-ejecutar");
    const progressDiv = document.getElementById("progressContainer");
    const progressBar = document.getElementById("progressBar");
    const progressText = document.getElementById("progressText");

    btnRun.disabled = true;
    btnRun.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Procesando...';
    if(progressDiv) progressDiv.classList.remove("d-none");
    if(progressBar) progressBar.style.width = "0%";
    if(progressText) progressText.innerText = "Iniciando análisis...";

    const payload = {
        project_name: formData.get("project_name"),
        asistente: formData.get("asistente"),
        keywords: keywords,
        start_date: formData.get("start_date"),
        end_date: formData.get("end_date"),
        sources: sources,
        languages: languages,
        population: formData.get("population") || "",
        results: sources.map(s => ({ social: s, success: true })) // placeholder
    };

    try {
        // 1️⃣ Inicia el análisis y recibe un ID de seguimiento
        const startResponse = await fetch("/ejecutar-analisis", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const startData = await startResponse.json();
        if (startData.status !== "ok") throw new Error(startData.message || "Error iniciando análisis");

        const analysisId = startData.analysis_id;
        progressText.innerText = "Análisis iniciado...";

        // 2️⃣ Polling de estado
        let completed = false;
        while (!completed) {
            await new Promise(r => setTimeout(r, 2000)); // Espera 2s

            const statusResponse = await fetch(`/estado-analisis?analysis_id=${analysisId}`);
            const statusData = await statusResponse.json();
            
            // statusData podría tener la forma:
            // { status: "iniciado"|"progress"|"terminado", current_source: "twitter", progress: 0-100, sources: [{name:"twitter", status:"progress"}, ...] }
            
            if (statusData.status === "iniciado") {
                progressText.innerText = "Iniciando análisis...";
                progressBar.style.width = "5%";
            } else if (statusData.status === "progress") {
                const current = statusData.current_source || "Procesando...";
                progressText.innerText = `Ejecutando en ${current}...`;
                progressBar.style.width = `${statusData.progress || 50}%`;
            } else if (statusData.status === "terminado") {
                completed = true;
                progressText.innerText = "¡Análisis completado!";
                progressBar.style.width = "100%";
                progressBar.classList.replace("bg-primary","bg-success");
            }
        }

        // Redirigir tras breve pausa
        setTimeout(() => {
            window.location.href = `/analizar-datasets?project_id=${analysisId}`;
        }, 2000);

    } catch(e) {
        console.error(e);
        alert("❌ Error: " + e.message);

        isRunning = false;
        btnRun.disabled = false;
        btnRun.innerHTML = '<i class="bi bi-play-circle-fill me-2"></i> REINTENTAR ANÁLISIS';
        if(progressBar) progressBar.classList.add("bg-danger");
    }
}

/*************************************************
 * EJECUCIÓN DEL ANÁLISIS (SIN ESTADO / POLLING)
 *************************************************/
async function runAnalysis() {
    const form = document.getElementById("projectForm");
    const formData = new FormData(form);

    const sources = formData.getAll("sources[]");
    const languages = formData.getAll("languages[]");
    const keywords = formData.get("keywords");

    // Validaciones
    if (!formData.get("project_name")) { 
        alert("Falta el nombre del proyecto"); 
        return; 
    }
    if (sources.length === 0) { 
        alert("Selecciona al menos una fuente."); 
        return; 
    }
    if (languages.length === 0) { 
        alert("Selecciona al menos un idioma."); 
        return; 
    }
    if (!keywords) { 
        alert("Debes generar y confirmar los términos de búsqueda primero."); 
        return; 
    }

    // Preparar UI
    isRunning = true;
    const btnRun = document.querySelector(".btn-ejecutar");
    const progressDiv = document.getElementById("progressContainer");
    const progressBar = document.getElementById("progressBar");
    const progressText = document.getElementById("progressText");
    const populationValue = formData.get("population") ? formData.get("population").trim() : "";

    btnRun.disabled = true;
    btnRun.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Procesando...';

    if (progressDiv) progressDiv.classList.remove("d-none");
    if (progressBar) progressBar.style.width = "0%";
    if (progressText) progressText.innerText = "Iniciando análisis...";

    const payload = {
        project_name: formData.get("project_name"),
        asistente: formData.get("asistente"),
        desc_tema: currentBriefDescription,
        keywords: keywords,
        start_date: formData.get("start_date"),
        end_date: formData.get("end_date"),
        sources: sources,
        languages: languages,
        population: populationValue || "GLOBAL", 
        results: sources.map(s => ({ social: s, success: true }))
    };

    try {
        // Llamada al backend
        const response = await fetch("/ejecutar-analisis", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok || data.status !== "ok") {
            throw new Error(data.message || "Error iniciando análisis");
        }

        const analysisId = data.analysis_id || data.user_id || (data.data ? data.data.analysis_id : null);

        // Validación importante
        if (!analysisId) {
            throw new Error("No se recibió el ID del análisis");
        }

        // Actualizar UI (simulado simple)
        if (progressText) progressText.innerText = "Procesando análisis...";
        if (progressBar) progressBar.style.width = "100%";

        // Redirección directa
        setTimeout(() => {
            window.location.href = `/analizar-datasets?project_id=${analysisId}`;
        }, 4000);

    } catch (e) {
        console.error(e);
        alert("❌ Error: " + e.message);

        isRunning = false;

        btnRun.disabled = false;
        btnRun.innerHTML = '<i class="bi bi-play-circle-fill me-2"></i> REINTENTAR ANÁLISIS';

        if (progressBar) {
            progressBar.classList.remove("bg-primary");
            progressBar.classList.add("bg-danger");
        }

        if (progressText) {
            progressText.innerText = "Error en el análisis";
        }
    }
}

/*************************************************
 * UTILIDADES UI
 *************************************************/
function setupSelectAll(masterId, selector) {
    const master = document.getElementById(masterId);
    if (!master) return;

    const getCheckboxes = () =>
        Array.from(document.querySelectorAll(selector))
            .filter(cb => !cb.disabled); // 👈 SOLO LOS HABILITADOS

    // Maestro controla hijos
    master.addEventListener("change", () => {
        getCheckboxes().forEach(cb => cb.checked = master.checked);
    });

    // Hijos controlan maestro
    document.querySelectorAll(selector).forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.disabled) return; // 👈 ignorar deshabilitados

            const enabled = getCheckboxes();
            const allChecked = enabled.every(c => c.checked);
            master.checked = allChecked;
        });
    });
}