document.addEventListener("DOMContentLoaded", () => {
    console.log("🚀 JS de Analizar Datasets cargado (v6 - ScoreOP).");

    const projectSelect      = document.getElementById("projectSelect");
    const resultsPlaceholder = document.getElementById("resultsPlaceholder");
    const chartsContainer    = document.getElementById("chartsContainer");

    const DEFINICIONES_PILARES = {
        "legitimacion":           "Mide si la ciudadanía percibe la medida como válida, legal y socialmente aceptable.",
        "efectividad":            "Evalúa si el público cree que la medida realmente cumple sus objetivos y resuelve el problema.",
        "justicia_equidad":       "Analiza si la política se percibe como justa e igualitaria para todos los sectores sociales.",
        "confianza_institucional": "Refleja el nivel de credibilidad y confianza en los organismos que implementan la medida."
    };

    // ────────────────────────────────────────────────────────
    // VARIABLES GLOBALES
    // ────────────────────────────────────────────────────────
    let rawDataset =[];
    let charts     = {};
    let tagifyInstance          = null;
    let aceptacionModalInstance = null;
    let currentGeoTerms         =[];
    let currentCustomTopic      = "";
    let currentGeoTermsAceptacion = [];

    // Paleta de colores principal
    const COLORS =["#00ced1", "#e8c302", "#ab54f0", "#f34554", "#2d85e5", "#999999"];

    // Paleta ScoreOP (5 categorías: muy pos → muy neg)
    const SCOREOP_COLORS = {
        muy_positivo : "#0a7c4a",
        positivo     : "#0eb26c",
        neutro       : "#adb5bd",
        negativo     : "#f28c8c",
        muy_negativo : "#d8535f"
    };

    // ════════════════════════════════════════════════════════
    // HELPER: extraer datos de la estructura por_plataforma
    // procedente del pandas multiindex to_dict()
    // ════════════════════════════════════════════════════════
    function extractPlatformData(porPlataforma) {
        if (!porPlataforma || typeof porPlataforma !== "object") {
            return { platforms: [], counts: [], means: [], medians: [], comments:[] };
        }

        // Recoger todas las plataformas existentes en cualquier sub-objeto
        const platformSet = new Set();
        Object.values(porPlataforma).forEach(v => {
            if (v && typeof v === "object") Object.keys(v).forEach(k => platformSet.add(k));
        });
        const platforms = Array.from(platformSet);

        // Encontrar claves por coincidencia de substring (robusto ante formatos de tuple-key)
        const allKeys   = Object.keys(porPlataforma);
        const countKey  = allKeys.find(k => k.toLowerCase().includes("count"));
        const meanKey   = allKeys.find(k => k.toLowerCase().includes("mean"));
        const medianKey = allKeys.find(k => k.toLowerCase().includes("median"));
        const commentKey= allKeys.find(k => k.toLowerCase().includes("sum"));

        return {
            platforms,
            counts  : countKey   ? platforms.map(p => porPlataforma[countKey][p]   || 0) :[],
            means   : meanKey    ? platforms.map(p => porPlataforma[meanKey][p]     || 0) :[],
            medians : medianKey  ? platforms.map(p => porPlataforma[medianKey][p]   || 0) :[],
            comments: commentKey ? platforms.map(p => porPlataforma[commentKey][p]  || 0) :[]
        };
    }

    // ════════════════════════════════════════════════════════
    // HELPER: devuelve la clase CSS de color según ScoreOP
    // ════════════════════════════════════════════════════════
    function scoreopColorClass(value) {
        if (value > 100)  return "success";
        if (value > 0)    return "success";   
        if (value === 0)  return "secondary";
        if (value >= -100)return "warning";
        return "danger";
    }

    function scoreopBadgeStyle(value) {
        if (value > 100)  return `background:${SCOREOP_COLORS.muy_positivo};color:#fff;`;
        if (value > 0)    return `background:${SCOREOP_COLORS.positivo};color:#fff;`;
        if (value === 0)  return `background:${SCOREOP_COLORS.neutro};color:#fff;`;
        if (value >= -100)return `background:${SCOREOP_COLORS.negativo};color:#6b1e1e;`;
        return `background:${SCOREOP_COLORS.muy_negativo};color:#fff;`;
    }

    // ════════════════════════════════════════════════════════
    // 1. CARGA DE DATOS
    // ════════════════════════════════════════════════════════
    async function cargarDashboard(analysisId, retryCount = 0) {
        if (!analysisId) return;

        if (retryCount === 0) {
            resultsPlaceholder.classList.remove("d-none");
            resultsPlaceholder.innerHTML = `
                <div class="py-5 text-center">
                    <div class="spinner-border text-primary" style="width:3rem;height:3rem;"></div>
                    <p class="mt-3 fw-bold">Sincronizando resultados del análisis...</p>
                    <small class="text-muted">Preparando visualización, un momento por favor.</small>
                </div>`;
            chartsContainer.classList.add("d-none");
        }

        try {
            console.log(`📡 Intento de carga ${retryCount + 1} para ID: ${analysisId}`);
            const response = await fetch(`/analisis/${analysisId}/dashboard`);
            if (!response.ok) throw new Error(`Servidor no listo (Status: ${response.status})`);

            const data = await response.json();
            if (!data || Object.keys(data).length === 0 || data.error) throw new Error("Datos incompletos");

            document.getElementById("displayProjectName").innerText = data.project_name || "--";
            document.getElementById("displayTemaName").innerText    = data.tema         || "--";
            document.getElementById("displayThemeDescription").innerText = data.desc_tema || "";

            resultsPlaceholder.classList.add("d-none");
            chartsContainer.classList.remove("d-none");

            renderDashboard(data);
            console.log("✅ Dashboard cargado correctamente.");

        } catch (error) {
            console.warn(`⚠️ Reintentando carga (${retryCount + 1}/5): ${error.message}`);
            if (retryCount < 5) {
                setTimeout(() => cargarDashboard(analysisId, retryCount + 1), 3000);
            } else {
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

    // ════════════════════════════════════════════════════════
    // 2. RENDERIZADO PRINCIPAL DEL DASHBOARD
    // ════════════════════════════════════════════════════════
    function renderDashboard(data) {
        if (!data || !data.kpis) {
            console.error("❌ Datos incompletos para el dashboard", data);
            resultsPlaceholder.innerHTML = `<div class="alert alert-warning">El análisis terminó pero los datos aún se están procesando. Por favor, refresca en unos segundos.</div>`;
            return;
        }
        console.log("🎨 Renderizando gráficas...");

        // ScoreOP: objeto raíz
        const scoreop = data.scoreop || { disponible: false };

        // ─── ENCABEZADO ───────────────────────────────────────
        const headerDiv = document.getElementById("projectHeader");
        if (headerDiv) {
            headerDiv.classList.remove("d-none");
            document.getElementById("displayProjectName").innerText     = data.project_name || "Proyecto sin nombre";
            document.getElementById("displayTemaName").innerText        = data.tema         || "No hay un tema definido.";
            document.getElementById("displayThemeDescription").innerText = data.desc_tema   || "No hay descripción disponible.";
        }

        // ══════════════════════════════════════════════════════
        // TAB 1 – PUBLICACIONES
        // ══════════════════════════════════════════════════════

        // KPI: total publicaciones (ScoreOP si disponible, fallback kpis.total)
        try {
            const total = scoreop.disponible ? (scoreop.total_posts || 0) : (data.kpis.total || 0);
            document.getElementById("kpiTotal").innerText = total.toLocaleString("es-ES");
        } catch(e) {}

        // Donut: publicaciones por plataforma
        try {
            if (scoreop.disponible && scoreop.por_plataforma) {
                const platData = extractPlatformData(scoreop.por_plataforma);
                renderChart("volumenRedChart", "doughnut", {
                    labels: platData.platforms,
                    datasets: [{ data: platData.counts, backgroundColor: COLORS, borderWidth: 0 }]
                }, { cutout: "60%" });
            } else {
                // Fallback: datos de menciones originales
                const vol = data.volumen_por_red || {};
                renderChart("volumenRedChart", "doughnut", {
                    labels: Object.keys(vol),
                    datasets:[{ data: Object.values(vol), backgroundColor: COLORS, borderWidth: 0 }]
                }, { cutout: "60%" });
            }
        } catch(e) { console.error("Error Donut Plataforma:", e); }

        // Línea: evolución de actividad en el tiempo
        try {
            const trend  = data.tendencia_global || {};
            const fechas = Object.keys(trend).sort();
            renderChart("tendenciaGlobalVolChart", "line", {
                labels: fechas,
                datasets:[{
                    label: "Actividad de publicaciones",
                    data: fechas.map(f => trend[f]),
                    borderColor: "#2d85e5",
                    backgroundColor: "rgba(45,133,229,0.1)",
                    fill: true,
                    tension: 0.3
                }]
            }, {
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: "Actividad", font: { size: 11, weight: "bold" } } },
                    x: { title: { display: true, text: "Fecha", font: { size: 11, weight: "bold" } } }
                }
            });
        } catch(e) { console.error("Error Trend Actividad:", e); }

        // Barras agrupadas: publicaciones + comentarios por plataforma
        try {
            if (scoreop.disponible && scoreop.por_plataforma) {
                const platData = extractPlatformData(scoreop.por_plataforma);
                const bgColors  = platData.platforms.map((_, i) => COLORS[i % COLORS.length] + "BB");
                const brdColors = platData.platforms.map((_, i) => COLORS[i % COLORS.length]);

                renderChart("tendenciaRedVolChart", "bar", {
                    labels: platData.platforms,
                    datasets:[
                        {
                            label: "Publicaciones",
                            data: platData.counts,
                            backgroundColor: bgColors,
                            borderColor: brdColors,
                            borderWidth: 2,
                            borderRadius: 6,
                            yAxisID: "y"
                        },
                        {
                            label: "Total comentarios recibidos",
                            data: platData.comments,
                            backgroundColor: "rgba(200,200,200,0.4)",
                            borderColor: "#888",
                            borderWidth: 1.5,
                            borderRadius: 6,
                            yAxisID: "y1"
                        }
                    ]
                }, {
                    scales: {
                        y: {
                            type: "linear", position: "left", beginAtZero: true,
                            title: { display: true, text: "Nº publicaciones", font: { size: 11 } }
                        },
                        y1: {
                            type: "linear", position: "right", beginAtZero: true,
                            title: { display: true, text: "Nº comentarios", font: { size: 11 } },
                            grid: { drawOnChartArea: false }
                        },
                        x: { title: { display: true, text: "Plataforma", font: { size: 11 } } }
                    }
                });
            } else {
                // Fallback: línea multi-plataforma por fecha
                const trendRed = data.tendencia_por_red || {};
                const fechasSet = new Set();
                Object.values(trendRed).forEach(r => {
                    if (r.total) Object.keys(r.total).forEach(d => fechasSet.add(d));
                });
                const fechasOrdenadas = Array.from(fechasSet).sort();
                const datasets = Object.keys(trendRed).map((red, i) => ({
                    label: red,
                    data: fechasOrdenadas.map(f => trendRed[red].total[f] || 0),
                    borderColor: COLORS[i % COLORS.length],
                    backgroundColor: "transparent",
                    borderWidth: 2,
                    tension: 0.3
                }));
                renderChart("tendenciaRedVolChart", "line", { labels: fechasOrdenadas, datasets });
            }
        } catch(e) { console.error("Error Barras Plataforma:", e); }


        // ══════════════════════════════════════════════════════
        // TAB 2 – IMPACTO SCOREOP
        // ══════════════════════════════════════════════════════
        try {
            if (scoreop.disponible) {
                renderScoreOP(scoreop);
            } else {
                renderScoreOPNoDisponible();
            }
        } catch(e) { console.error("Error ScoreOP Tab:", e); }


        // ══════════════════════════════════════════════════════
        // TAB 3 – TOPICS Y NUBES
        // ══════════════════════════════════════════════════════
        try {
            const topics    = data.topics ||[];
            const topTopics = topics.sort((a, b) => b.volumen - a.volumen).slice(0, 10);
            renderChart("topicsPieChart", "pie", {
                labels: topTopics.map(t => t.TOPIC),
                datasets:[{ data: topTopics.map(t => t.volumen), backgroundColor: COLORS, borderWidth: 1 }]
            });
            renderTopicsDetail(topics, data.kpis.total);
        } catch(e) { console.error("Error Topics Pie:", e); }

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
                            <img src="data:image/png;base64,${base64Str}" class="img-fluid" style="max-height:150px;">
                        </div>`;
                    cloudContainer.appendChild(colDiv);
                }
            }
        } catch(e) { console.error("Error Nubes:", e); }
    }

    // ════════════════════════════════════════════════════════
    // 3. RENDERIZADO SCOREOP
    // ════════════════════════════════════════════════════════
    function renderScoreOP(scoreop) {
        const stats = scoreop.stats        || {};
        const dist  = scoreop.distribution || {};

        // ── KPIs numéricos ──────────────────────────────────
        const setKpi = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.innerText = (val !== undefined && val !== null) ? val.toFixed(1) : "--";
        };
        setKpi("kpiScoreopMedia",   stats.media);
        setKpi("kpiScoreopMediana", stats.mediana);
        setKpi("kpiScoreopMax",     stats.max);
        setKpi("kpiScoreopMin",     stats.min);

        // ── Inyectar estructura HTML dinámica en #scoreop-content ──
        const contentEl = document.getElementById("scoreop-content");
        if (!contentEl) return;

        contentEl.innerHTML = `
            <!-- Distribución + ScoreOP por plataforma -->
            <div class="row g-4 align-items-stretch mb-4">
                <div class="col-md-4">
                    <div class="card border-0 shadow-sm h-100 rounded-4 p-4">
                        <h6 class="text-dark fw-bold small text-uppercase mb-3">Distribución de impacto</h6>
                        <div style="height:200px;">
                            <canvas id="scoreopDistributionChart"></canvas>
                        </div>
                        <div class="mt-3" id="scoreop-dist-badges"></div>
                        <p class="text-muted small mt-3 mb-0 text-center">
                            Clasifica cada publicación según el nivel de impacto generado en la comunidad.
                        </p>
                    </div>
                </div>
                <div class="col-md-8">
                    <div class="card border-0 shadow-sm h-100 rounded-4 p-4">
                        <h6 class="text-dark fw-bold small text-uppercase mb-3">
                            <i class="bi bi-bar-chart me-2 text-primary"></i>ScoreOP medio por plataforma
                        </h6>
                        <div style="height:220px;">
                            <canvas id="scoreopPlatformChart"></canvas>
                        </div>
                        <p class="text-muted small mt-3 mb-0 text-center">
                            Compara el impacto medio de las publicaciones entre plataformas.
                        </p>
                    </div>
                </div>
            </div>

            <!-- Top / Bottom posts -->
            <div class="bg-light p-3 rounded-3 mb-4 border-start border-4 border-success">
                <h6 class="text-dark fw-bold small text-uppercase mb-0">
                    <i class="bi bi-list-stars me-2"></i>Publicaciones más relevantes
                </h6>
            </div>
            <div class="row g-4">
                <div class="col-md-6">
                    <div class="card border-0 shadow-sm rounded-4 p-4 h-100">
                        <h6 class="text-success fw-bold small text-uppercase mb-3">
                            <i class="bi bi-arrow-up-circle-fill me-2"></i>Mayor impacto positivo
                        </h6>
                        <div id="topPostsContainer" style="max-height:420px;overflow-y:auto;"></div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card border-0 shadow-sm rounded-4 p-4 h-100">
                        <h6 class="text-danger fw-bold small text-uppercase mb-3">
                            <i class="bi bi-arrow-down-circle-fill me-2"></i>Mayor controversia
                        </h6>
                        <div id="bottomPostsContainer" style="max-height:420px;overflow-y:auto;"></div>
                    </div>
                </div>
            </div>
        `;

        // ── Donut distribución ───────────────────────────────
        const distLabels =["Muy positivo", "Positivo", "Neutro", "Negativo", "Muy negativo"];
        const distValues =[
            dist.muy_positivo || 0,
            dist.positivo     || 0,
            dist.neutro       || 0,
            dist.negativo     || 0,
            dist.muy_negativo || 0
        ];
        const distColors = Object.values(SCOREOP_COLORS);

        setTimeout(() => {
            renderChart("scoreopDistributionChart", "doughnut", {
                labels: distLabels,
                datasets:[{ data: distValues, backgroundColor: distColors, borderWidth: 0 }]
            }, {
                cutout: "65%",
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } }
                }
            });

            // Badges bajo el donut
            const badgesEl = document.getElementById("scoreop-dist-badges");
            if (badgesEl) {
                badgesEl.innerHTML = distLabels.map((lbl, i) => `
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <small class="fw-bold" style="color:${distColors[i]};">${lbl}</small>
                        <span class="badge rounded-pill px-2" style="background:${distColors[i]};color:#fff;">${distValues[i]}</span>
                    </div>
                `).join("");
            }

            // ── Bar: ScoreOP medio por plataforma ────────────
            if (scoreop.por_plataforma) {
                const platData = extractPlatformData(scoreop.por_plataforma);
                if (platData.platforms.length > 0) {
                    const bgBars = platData.platforms.map((_, i) => COLORS[i % COLORS.length] + "BB");
                    const brBars = platData.platforms.map((_, i) => COLORS[i % COLORS.length]);

                    renderChart("scoreopPlatformChart", "bar", {
                        labels: platData.platforms,
                        datasets:[{
                            label: "ScoreOP medio",
                            data: platData.means,
                            backgroundColor: bgBars,
                            borderColor: brBars,
                            borderWidth: 2,
                            borderRadius: 6
                        }]
                    }, {
                        plugins: { legend: { display: false } },
                        scales: {
                            y: {
                                beginAtZero: false,
                                title: { display: true, text: "ScoreOP medio", font: { size: 11 } }
                            },
                            x: {
                                title: { display: true, text: "Plataforma", font: { size: 11 } }
                            }
                        }
                    });
                }
            }

            // ── Listas Top / Bottom ──────────────────────────
            renderPostsList("topPostsContainer",    scoreop.top_posts    ||[], "top");
            renderPostsList("bottomPostsContainer", scoreop.bottom_posts ||[], "bottom");

        }, 0); 
    }

    // ── Mensaje cuando ScoreOP no está disponible ────────────
    function renderScoreOPNoDisponible() {
        const contentEl = document.getElementById("scoreop-content");
        if (contentEl) {
            contentEl.innerHTML = `
                <div class="alert alert-info shadow-sm d-flex align-items-start gap-3 p-4 rounded-4">
                    <i class="bi bi-info-circle-fill fs-3 text-info flex-shrink-0 mt-1"></i>
                    <div>
                        <h6 class="fw-bold mb-1">ScoreOP no disponible para este análisis</h6>
                        <p class="mb-0 text-muted small">
                            El archivo <code>scoreop_consolidado.csv</code> no ha sido encontrado en la carpeta de resultados. 
                            Asegúrate de que el módulo de cálculo ScoreOP se ejecutó correctamente.
                        </p>
                    </div>
                </div>`;
        }["kpiScoreopMedia","kpiScoreopMediana","kpiScoreopMax","kpiScoreopMin"].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerText = "--";
        });
    }

    // ════════════════════════════════════════════════════════
    // 4. LISTA DE POSTS (top / bottom)
    // ════════════════════════════════════════════════════════
    function renderPostsList(containerId, posts, type) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (!posts || posts.length === 0) {
            container.innerHTML = '<p class="text-muted small fst-italic">No hay datos disponibles.</p>';
            return;
        }

        const platformBadgeClass = (plat) => {
            const p = (plat || "").toLowerCase();
            if (p.includes("reddit"))   return "bg-warning text-dark";
            if (p.includes("blue"))     return "bg-primary text-white";
            if (p.includes("youtube"))  return "bg-danger text-white";
            return "bg-secondary text-white";
        };

        container.innerHTML = posts.map((post, i) => {
            const score    = post.ScoreOP ?? 0;
            const content  = (post.contenido_post || "Sin contenido").substring(0, 140);
            const truncated = (post.contenido_post || "").length > 140;
            const stance   = post.stance_post || "--";
            const topic    = post.topic       || "";
            const nComent  = post.num_comentarios ?? 0;

            return `
                <div class="post-card p-3 mb-2 border rounded-3 bg-white shadow-sm">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            <span class="badge ${platformBadgeClass(post.plataforma)}" style="font-size:0.65rem;">
                                ${post.plataforma || "--"}
                            </span>
                            ${topic ? `<small class="text-muted fw-bold text-uppercase" style="font-size:0.65rem;">${topic}</small>` : ""}
                        </div>
                        <span class="badge rounded-pill px-2 fw-bold" style="${scoreopBadgeStyle(score)}">
                            ScoreOP: ${score.toFixed(1)}
                        </span>
                    </div>
                    <p class="mb-2 small text-dark" style="line-height:1.45;">
                        ${content}${truncated ? "<span class='text-muted'>…</span>" : ""}
                    </p>
                    <div class="d-flex gap-3 mt-1 flex-wrap">
                        <small class="text-muted">
                            <i class="bi bi-chat-dots me-1"></i>${nComent.toLocaleString("es-ES")} comentarios
                        </small>
                        <small class="text-muted">
                            <i class="bi bi-hand-${type === "top" ? "thumbs-up" : "thumbs-down"} me-1"></i>${stance}
                        </small>
                    </div>
                </div>`;
        }).join("");
    }

    // ════════════════════════════════════════════════════════
    // 5. FUNCIÓN GENÉRICA DE CHART.JS
    // ════════════════════════════════════════════════════════
    function renderChart(id, type, data, options = {}) {
        const ctx = document.getElementById(id);
        if (!ctx) return;
        if (charts[id]) charts[id].destroy();

        const standardScales = {
            y: { beginAtZero: true, title: { display: true, text: "Volumen", font: { size: 11, weight: "bold" } } },
            x: { title: { display: true, text: "Fecha",   font: { size: 11, weight: "bold" } } }
        };

        charts[id] = new Chart(ctx, {
            type,
            data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: type === "line" ? standardScales : {},
                plugins: { legend: { position: "bottom" } },
                ...options
            }
        });
    }

    // ════════════════════════════════════════════════════════
    // 6. TOPICS DETAIL
    // ════════════════════════════════════════════════════════
    function renderTopicsDetail(topics, totalGlobal) {
        const container = document.getElementById("topicsDetailContainer");
        if (!container) return;
        container.innerHTML = "";

        topics.sort((a, b) => b.volumen - a.volumen).forEach(topic => {
            const vol    = topic.volumen || 1;
            const pPos   = parseFloat(((topic.pos || 0) / vol) * 100) || 0;
            const pNeu   = parseFloat(((topic.neu || 0) / vol) * 100) || 0;
            const pNeg   = parseFloat(((topic.neg || 0) / vol) * 100) || 0;
            const pGlobal= parseFloat((vol / totalGlobal) * 100)        || 0;

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
                <div class="progress rounded-pill" style="height:12px;background-color:#f0f0f0;">
                    <div class="progress-bar bg-success"   style="width:${pPos}%"></div>
                    <div class="progress-bar bg-secondary" style="width:${pNeu}%;opacity:0.7;"></div>
                    <div class="progress-bar bg-danger"    style="width:${pNeg}%"></div>
                </div>
                <div class="d-flex justify-content-between mt-1" style="font-size:0.7rem;">
                    <span class="text-success fw-bold">${pPos.toFixed(1)}% Pos</span>
                    <span class="text-muted fw-bold">${pNeu.toFixed(1)}% Neu</span>
                    <span class="text-danger fw-bold">${pNeg.toFixed(1)}% Neg</span>
                </div>`;
            container.appendChild(row);
        });
    }

    // ════════════════════════════════════════════════════════
    // 7. FILTROS GEO + TOPIC
    // ════════════════════════════════════════════════════════
    function initFilters() {
        const geoInput     = document.getElementById("geoFilterInput");
        const btnApplyGeo  = document.getElementById("btnApplyFilter");
        const btnClearGeo  = document.getElementById("btnClearFilter");
        const topicInput   = document.getElementById("topicFilterInput");
        const btnApplyTopic= document.getElementById("btnApplyTopic");
        const btnClearTopic= document.getElementById("btnClearTopic");

        if (geoInput && typeof Tagify !== "undefined" && !tagifyInstance) {
            try {
                tagifyInstance = new Tagify(geoInput, { delimiters: ",", dropdown: { enabled: 0 } });
            } catch(e) { console.warn("Tagify error", e); }
        }

        async function applyFilters() {
            const analysisId = projectSelect.value;
            if (!analysisId) { alert("Selecciona un proyecto."); return; }

            currentGeoTerms = tagifyInstance
                ? tagifyInstance.value.map(t => t.value)
                : geoInput ? geoInput.value.split(",").map(t => t.trim()).filter(t => t) :[];

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
                <small class="text-muted">Recalculando dashboard completo...</small>`;

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
                rawDataset = newData.raw_data ||[];
                renderDashboard(newData);
            } catch (error) {
                console.error("❌ Error filtro:", error);
                resultsPlaceholder.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
            }
        }

        if (btnApplyGeo)  btnApplyGeo.addEventListener("click",  applyFilters);
        if (btnApplyTopic) btnApplyTopic.addEventListener("click", applyFilters);

        if (btnClearGeo) btnClearGeo.addEventListener("click", () => {
            if (tagifyInstance) tagifyInstance.removeAllTags();
            else if (geoInput) geoInput.value = "";
            currentGeoTerms =[];
            currentCustomTopic ? applyFilters() : cargarDashboard(projectSelect.value);
        });

        if (btnClearTopic) btnClearTopic.addEventListener("click", () => {
            if (topicInput) topicInput.value = "";
            currentCustomTopic = "";
            currentGeoTerms.length ? applyFilters() : cargarDashboard(projectSelect.value);
        });
    }

    initFilters();

    // ════════════════════════════════════════════════════════
    // 8. CARGA AUTOMÁTICA POR URL (?project_id=...)
    // ════════════════════════════════════════════════════════
    const urlParams = new URLSearchParams(window.location.search);
    const pid = urlParams.get("project_id");

    if (pid) {
        console.log("🔎 Detectado project_id en URL:", pid);
        if (projectSelect) {
            let option = projectSelect.querySelector(`option[value="${pid}"]`);
            if (!option) {
                option = document.createElement("option");
                option.value = pid;
                option.text  = pid;
                projectSelect.appendChild(option);
            }
            projectSelect.value = pid;
        }
        cargarDashboard(pid);
    }

    projectSelect.addEventListener("change", e => cargarDashboard(e.target.value));

    // ════════════════════════════════════════════════════════
    // 9. INDICADOR DE ACEPTACIÓN
    // ════════════════════════════════════════════════════════
    async function aplicarFiltroAceptacion() {
        const analysisId   = projectSelect.value;
        if (!analysisId) return;
        const geoInputModal = document.getElementById("geoInputModal");
        const rawValue      = geoInputModal ? geoInputModal.value.trim() : "";
        const terms = rawValue.split(",").map(t => t.trim()).filter(t => t.length > 0);
        currentGeoTermsAceptacion = terms;

        const aceptacionContainer = document.getElementById("aceptacionContainer");
        if (aceptacionContainer) {
            aceptacionContainer.innerHTML = `
                <div class="card border-0 shadow-sm p-3 text-center">
                    <div class="spinner-border text-primary mb-2"></div>
                    <div class="fw-bold">Actualizando indicador</div>
                    <small class="text-muted">${terms.length ? terms.join(", ") : "Cargando valores originales..."}</small>
                </div>`;
        }

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
            if (aceptacionContainer) {
                aceptacionContainer.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
            }
        }
    }

    const btnRunAcep         = document.getElementById("btnRunAcep");
    const aceptacionContainer= document.getElementById("aceptacionContainer");

    if (btnRunAcep) {
        btnRunAcep.addEventListener("click", async () => {
            const analysisId = projectSelect.value;
            if (!analysisId) return;
            btnRunAcep.disabled = true;

            if (aceptacionContainer) {
                aceptacionContainer.innerHTML = `
                    <div class="card border-0 shadow-sm p-3 text-center">
                        <div class="spinner-border text-primary mb-2"></div>
                        <div class="fw-bold">Calculando indicador de aceptación</div>
                        <small class="text-muted">
                            ${currentGeoTermsAceptacion.length
                                ? `Filtro activo: ${currentGeoTermsAceptacion.join(", ")}`
                                : "Sin filtro geográfico"}
                        </small>
                    </div>`;
            }

            try {
                const response = await fetch(`/analisis/${analysisId}/aceptacion/filter-geo`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ terms: currentGeoTermsAceptacion })
                });
                if (!response.ok) throw new Error((await response.text()) || "Error ejecutando indicador.");
                const data = await response.json();
                renderAceptacion(data, data.files || {});
            } catch (error) {
                if (aceptacionContainer) {
                    aceptacionContainer.innerHTML = `<div class="alert alert-danger mt-2">${error.message}</div>`;
                }
            } finally {
                btnRunAcep.disabled = false;
            }
        });
    }

    function renderAceptacion(result, files = {}) {
        if (!result) {
            const bodyEl = document.getElementById("aceptacionModalBody");
            if (bodyEl) bodyEl.innerHTML = '<div class="alert alert-warning">No hay datos disponibles.</div>';
            return;
        }

        const valor         = result["Aceptación Global [%]"] ?? 0;
        const interpretacion= result["Interpretación"] ?? "";
        const porPilares    = result["Aceptación por pilar"] || {};

        if (aceptacionContainer) {
            aceptacionContainer.innerHTML = `
                <div class="card border-primary shadow-sm p-3 bg-white rounded-4">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <small class="text-muted text-uppercase fw-bold">Resultado Aceptación</small>
                        <span class="badge ${getAceptacionColorClass(valor).replace("text-", "bg-")}">${valor.toFixed(1)}%</span>
                    </div>
                    <div class="h5 fw-bold mb-1">${interpretacion}</div>
                    <small class="text-muted fst-italic">Basado en ${result["Menciones con juicio de valor"]} menciones relevantes.</small>
                    <button class="btn btn-sm btn-outline-primary mt-3 w-100" onclick="new bootstrap.Modal(document.getElementById('aceptacionModal')).show()">
                        Ver informe detallado
                    </button>
                </div>`;
        }

        const notaMetodologica = `
            <div class="alert alert-info border-0 shadow-sm small mb-4">
                <i class="bi bi-info-circle-fill me-2"></i>
                <strong>Nota metodológica:</strong> Este análisis se basa en <strong>${result["Menciones con juicio de valor"]} menciones</strong> con juicios de valor explícitos.
            </div>`;

        let pillarsHtml = '<div class="row g-3">';
        for (const[p, value] of Object.entries(porPilares)) {
            const percent    = ((value + 1) / 2 * 100) || 0;
            const nombreLimpio = p.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
            const definicion = DEFINICIONES_PILARES[p] || "Análisis de pilar estratégico.";
            pillarsHtml += `
                <div class="col-md-6">
                    <div class="p-3 border rounded-4 bg-white shadow-sm h-100">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="fw-bold mb-0">${nombreLimpio}</h6>
                            <span class="fw-bold ${getAceptacionColorClass(percent)}">${percent.toFixed(1)}%</span>
                        </div>
                        <div class="progress mb-2" style="height:6px;">
                            <div class="progress-bar ${getAceptacionColorClass(percent).replace("text-","bg-")}" style="width:${percent}%"></div>
                        </div>
                        <p class="text-muted mb-0" style="font-size:0.75rem;line-height:1.2;">${definicion}</p>
                    </div>
                </div>`;
        }
        pillarsHtml += "</div>";

        const bodyEl = document.getElementById("aceptacionModalBody");
        if (bodyEl) {
            bodyEl.innerHTML = `
                ${notaMetodologica}
                <div class="text-center mb-4">
                    <div class="display-4 fw-bold ${getAceptacionColorClass(valor)}">${valor.toFixed(1)}%</div>
                    <div class="h5 text-muted">${interpretacion}</div>
                </div>
                <h6 class="text-dark fw-bold small text-uppercase mb-3 border-bottom pb-2">Desglose por Pilares Estratégicos</h6>
                ${pillarsHtml}`;
        }

        const aceptacionModalEl = document.getElementById("aceptacionModal");
        if (!aceptacionModalInstance) {
            aceptacionModalInstance = new bootstrap.Modal(aceptacionModalEl);
        }
        if (!aceptacionModalEl.classList.contains("show")) {
            aceptacionModalInstance.show();
        }

        const btnApplyModal = document.getElementById("btnApplyGeoFromModal");
        if (btnApplyModal) {
            btnApplyModal.onclick = async () => {
                const geoInput = document.getElementById("geoInputModal").value.trim();
                if (!geoInput) return alert("Introduce al menos un término geográfico.");
                currentGeoTermsAceptacion = geoInput.split(",").map(t => t.trim()).filter(t => t.length > 0);
                try {
                    btnApplyModal.disabled  = true;
                    btnApplyModal.innerText = "Aplicando...";
                    await aplicarFiltroAceptacion();
                } catch(err) {
                    alert("Error: " + err.message);
                } finally {
                    btnApplyModal.disabled  = false;
                    btnApplyModal.innerText = "Aplicar filtro geográfico";
                }
            };
        }

        const btnClearModal = document.getElementById("btnClearGeoFromModal");
        if (btnClearModal) {
            btnClearModal.onclick = async () => {
                const inp = document.getElementById("geoInputModal");
                if (inp) inp.value = "";
                await aplicarFiltroAceptacion();
            };
        }

        const btnDl = document.getElementById("btnDownloadAceptacion");
        if (btnDl) {
            btnDl.onclick = () => {
                const analysisId = projectSelect.value;
                if (!analysisId) return alert("No hay un proyecto seleccionado.");
                window.location = `/analisis/${analysisId}/aceptacion/download-txt`;
            };
        }
    }

    function getAceptacionColorClass(valor) {
        if (valor >= 75) return "text-success";
        if (valor >= 50) return "text-warning";
        return "text-danger";
    }

    // ════════════════════════════════════════════════════════
    // 10. LIMPIEZA MODAL BOOTSTRAP (fondo negro)
    // ════════════════════════════════════════════════════════
    const modalEl = document.getElementById("aceptacionModal");
    if (modalEl) {
        modalEl.addEventListener("hidden.bs.modal", () => {
            document.querySelectorAll(".modal-backdrop").forEach(el => el.remove());
            document.body.classList.remove("modal-open");
            document.body.style.overflow    = "auto";
            document.body.style.paddingRight = "0px";
        });
    }

    // ════════════════════════════════════════════════════════
    // 11. REDIMENSIONAR GRÁFICAS AL CAMBIAR PESTAÑA
    // ════════════════════════════════════════════════════════
    document.querySelectorAll("button[data-bs-toggle='tab']").forEach(tabEl => {
        tabEl.addEventListener("shown.bs.tab", () => {
            Object.values(charts).forEach(chart => { if (chart) chart.resize(); });
        });
    });

    // ════════════════════════════════════════════════════════
    // 12. ZOOM EN NUBES DE PALABRAS
    // ════════════════════════════════════════════════════════
    const cloudContainer = document.getElementById("cloudContainer");
    const cloudModal     = new bootstrap.Modal(document.getElementById("vllmCloudModal"));
    const zoomImg        = document.getElementById("vllmCloudZoomImg");

    if (cloudContainer) {
        cloudContainer.addEventListener("click", (e) => {
            if (e.target.tagName === "IMG") {
                zoomImg.src = e.target.src;
                cloudModal.show();
            }
        });
    }

}); // fin DOMContentLoaded