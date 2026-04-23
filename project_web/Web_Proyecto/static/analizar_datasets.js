document.addEventListener("DOMContentLoaded", () => {
    console.log("🚀 JS de Analizar Datasets cargado.");

    const projectSelect = document.getElementById("projectSelect");
    const resultsPlaceholder = document.getElementById("resultsPlaceholder");
    const chartsContainer = document.getElementById("chartsContainer");
    const DEFINICIONES_PILARES = {
        "legitimacion": "Mide si la ciudadanía percibe la medida como válida, legal y socialmente aceptable.",
        "efectividad": "Evalúa si el público cree que la medida realmente cumple sus objetivos y resuelve el problema.",
        "justicia_equidad": "Analiza si la política se percibe como justa e igualitaria para todos los sectores sociales.",
        "confianza_institucional": "Refleja el nivel de credibilidad y confianza en los organismos que implementan la medida."
    };
    
    // VARIABLES GLOBALES
    let rawDataset = []; 
    let charts = {};     
    let tagifyInstance = null; 
    let aceptacionModalInstance = null;
    let currentGeoTerms = [];
    let currentCustomTopic = "";
    let currentGeoTermsAceptacion = []; // Indicador aceptación

    const COLORS = ["#00ced1", "#e8c302", "#ab54f0", "#f34554", "#2d85e5", "#999999"];

    async function aplicarFiltroAceptacion() {
        const analysisId = projectSelect.value;
        if (!analysisId) return;

        const geoInputModal = document.getElementById("geoInputModal");
        const rawValue = geoInputModal.value.trim();

        // Si está vacío, terms será [], lo cual el backend entiende como "quitar filtros"
        const terms = rawValue
            .split(",")
            .map(t => t.trim())
            .filter(t => t.length > 0);

        currentGeoTermsAceptacion = terms;

        const aceptacionContainer = document.getElementById("aceptacionContainer");
        aceptacionContainer.innerHTML = `
            <div class="card border-0 shadow-sm p-3 text-center">
                <div class="spinner-border text-primary mb-2"></div>
                <div class="fw-bold">Actualizando indicador</div>
                <small class="text-muted">${terms.length ? terms.join(", ") : "Cargando valores originales..."}</small>
            </div>
        `;

        try {
            const response = await fetch(`/analisis/${analysisId}/aceptacion/filter-geo`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ terms: currentGeoTermsAceptacion })
            });

            if (!response.ok) throw new Error("Error en el servidor");
            const data = await response.json();
            renderAceptacion(data);

        } catch (err) {
            aceptacionContainer.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
        }
    }

    // ==========================================
    // 1. CARGA DE DATOS
    // ==========================================
    async function cargarDashboard(analysisId, retryCount = 0) {
        if (!analysisId) return;
        
        // 1. Mostrar estado de carga
        if (retryCount === 0) {
            resultsPlaceholder.classList.remove("d-none");
            resultsPlaceholder.innerHTML = `
                <div class="py-5 text-center">
                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;"></div>
                    <p class="mt-3 fw-bold">Sincronizando resultados del análisis...</p>
                    <small class="text-muted">Preparando visualización, un momento por favor.</small>
                </div>`;
            chartsContainer.classList.add("d-none");
        }

        try {
            console.log(`📡 Intento de carga ${retryCount + 1} para ID: ${analysisId}`);
            const response = await fetch(`/analisis/${analysisId}/dashboard`);
            
            // Si el servidor da error 500 o 404, lanzamos error para ir al catch y reintentar
            if (!response.ok) throw new Error(`Servidor no listo (Status: ${response.status})`);
            
            const data = await response.json();

            // Si los datos están vacíos, el archivo aún se está escribiendo
            if (!data || Object.keys(data).length === 0 || data.error) {
                throw new Error("Datos incompletos");
            }

            // ✅ ÉXITO: Rellenar y mostrar
            document.getElementById("displayProjectName").innerText = data.project_name || "--";
            document.getElementById("displayTemaName").innerText = data.tema || "--";
            document.getElementById("displayThemeDescription").innerText = data.desc_tema || "";

            resultsPlaceholder.classList.add("d-none");
            chartsContainer.classList.remove("d-none");
            
            renderDashboard(data);
            console.log("✅ Dashboard cargado correctamente.");

        } catch (error) {
            console.warn(`⚠️ Reintentando carga (${retryCount + 1}/5): ${error.message}`);

            // Si falla, esperamos 3 segundos y reintentamos hasta 5 veces
            if (retryCount < 5) {
                setTimeout(() => {
                    cargarDashboard(analysisId, retryCount + 1);
                }, 3000);
            } else {
                // Error definitivo tras 15 segundos de intentos
                resultsPlaceholder.innerHTML = `
                    <div class="alert alert-warning shadow-sm text-center p-4">
                        <i class="bi bi-exclamation-triangle display-4 d-block mb-3"></i>
                        <h5 class="fw-bold">Los datos están tardando en generarse</h5>
                        <p>El análisis ha finalizado, pero el servidor aún está procesando las gráficas.</p>
                        <button class="btn btn-warning fw-bold mt-2" onclick="location.reload()">
                            <i class="bi bi-arrow-clockwise"></i> REINTENTAR AHORA
                        </button>
                    </div>`;
            }
        }
    }
    //Para sincronizar los datos
    async function runPollingAndLoadDashboard(analysisId) {
        let completed = false;
        while (!completed) {
            await new Promise(r => setTimeout(r, 1000));

            const statusRes = await fetch(`/estado-analisis?analysis_id=${analysisId}`);
            const statusData = await statusRes.json();

            if (statusData.status === "iniciado") {
                progressText.innerText = "Iniciando análisis...";
            } else if (statusData.status === "progress") {
                progressText.innerText = `Ejecutando en ${statusData.current_source}...`;
                progressBar.style.width = `${statusData.progress}%`;
            } else if (statusData.status === "terminado") {
                completed = true;
                progressText.innerText = "¡Análisis completado!";
                progressBar.style.width = "100%";
                progressBar.classList.replace("bg-primary", "bg-success");
            }
        }

        // Ahora que terminó, carga el dashboard
        await cargarDashboard(analysisId);
    }    

    // ==========================================
    // 2. RENDERIZADO DE GRÁFICAS
    // ==========================================
    function renderDashboard(data) {
        if (!data || !data.kpis) {
            console.error("❌ Datos incompletos para el dashboard", data);
            resultsPlaceholder.innerHTML = `<div class="alert alert-warning">El análisis terminó pero los datos aún se están procesando. Por favor, refresca en unos segundos.</div>`;
            return;
        }
        console.log("🎨 Renderizando gráficas...");

        // RELLENAR ENCABEZADO DE CONTEXTO ---
        const headerDiv = document.getElementById("projectHeader");
        const temaNameDisplay = document.getElementById("displayTemaName");
        const projectNameDisplay = document.getElementById("displayProjectName");
        const themeDescDisplay = document.getElementById("displayThemeDescription");

        if (headerDiv) {
            headerDiv.classList.remove("d-none");
            // Intentamos sacar el nombre del proyecto del select o de la data
            const selectedOption = projectSelect.options[projectSelect.selectedIndex];
            projectNameDisplay.innerText = data.project_name || "Proyecto sin nombre";
            temaNameDisplay.innerText = data.tema || "No hay un tema definido para este proyecto.";
            
            // La descripción viene de la IA (la guardamos en el backend como 'desc_tema')
            // Si tu backend la envía en el JSON del dashboard, la usamos:
            themeDescDisplay.innerText = data.desc_tema || "No hay una descripción disponible para este tema.";
        }

        // BLOQUE 1: VOLUMEN
        try {
            document.getElementById("kpiTotal").innerText = data.kpis.total || 0;
        } catch (e) {}

        try {
            const vol = data.volumen_por_red || {};
            renderChart("volumenRedChart", "doughnut", {
                labels: Object.keys(vol),
                datasets: [{
                    data: Object.values(vol),
                    backgroundColor: COLORS,
                    borderWidth: 0
                }]
            }, { cutout: '60%' });
        } catch (e) { console.error("Error Vol Red:", e); }

        try {
            const trend = data.tendencia_global || {};
            const fechas = Object.keys(trend).sort();
            const totales = fechas.map(f => trend[f]);
            
            renderChart("tendenciaGlobalVolChart", "line", {
                labels: fechas,
                datasets: [{
                    label: "Menciones totales",
                    data: totales,
                    borderColor: "#2d85e5",
                    backgroundColor: "rgba(45,133,229,0.1)",
                    fill: true,
                    tension: 0.3
                }]
            });
        } catch (e) { console.error("Error Trend Global:", e); }

        try {
            const trendRed = data.tendencia_por_red || {};
            const fechasSet = new Set();
            Object.values(trendRed).forEach(r => {
                if(r.total) Object.keys(r.total).forEach(d => fechasSet.add(d));
            });
            const fechasOrdenadas = Array.from(fechasSet).sort();

            const datasets = Object.keys(trendRed).map((red, index) => {
                const dataPuntos = fechasOrdenadas.map(f => trendRed[red].total[f] || 0);
                return {
                    label: red,
                    data: dataPuntos,
                    borderColor: COLORS[index % COLORS.length],
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    tension: 0.3
                };
            });

            renderChart("tendenciaRedVolChart", "line", {
                labels: fechasOrdenadas,
                datasets: datasets
            });
        } catch (e) { console.error("Error Trend Red Multi:", e); }

        // BLOQUE 2: SENTIMIENTO GLOBAL
        try {
            const kpis = data.kpis || {};
            document.getElementById("kpiPos").innerText = kpis.positivos || 0;
            document.getElementById("kpiNeu").innerText = kpis.neutros || 0;
            document.getElementById("kpiNeg").innerText = kpis.negativos || 0;

            renderChart("sentimientoGlobalDonut", "doughnut", {
                labels: ["Positivo", "Neutro", "Negativo"],
                datasets: [{
                    data: [kpis.positivos, kpis.neutros, kpis.negativos],
                    backgroundColor: ["#0eb26c", "#e4e8eb", "#d8535f"],
                    borderWidth: 0
                }]
            }, { cutout: '70%' });
        } catch (e) { console.error("Error Sent Global:", e); }

        try {
            const trendSent = data.tendencia_sentimiento || {};
            const fechas = Object.keys(trendSent).sort();
            
            const dataPos = fechas.map(f => trendSent[f]["Positivo"] || 0);
            const dataNeu = fechas.map(f => trendSent[f]["Neutro"] || 0);
            const dataNeg = fechas.map(f => trendSent[f]["Negativo"] || 0);

            renderChart("sentimientoGlobalTrend", "line", {
                labels: fechas,
                datasets: [
                    { label: "Positivo", data: dataPos, borderColor: "#0eb26c", tension: 0.3 },
                    { label: "Neutro", data: dataNeu, borderColor: "#999999", borderDash: [5, 5], tension: 0.3 },
                    { label: "Negativo", data: dataNeg, borderColor: "#d8535f", tension: 0.3 }
                ]
            });
        } catch (e) { console.error("Error Trend Sent Global:", e); }

        // BLOQUE 3: SENTIMIENTO POR RED
        try {
            const container = document.getElementById("redesContainer");
            container.innerHTML = ""; 
            const trendRed = data.tendencia_por_red || {};

            for (let red in trendRed) {
                const safeRedId = red.replace(/\s+/g, '_').replace(/[()]/g, '');
                const colRed = document.createElement("div");
                colRed.className = "col-12"; // Una fila completa por red
                
                // Calculamos totales para los badges de esta red
                let pos = 0, neu = 0, neg = 0;
                const sentData = trendRed[red].sentimiento || {};
                const fechasRed = Object.keys(sentData).sort();
                fechasRed.forEach(f => {
                    pos += sentData[f]["Positivo"] || 0;
                    neu += sentData[f]["Neutro"] || 0;
                    neg += sentData[f]["Negativo"] || 0;
                });

                // Dentro del bucle for (let red in trendRed)
                colRed.innerHTML = `
                    <div class="card border-0 shadow-sm mb-4 rounded-4 overflow-hidden">
                        <div class="card-header bg-light py-2 border-0">
                            <span class="fw-bold text-dark small text-uppercase"><i class="bi bi-dot text-success"></i> ${red}</span>
                        </div>
                        <div class="card-body p-4">
                            <div class="row g-4 align-items-stretch">
                                <div class="col-md-4 d-flex">
                                    <div class="p-4 border rounded-4 bg-white shadow-sm text-center w-100 d-flex flex-column justify-content-center">
                                        <h6 class="text-muted text-uppercase small fw-bold mb-4">Polaridad en ${red}</h6>
                                        <div style="height: 180px;">
                                            <canvas id="donut_${safeRedId}"></canvas>
                                        </div>
                                        <div class="d-flex justify-content-center gap-2 mt-4">
                                            <div class="badge bg-success-subtle text-success p-2 rounded-pill small">${pos} Pos</div>
                                            <div class="badge bg-secondary-subtle text-secondary p-2 rounded-pill small">${neu} Neu</div>
                                            <div class="badge bg-danger-subtle text-danger rounded-pill">${neg} Neg</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-8 d-flex">
                                    <div class="p-3 border rounded-3 bg-white h-100 w-100">
                                        <h6 class="text-dark fw-bold small text-uppercase mb-3"><i class="bi bi-graph-up me-2 text-primary"></i>Evolución temporal en ${red}</h6>
                                        <div style="height: 220px;">
                                            <canvas id="line_${safeRedId}"></canvas>
                                        </div>
                                        <p class="text-muted small text-center mt-3 mb-0">Identifica fluctuaciones en el tono de las menciones dentro de esta plataforma.</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                container.appendChild(colRed);

                // Renderizado de las gráficas (se mantiene igual el setTimeout)
                setTimeout(() => {
                    renderChart(`donut_${safeRedId}`, "doughnut", {
                        labels: ["Pos", "Neu", "Neg"],
                        datasets: [{
                            data: [pos, neu, neg],
                            backgroundColor: ["#0eb26c", "#e4e8eb", "#d8535f"],
                            borderWidth: 0
                        }]
                    }, { plugins: { legend: { display: false } }, cutout: '70%' });

                    const dPos = fechasRed.map(f => sentData[f]["Positivo"] || 0);
                    const dNeu = fechasRed.map(f => sentData[f]["Neutro"] || 0);
                    const dNeg = fechasRed.map(f => sentData[f]["Negativo"] || 0);

                    renderChart(`line_${safeRedId}`, "line", {
                        labels: fechasRed,
                        datasets: [
                            { label: "Pos", data: fechasRed.map(f => sentData[f]["Positivo"] || 0), borderColor: "#0eb26c", backgroundColor: "#0eb26c", tension: 0.3, pointRadius: 4, borderWidth: 2 },
                            { label: "Neu", data: fechasRed.map(f => sentData[f]["Neutro"] || 0), borderColor: "#999999", backgroundColor: "#999999", borderDash: [3,3], tension: 0.3, pointRadius: 4, borderWidth: 1 },
                            { label: "Neg", data: fechasRed.map(f => sentData[f]["Negativo"] || 0), borderColor: "#d8535f", backgroundColor: "#d8535f", tension: 0.3, pointRadius: 4, borderWidth: 2 }
                        ]
                    }, { plugins: { legend: { display: false } }, maintainAspectRatio: false });
                }, 0);
            }
        } catch (e) { console.error("Error Bloque Redes:", e); }

        // BLOQUE 4: TOPICS Y NUBES
        try {
            const topics = data.topics || [];
            const topTopics = topics.sort((a, b) => b.volumen - a.volumen).slice(0, 10);
            
            const labels = topTopics.map(t => t.TOPIC);
            const values = topTopics.map(t => t.volumen);

            renderChart("topicsPieChart", "pie", {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: COLORS,
                    borderWidth: 1
                }]
            });
            renderTopicsDetail(topics, data.kpis.total);
        } catch (e) { console.error("Error Topics Pie:", e); }

        try {
            const cloudContainer = document.getElementById("cloudContainer");
            if (cloudContainer && data.nubes) {
                cloudContainer.innerHTML = ""; 
                for (const [nombre, base64Str] of Object.entries(data.nubes)) {
                    const colDiv = document.createElement("div");
                    colDiv.className = "col-6 text-center mb-2";
                    colDiv.innerHTML = `
                        <div class="border rounded p-1">
                            <small class="d-block fw-bold text-muted mb-1">${nombre.replace("nube_", "")}</small>
                            <img src="data:image/png;base64,${base64Str}" class="img-fluid" style="max-height: 150px;">
                        </div>
                    `;
                    cloudContainer.appendChild(colDiv);
                }
            }
        } catch (e) { console.error("Error Nubes:", e); }
    }

    function renderChart(id, type, data, options = {}) {
        const ctx = document.getElementById(id);
        if (!ctx) return;
        if (charts[id]) charts[id].destroy();
        // Configuración estándar para que todos los ejes sean iguales
        const standardScales = {
            y: {
                beginAtZero: true,
                title: {
                    display: true,
                    text: 'Nº de menciones', // <--- Título del eje Y
                    font: { size: 11, weight: 'bold' }
                }
            },
            x: {
                title: {
                    display: true,
                    text: 'Fecha de publicación', // <--- Título del eje X
                    font: { size: 11, weight: 'bold' }
                }
            }
        };

        charts[id] = new Chart(ctx, {
            type: type,
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                // Mezclamos las escalas estándar con las opciones específicas que envíes
                scales: type === 'line' ? standardScales : {}, 
                plugins: {
                    legend: { position: 'bottom' }
                },
                ...options
            }
        });
    }

    function renderTopicsDetail(topics, totalGlobal) {
        const container = document.getElementById("topicsDetailContainer");
        if (!container) return;
        container.innerHTML = "";

        topics.sort((a, b) => b.volumen - a.volumen).forEach(topic => {
            const vol = topic.volumen || 1;
            
            // FORZAMOS EL CÁLCULO: Si el dato es NaN o undefined, se convierte en 0
            const pPos = parseFloat(((topic.pos || 0) / vol) * 100) || 0;
            const pNeu = parseFloat(((topic.neu || 0) / vol) * 100) || 0;
            const pNeg = parseFloat(((topic.neg || 0) / vol) * 100) || 0;
            const pGlobal = parseFloat((vol / totalGlobal) * 100) || 0;

            const row = document.createElement("div");
            row.className = "mb-4";
            row.innerHTML = `
                <div class="d-flex justify-content-between align-items-end mb-1">
                    <div>
                        <span class="fw-bold text-dark text-capitalize">${topic.TOPIC}</span>
                        <span class="badge bg-light text-dark border ms-2">${topic.volumen} menciones</span>
                    </div>
                    <small class="text-muted fw-bold">${pGlobal.toFixed(1)}% del total</small>
                </div>
                <div class="progress rounded-pill" style="height: 12px; background-color: #f0f0f0;">
                    <div class="progress-bar bg-success" style="width: ${pPos}%"></div>
                    <div class="progress-bar bg-secondary" style="width: ${pNeu}%" style="opacity: 0.7;"></div>
                    <div class="progress-bar bg-danger" style="width: ${pNeg}%"></div>
                </div>
                <div class="d-flex justify-content-between mt-1" style="font-size: 0.7rem;">
                    <span class="text-success fw-bold">${pPos.toFixed(1)}% Pos</span>
                    <span class="text-muted fw-bold">${pNeu.toFixed(1)}% Neu</span>
                    <span class="text-danger fw-bold">${pNeg.toFixed(1)}% Neg</span>
                </div>
            `;
            container.appendChild(row);
        });
    }

    // ==========================================
    // FILTROS GEO + TOPIC
    // ==========================================
    function initFilters() {
        const geoInput = document.getElementById("geoFilterInput");
        const btnApplyGeo = document.getElementById("btnApplyFilter");
        const btnClearGeo = document.getElementById("btnClearFilter");

        const topicInput = document.getElementById("topicFilterInput"); 
        const btnApplyTopic = document.getElementById("btnApplyTopic");
        const btnClearTopic = document.getElementById("btnClearTopic");

        // Inicializar Tagify
        if (geoInput && typeof Tagify !== 'undefined' && !tagifyInstance) {
            try {
                tagifyInstance = new Tagify(geoInput, { delimiters: ",", dropdown: { enabled: 0 } });
            } catch(e) { console.warn("Tagify error", e); }
        }

        async function applyFilters() {
            const analysisId = projectSelect.value;
            if (!analysisId) {
                alert("Selecciona un proyecto.");
                return;
            }

            currentGeoTerms = tagifyInstance ? tagifyInstance.value.map(t => t.value)
                                              : geoInput ? geoInput.value.split(",").map(t => t.trim()).filter(t => t) : [];

            currentCustomTopic = topicInput ? topicInput.value.trim() : "";

            if (currentGeoTerms.length === 0 && currentCustomTopic === "") {
                alert("Ingresa un término geográfico o un topic para filtrar.");
                return;
            }

            resultsPlaceholder.classList.remove("d-none");
            chartsContainer.classList.add("d-none");

            let msg = currentGeoTerms.length && currentCustomTopic
                      ? `Filtrando por Geo: <b>${currentGeoTerms.join(", ")}</b> Y Topic: <b>${currentCustomTopic}</b>`
                      : currentCustomTopic
                      ? `Buscando topics relacionados con: <b>${currentCustomTopic}</b> (IA)`
                      : `Filtrando por Geo: <b>${currentGeoTerms.join(", ")}</b>`;

            resultsPlaceholder.innerHTML = `
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2">${msg}</p>
                <small class="text-muted">Recalculando dashboard completo...</small>
            `;

            try {
                const response = await fetch(`/analisis/${analysisId}/filter-geo`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ terms: currentGeoTerms, custom_topic: currentCustomTopic })
                });

                if (!response.ok) throw new Error("Error en el servidor.");

                const newData = await response.json();

                resultsPlaceholder.classList.add("d-none");
                chartsContainer.classList.remove("d-none");

                rawDataset = newData.raw_data || [];
                renderDashboard(newData);

            } catch (error) {
                console.error("❌ Error filtro:", error);
                resultsPlaceholder.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
            }
        }

        if (btnApplyGeo) btnApplyGeo.addEventListener("click", applyFilters);
        if (btnApplyTopic) btnApplyTopic.addEventListener("click", applyFilters);

        if (btnClearGeo) btnClearGeo.addEventListener("click", () => {
            if (tagifyInstance) tagifyInstance.removeAllTags();
            else geoInput.value = "";
            currentGeoTerms = [];
            currentCustomTopic ? applyFilters() : cargarDashboard(projectSelect.value);
        });

        if (btnClearTopic) btnClearTopic.addEventListener("click", () => {
            topicInput.value = "";
            currentCustomTopic = "";
            currentGeoTerms.length ? applyFilters() : cargarDashboard(projectSelect.value);
        });
    }

    initFilters();

    // --- NUEVA LÓGICA DE CARGA AUTOMÁTICA ---
    const urlParams = new URLSearchParams(window.location.search);
    const pid = urlParams.get("project_id");

    if (pid) {
        console.log("🔎 Detectado project_id en URL:", pid);

        // 1. Si el select existe, le asignamos el valor
        if (projectSelect) {
            // Creamos la opción dinámicamente si no existe para que el .value funcione
            let option = projectSelect.querySelector(`option[value="${pid}"]`);
            if (!option) {
                option = document.createElement('option');
                option.value = pid;
                option.text = pid;
                projectSelect.appendChild(option);
            }
            projectSelect.value = pid;
        }
        
        // 2. Disparamos la carga directamente
        cargarDashboard(pid);
        // console.log("🚀 Cargando dashboard para:", pid);
    }

    // Escuchar cambios manuales en el desplegable
    projectSelect.addEventListener("change", e => cargarDashboard(e.target.value));

    // ==========================================
    // INDICADOR DE ACEPTACIÓN
    // ==========================================
    const btnRunAcep = document.getElementById("btnRunAcep");
    const aceptacionContainer = document.getElementById("aceptacionContainer");

    if (btnRunAcep) {
        btnRunAcep.addEventListener("click", async () => {
            const analysisId = projectSelect.value;
            if (!analysisId) return;

            btnRunAcep.disabled = true;

            aceptacionContainer.innerHTML = `
                <div class="card border-0 shadow-sm p-3 text-center">
                    <div class="spinner-border text-primary mb-2"></div>
                    <div class="fw-bold">Calculando indicador de aceptación</div>
                    <small class="text-muted">
                        ${currentGeoTermsAceptacion.length 
                            ? `Filtro activo: ${currentGeoTermsAceptacion.join(", ")}` 
                            : "Sin filtro geográfico"}
                    </small>
                </div>
            `;

            try {
                const response = await fetch(`/analisis/${analysisId}/aceptacion/filter-geo`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ terms: currentGeoTermsAceptacion })
                });

                if (!response.ok) {
                    const txt = await response.text();
                    throw new Error(txt || "Error ejecutando indicador.");
                }

                const data = await response.json();
                renderAceptacion(data, data.files || {});

            } catch (error) {
                aceptacionContainer.innerHTML = `
                    <div class="alert alert-danger mt-2">
                        ${error.message}
                    </div>
                `;
            } finally {
                btnRunAcep.disabled = false;
            }
        });
    }

    function renderAceptacion(result, files = {}) {
        if (!result) {
            document.getElementById('aceptacionModalBody').innerHTML = '<div class="alert alert-warning">No hay datos disponibles.</div>';
            return;
        }

        const valor = result["Aceptación Global [%]"] ?? 0;
        const interpretacion = result["Interpretación"] ?? "";
        const porPilares = result["Aceptación por pilar"] || {};

        // --- 1. ACTUALIZAR PANEL LATERAL (Quitar el "Calculando...") ---
        const aceptacionContainer = document.getElementById("aceptacionContainer");
        if (aceptacionContainer) {
            aceptacionContainer.innerHTML = `
                <div class="card border-primary shadow-sm p-3 bg-white rounded-4">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <small class="text-muted text-uppercase fw-bold">Resultado Aceptación</small>
                        <span class="badge ${getAceptacionColorClass(valor).replace('text-', 'bg-')}">${valor.toFixed(1)}%</span>
                    </div>
                    <div class="h5 fw-bold mb-1">${interpretacion}</div>
                    <small class="text-muted fst-italic">Basado en ${result["Menciones con juicio de valor"]} menciones relevantes.</small>
                    <button class="btn btn-sm btn-outline-primary mt-3 w-100" onclick="new bootstrap.Modal(document.getElementById('aceptacionModal')).show()">
                        Ver informe detallado
                    </button>
                </div>
            `;
        }

        // --- 2. CONSTRUIR EL MODAL CON EXPLICACIONES ---
        const notaMetodologica = `
            <div class="alert alert-info border-0 shadow-sm small mb-4">
                <i class="bi bi-info-circle-fill me-2"></i>
                <strong>Nota metodológica:</strong> Este análisis se basa exclusivamente en un subconjunto de <strong>${result["Menciones con juicio de valor"]} menciones</strong> que contienen juicios de valor explícitos. Se descartan las menciones puramente informativas o no relacionadas.
            </div>
        `;

        let pillarsHtml = '<div class="row g-3">';
        for (const [p, value] of Object.entries(porPilares)) {
            const percent = ((value + 1) / 2 * 100) || 0;
            const nombreLimpio = p.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const definicion = DEFINICIONES_PILARES[p] || "Análisis de pilar estratégico.";
            
            pillarsHtml += `
                <div class="col-md-6">
                    <div class="p-3 border rounded-4 bg-white shadow-sm h-100">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="fw-bold mb-0">${nombreLimpio}</h6>
                            <span class="fw-bold ${getAceptacionColorClass(percent)}">${percent.toFixed(1)}%</span>
                        </div>
                        <div class="progress mb-2" style="height: 6px;">
                            <div class="progress-bar ${getAceptacionColorClass(percent).replace('text-', 'bg-')}" style="width: ${percent}%"></div>
                        </div>
                        <p class="text-muted mb-0" style="font-size: 0.75rem; line-height: 1.2;">${definicion}</p>
                    </div>
                </div>`;
        }
        pillarsHtml += '</div>';

        const body = `
            ${notaMetodologica}
            <div class="text-center mb-4">
                <div class="display-4 fw-bold ${getAceptacionColorClass(valor)}">${valor.toFixed(1)}%</div>
                <div class="h5 text-muted">${interpretacion}</div>
            </div>
            <h6 class="text-dark fw-bold small text-uppercase mb-3 border-bottom pb-2">Desglose por Pilares Estratégicos</h6>
            ${pillarsHtml}
        `;

        document.getElementById('aceptacionModalBody').innerHTML = body;
        
        const jsonPath = files.json || files.csv || files.txt || '';
        
        // --- CONTROL DEL MODAL (SOLUCIÓN AL FONDO NEGRO) ---
        const aceptacionModalEl = document.getElementById('aceptacionModal');
        
        // Si no existe la instancia, la creamos una sola vez
        
        if (!aceptacionModalInstance) {
            aceptacionModalInstance = new bootstrap.Modal(aceptacionModalEl);
        }

        // Solo mostramos el modal si no tiene la clase 'show' (evita duplicar backdrops)
        if (!aceptacionModalEl.classList.contains('show')) {
            aceptacionModalInstance.show();
        }

        // Configurar botones (usamos onclick para evitar acumular event listeners)
        document.getElementById('btnApplyGeoFromModal').onclick = async () => {
            const geoInput = document.getElementById("geoInputModal").value.trim();
            if (!geoInput) return alert("Introduce al menos un término geográfico.");
            currentGeoTermsAceptacion = geoInput.split(",").map(t => t.trim()).filter(t => t.length > 0);
            
            const btnApply = document.getElementById('btnApplyGeoFromModal');
            try {
                btnApply.disabled = true;
                btnApply.innerText = "Aplicando...";
                await aplicarFiltroAceptacion(); 
                // No cerramos el modal aquí, renderAceptacion se encargará de actualizar el contenido
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                btnApply.disabled = false;
                btnApply.innerText = "Aplicar filtro geográfico";
            }
        };

        // Botón Limpiar (CORREGIDO PARA QUE REALMENTE LIMPIE)
        document.getElementById("btnClearGeoFromModal").onclick = async function() {
            document.getElementById("geoInputModal").value = ""; // Borra el texto del input
            await aplicarFiltroAceptacion(); // Llama a la función que ahora acepta vacíos
        };

        // Botón Descargar INFORME TXT ---
        const btnDl = document.getElementById('btnDownloadAceptacion');
        btnDl.onclick = () => {
            const analysisId = projectSelect.value; // Obtenemos el ID del proyecto seleccionado
            if (!analysisId) return alert('No hay un proyecto seleccionado.');
            
            // Redirigimos a la nueva ruta de descarga que creamos en main.py
            window.location = `/analisis/${analysisId}/aceptacion/download-txt`;
        };
    } // <--- AQUÍ CERRAMOS renderAceptacion

    function getAceptacionColorClass(valor) {
        if (valor >= 75) return "text-success";
        if (valor >= 50) return "text-warning";
        return "text-danger";
    }

    // ==========================================
    // LIMPIEZA DE SEGURIDAD (PANTALLA NEGRA)
    // ==========================================
    const modalEl = document.getElementById('aceptacionModal');
    if (modalEl) {
        modalEl.addEventListener('hidden.bs.modal', () => {
            // Esto elimina cualquier rastro de fondo negro al cerrar
            document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
            document.body.style.overflow = 'auto';
            document.body.style.paddingRight = '0px';
        });
    }

    // ============================================================
    // REDIMENSIONAR GRÁFICAS AL CAMBIAR DE PESTAÑA
    // ============================================================
    // Esto es vital porque las gráficas en pestañas ocultas no tienen tamaño
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(tabEl => {
        tabEl.addEventListener('shown.bs.tab', () => {
            console.log("📏 Pestaña activa, ajustando tamaño de gráficas...");
            Object.values(charts).forEach(chart => {
                if (chart) {
                    chart.resize();
                }
            });
        });
    });

    // Coloca esto al final de tu DOMContentLoaded en analizar_datasets.js
    const cloudContainer = document.getElementById('cloudContainer');
    const cloudModal = new bootstrap.Modal(document.getElementById('vllmCloudModal'));
    const zoomImg = document.getElementById('vllmCloudZoomImg');

    if (cloudContainer) {
        cloudContainer.addEventListener('click', (e) => {
            // Verificamos que lo que se clickeó sea una imagen
            if (e.target.tagName === 'IMG') {
                console.log("🔍 Ampliando nube...");
                zoomImg.src = e.target.src; // Pasamos la imagen al modal
                cloudModal.show();          // Mostramos el modal
            }
        });
    }

}); // <--- AQUÍ CERRAMOS EL DOMContentLoaded