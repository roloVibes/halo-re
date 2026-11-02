// Findings Browser — interactive list/detail view for security findings (halo-re pack)
// Loaded as ES module: import(url) → { mount(el, api) }

// Local DOM helpers (no imports: the host page loads this module directly
// and CSP forbids external code).
function h(tag, props, ...children) {
    const el = document.createElement(tag);
    if (props) {
        for (const [k, v] of Object.entries(props)) {
            if (k === "style") Object.assign(el.style, v);
            else el.setAttribute(k, v);
        }
    }
    for (const c of children) {
        if (c === null || c === undefined) continue;
        el.append(c);
    }
    return el;
}

function css(el, styleObj) {
    Object.assign(el.style, styleObj);
}

function badge(color, text) {
    const wrap = h("span", null);
    css(wrap, { whiteSpace: "nowrap", marginRight: "10px" });
    const dot = h("span", null);
    css(dot, { display: "inline-block", width: "8px", height: "8px",
               borderRadius: "999px", background: color, marginRight: "6px" });
    wrap.append(dot, text);
    return wrap;
}

function fetchJson(path) {
    const headers = {};
    const token = sessionStorage.getItem("halo-studio-token");
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetch(path, { headers }).then(r => {
        if (!r.ok) throw new Error(path + " -> HTTP " + r.status);
        return r.text();
    });
}

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const SEVERITY_COLORS = {
    critical: "#d7263d",
    high: "#f4711f",
    medium: "#e6a817",
    low: "#4a7ba6",
    info: "#8a8f98"
};
const STATE_COLORS = {
    confirmed: "#1a7f37",
    reviewed: "#2f6feb",
    identified: "#9a6700"
};
const LIST_URL = "api/pack/halo-re/data/findings/summary.json";

export function mount(el, api) {
    const state = {
        rows: [],
        engagement: null,
        generated: null,
        filters: { search: "", severity: "all", state: "all", source: "all" },
        selected: -1,
        detailId: null,
        lastJson: null,
        es: null,
        timer: null
    };

    // Root container
    const root = h("div", null);
    css(root, {
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: "0",
        color: "#e6edf3",
        fontSize: "14px",
        lineHeight: "1.5"
    });
    el.appendChild(root);

    // Header strip
    const header = h("div", null);
    css(header, {
        padding: "12px 16px",
        borderBottom: "1px solid #30363d",
        display: "flex",
        alignItems: "center",
        gap: "16px",
        flexWrap: "wrap"
    });
    root.appendChild(header);

    const headerTitle = h("span", null);
    css(headerTitle, { fontWeight: "bold", fontSize: "16px" });
    header.appendChild(headerTitle);

    const headerCounts = h("span", null);
    css(headerCounts, { color: "#8b949e", fontSize: "13px" });
    header.appendChild(headerCounts);

    const headerTime = h("span", null);
    css(headerTime, { color: "#8b949e", fontSize: "12px", fontFamily: "ui-monospace, monospace" });
    header.appendChild(headerTime);

    const refreshBtn = h("button", null, "Refresh");
    css(refreshBtn, {
        background: "#21262d",
        border: "1px solid #30363d",
        color: "#e6edf3",
        borderRadius: "6px",
        padding: "4px 10px",
        cursor: "pointer",
        fontSize: "13px"
    });
    header.appendChild(refreshBtn);

    // Content area
    const content = h("div", null);
    css(content, {
        flex: "1",
        overflow: "auto",
        padding: "16px"
    });
    root.appendChild(content);

    function getToken() {
        return sessionStorage.getItem("halo-studio-token");
    }

    async function loadList() {
        try {
            const json = await fetchJson(LIST_URL);
            if (json === state.lastJson) return;
            state.lastJson = json;
            const data = JSON.parse(json);
            state.rows = data.rows || [];
            state.engagement = data.engagement_id || null;
            state.generated = data.generated || null;
            updateHeader();
            if (state.detailId) {
                refreshDetail(state.detailId);
            } else {
                renderList();
            }
        } catch (e) {
            renderError(e.message);
        }
    }

    function updateHeader() {
        const eng = state.engagement || "no engagement loaded";
        headerTitle.textContent = `Findings — ${eng}`;

        let identified = 0, reviewed = 0, confirmed = 0, terminal = 0;
        for (const r of state.rows) {
            if (r.state === "identified") identified++;
            else if (r.state === "reviewed") reviewed++;
            else if (r.state === "confirmed") confirmed++;
            else terminal++;
        }
        headerCounts.textContent = `${state.rows.length} identified · ${reviewed} reviewed · ${confirmed} confirmed · ${terminal} terminal`;

        if (state.generated) {
            headerTime.textContent = `generated ${state.generated}`;
        } else {
            headerTime.textContent = "";
        }
    }

    function getDistinctSources() {
        const set = new Set();
        for (const r of state.rows) {
            if (r.source) set.add(r.source);
        }
        return Array.from(set).sort();
    }

    function getDistinctStates() {
        const set = new Set();
        for (const r of state.rows) {
            if (r.state) set.add(r.state);
        }
        return Array.from(set).sort();
    }

    function filteredRows() {
        const f = state.filters;
        return state.rows.filter(r => {
            if (f.search) {
                const s = f.search.toLowerCase();
                const id = (r.finding_id || "").toLowerCase();
                const title = (r.title || "").toLowerCase();
                const target = (r.target_ref || "").toLowerCase();
                if (!id.includes(s) && !title.includes(s) && !target.includes(s)) return false;
            }
            if (f.severity !== "all" && r.severity !== f.severity) return false;
            if (f.state !== "all" && r.state !== f.state) return false;
            if (f.source !== "all" && r.source !== f.source) return false;
            return true;
        });
    }

    function sortRows(rows) {
        return rows.slice().sort((a, b) => {
            const aConfirmed = a.state === "confirmed" ? 0 : 1;
            const bConfirmed = b.state === "confirmed" ? 0 : 1;
            if (aConfirmed !== bConfirmed) return aConfirmed - bConfirmed;
            const aSev = SEVERITY_ORDER[a.severity] ?? 99;
            const bSev = SEVERITY_ORDER[b.severity] ?? 99;
            if (aSev !== bSev) return aSev - bSev;
            return (a.finding_id || "").localeCompare(b.finding_id || "");
        });
    }

    function renderList() {
        content.replaceChildren();

        // Filter bar
        const filterBar = h("div", null);
        css(filterBar, {
            display: "flex",
            gap: "8px",
            marginBottom: "12px",
            flexWrap: "wrap",
            alignItems: "center"
        });
        content.appendChild(filterBar);

        const searchInput = h("input", null);
        searchInput.type = "text";
        searchInput.placeholder = "Search ID, title, target...";
        searchInput.value = state.filters.search;
        css(searchInput, {
            background: "#0d1117",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "6px 10px",
            fontSize: "13px",
            minWidth: "200px"
        });
        searchInput.addEventListener("input", () => {
            state.filters.search = searchInput.value;
            state.selected = -1;
            renderList();
        });
        filterBar.appendChild(searchInput);

        // Severity select
        const sevSelect = h("select", null);
        css(sevSelect, {
            background: "#0d1117",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "6px 8px",
            fontSize: "13px"
        });
        const sevOptions = ["all", "critical", "high", "medium", "low", "info"];
        for (const s of sevOptions) {
            const opt = h("option", null, s === "all" ? "All severities" : s);
            opt.value = s;
            if (state.filters.severity === s) opt.selected = true;
            sevSelect.appendChild(opt);
        }
        sevSelect.addEventListener("change", () => {
            state.filters.severity = sevSelect.value;
            state.selected = -1;
            renderList();
        });
        filterBar.appendChild(sevSelect);

        // State select
        const stateSelect = h("select", null);
        css(stateSelect, {
            background: "#0d1117",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "6px 8px",
            fontSize: "13px"
        });
        const allStates = ["all", "identified", "reviewed", "confirmed", ...getDistinctStates().filter(s => !["identified", "reviewed", "confirmed"].includes(s))];
        for (const s of allStates) {
            const opt = h("option", null, s === "all" ? "All states" : s);
            opt.value = s;
            if (state.filters.state === s) opt.selected = true;
            stateSelect.appendChild(opt);
        }
        stateSelect.addEventListener("change", () => {
            state.filters.state = stateSelect.value;
            state.selected = -1;
            renderList();
        });
        filterBar.appendChild(stateSelect);

        // Source select
        const srcSelect = h("select", null);
        css(srcSelect, {
            background: "#0d1117",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "6px 8px",
            fontSize: "13px"
        });
        const allSources = ["all", ...getDistinctSources()];
        for (const s of allSources) {
            const opt = h("option", null, s === "all" ? "All sources" : s);
            opt.value = s;
            if (state.filters.source === s) opt.selected = true;
            srcSelect.appendChild(opt);
        }
        srcSelect.addEventListener("change", () => {
            state.filters.source = srcSelect.value;
            state.selected = -1;
            renderList();
        });
        filterBar.appendChild(srcSelect);

        // Empty states
        if (!state.engagement) {
            renderEmpty("No engagement loaded. Start an analysis engagement and run the findings view — the tab fills as findings land.");
            return;
        }
        if (state.rows.length === 0) {
            renderEmpty("No findings yet. They appear here the moment one is recorded.");
            return;
        }

        const filtered = filteredRows();
        if (filtered.length === 0) {
            renderEmpty("No findings match the filters.");
            return;
        }

        const sorted = sortRows(filtered);

        // Table
        const table = h("table", null);
        table.tabIndex = 0;
        css(table, {
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "13px"
        });
        content.appendChild(table);

        // Header row
        const thead = h("thead", null);
        table.appendChild(thead);
        const headerRow = h("tr", null);
        thead.appendChild(headerRow);
        const headerCells = ["Severity", "State", "ID", "Title", "Binary", "Function", "Source", "Updated", ""];
        for (const text of headerCells) {
            const th = h("th", null, text);
            css(th, {
                padding: "8px",
                textAlign: "left",
                borderBottom: "1px solid #30363d",
                position: "sticky",
                top: "0",
                background: "#0d1117",
                color: "#8b949e",
                fontWeight: "bold",
                fontSize: "12px",
                textTransform: "uppercase",
                letterSpacing: "0.05em"
            });
            headerRow.appendChild(th);
        }

        // Body
        const tbody = h("tbody", null);
        table.appendChild(tbody);

        for (let i = 0; i < sorted.length; i++) {
            const r = sorted[i];
            const tr = h("tr", null);
            tr.dataset.index = i;
            tr.dataset.id = r.finding_id;
            css(tr, {
                cursor: "pointer",
                padding: "4px 8px"
            });
            if (state.selected === i) {
                css(tr, { background: "rgba(88,166,255,0.16)" });
            }
            tr.addEventListener("mouseenter", () => {
                if (state.selected !== i) {
                    css(tr, { background: "rgba(88,166,255,0.08)" });
                }
            });
            tr.addEventListener("mouseleave", () => {
                if (state.selected !== i) {
                    css(tr, { background: "transparent" });
                }
            });
            tr.addEventListener("click", () => {
                openDetail(r.finding_id);
            });
            tbody.appendChild(tr);

            // Severity cell
            const sevCell = h("td", null);
            css(sevCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            if (r.severity) {
                sevCell.appendChild(badge(SEVERITY_COLORS[r.severity] || "#6e7781", r.severity));
            }
            tr.appendChild(sevCell);

            // State cell
            const stateCell = h("td", null);
            css(stateCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            if (r.state) {
                const color = STATE_COLORS[r.state] || "#6e7781";
                stateCell.appendChild(badge(color, r.state));
            }
            tr.appendChild(stateCell);

            // ID cell (link-styled)
            const idCell = h("td", null);
            css(idCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            const idLink = h("span", null, r.finding_id || "");
            css(idLink, {
                color: "#58a6ff",
                cursor: "pointer",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px"
            });
            idLink.addEventListener("click", (e) => {
                e.stopPropagation();
                openDetail(r.finding_id);
            });
            idCell.appendChild(idLink);
            tr.appendChild(idCell);

            // Title cell
            const titleCell = h("td", null, r.title || "");
            css(titleCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            tr.appendChild(titleCell);

            // Binary cell
            const binaryCell = h("td", null, r.binary || "");
            css(binaryCell, {
                padding: "4px 8px",
                borderBottom: "1px solid #30363d",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                color: "#8b949e"
            });
            tr.appendChild(binaryCell);

            // Function cell
            const funcCell = h("td", null, r.function || "");
            css(funcCell, {
                padding: "4px 8px",
                borderBottom: "1px solid #30363d",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                color: "#8b949e"
            });
            tr.appendChild(funcCell);

            // Source cell
            const srcCell = h("td", null, r.source || "");
            css(srcCell, { padding: "4px 8px", borderBottom: "1px solid #30363d", color: "#8b949e" });
            tr.appendChild(srcCell);

            // Updated cell
            const updatedCell = h("td", null, r.updated || "");
            css(updatedCell, {
                padding: "4px 8px",
                borderBottom: "1px solid #30363d",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                color: "#8b949e"
            });
            tr.appendChild(updatedCell);

            // Actions cell
            const actionsCell = h("td", null);
            css(actionsCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            const openBtn = h("button", null, "Open");
            css(openBtn, {
                background: "#21262d",
                border: "1px solid #30363d",
                color: "#e6edf3",
                borderRadius: "6px",
                padding: "2px 8px",
                cursor: "pointer",
                fontSize: "12px"
            });
            openBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                openDetail(r.finding_id);
            });
            actionsCell.appendChild(openBtn);
            tr.appendChild(actionsCell);
        }

        // Keyboard navigation
        table.addEventListener("keydown", (e) => {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                if (state.selected < sorted.length - 1) {
                    state.selected++;
                    renderList();
                }
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (state.selected > 0) {
                    state.selected--;
                    renderList();
                }
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (state.selected >= 0 && state.selected < sorted.length) {
                    openDetail(sorted[state.selected].finding_id);
                }
            } else if (e.key === "Escape") {
                e.preventDefault();
                state.detailId = null;
                renderList();
            }
        });
    }

    function renderEmpty(msg) {
        const div = h("div", null, msg);
        css(div, {
            color: "#8b949e",
            padding: "32px",
            textAlign: "center",
            fontSize: "14px"
        });
        content.appendChild(div);
    }

    function renderError(msg) {
        const div = h("div", null);
        css(div, {
            color: "#d7263d",
            padding: "32px",
            textAlign: "center"
        });
        const msgSpan = h("span", null, `Error loading findings: ${msg}`);
        div.appendChild(msgSpan);
        const retryBtn = h("button", null, "Retry");
        css(retryBtn, {
            background: "#21262d",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "4px 10px",
            cursor: "pointer",
            marginTop: "12px"
        });
        retryBtn.addEventListener("click", loadList);
        div.appendChild(retryBtn);
        content.appendChild(div);
    }

    async function openDetail(id) {
        state.detailId = id;
        state.selected = -1;
        await renderDetail(id);
    }

    async function renderDetail(id) {
        content.replaceChildren();

        // Back and raw buttons
        const btnRow = h("div", null);
        css(btnRow, {
            display: "flex",
            gap: "8px",
            marginBottom: "16px"
        });
        content.appendChild(btnRow);

        const backBtn = h("button", null, "← Back to findings");
        css(backBtn, {
            background: "#21262d",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "4px 10px",
            cursor: "pointer"
        });
        backBtn.addEventListener("click", () => {
            state.detailId = null;
            renderList();
        });
        btnRow.appendChild(backBtn);

        const rawBtn = h("button", null, "Open raw JSON");
        css(rawBtn, {
            background: "#21262d",
            border: "1px solid #30363d",
            color: "#e6edf3",
            borderRadius: "6px",
            padding: "4px 10px",
            cursor: "pointer"
        });
        rawBtn.addEventListener("click", () => {
            const token = getToken();
            let url = `api/pack/halo-re/data/findings/${id}.json`;
            if (token) {
                url += `?t=${encodeURIComponent(token)}`;
            }
            window.open(url, "_blank");
        });
        btnRow.appendChild(rawBtn);

        try {
            const json = await fetchJson(`api/pack/halo-re/data/findings/${id}.json`);
            const data = JSON.parse(json);
            const finding = data.finding || {};
            const displayState = data.display_state || finding.status || "";
            const severity = data.severity || finding.severity || "";

            // Title
            const titleEl = h("h2", null, finding.title || "Untitled finding");
            css(titleEl, {
                fontSize: "20px",
                fontWeight: "bold",
                margin: "0 0 8px 0"
            });
            content.appendChild(titleEl);

            // Badges
            const badgeRow = h("div", null);
            css(badgeRow, {
                display: "flex",
                gap: "8px",
                marginBottom: "12px",
                flexWrap: "wrap"
            });
            content.appendChild(badgeRow);

            if (severity) {
                badgeRow.appendChild(badge(SEVERITY_COLORS[severity] || "#6e7781", severity));
            }
            if (displayState) {
                badgeRow.appendChild(badge(STATE_COLORS[displayState] || "#6e7781", displayState));
            }
            if (finding.source) {
                badgeRow.appendChild(badge("#6e7781", finding.source));
            }

            // Meta line
            const metaLine = h("div", null);
            css(metaLine, {
                color: "#8b949e",
                fontSize: "13px",
                marginBottom: "16px",
                fontFamily: "ui-monospace, monospace"
            });
            const parts = [];
            if (finding.finding_id) parts.push(`ID: ${finding.finding_id}`);
            if (finding.engagement_id) parts.push(`Engagement: ${finding.engagement_id}`);
            if (finding.target_ref) parts.push(`Target: ${finding.target_ref}`);
            if (finding.binary) parts.push(`binary ${finding.binary}`);
            if (finding.function) parts.push(`function ${finding.function}`);
            if (finding.status) parts.push(`Status: ${finding.status}`);
            metaLine.textContent = parts.join(" · ");
            content.appendChild(metaLine);

            // Sections
            if (finding.description) {
                addSection("Description", finding.description, true);
            }
            if (finding.expected_behavior) {
                addSection("Expected behavior", finding.expected_behavior, true);
            }
            if (finding.observed_behavior) {
                addSection("Observed behavior", finding.observed_behavior, true);
            }
            if (finding.impact) {
                addSection("Impact", finding.impact, true);
            }
            if (finding.remediation) {
                addSection("Remediation", finding.remediation, true);
            }
            if (finding.prerequisites && finding.prerequisites.length > 0) {
                addListSection("Prerequisites", finding.prerequisites);
            }
            if (finding.reproduction) {
                addReproductionSection(finding.reproduction);
            }
            if (finding.validation) {
                addValidationSection(finding.validation);
            }
            if (finding.reviewer_decision) {
                addReviewerSection(finding.reviewer_decision);
            }
            if (data.evidence_rows && data.evidence_rows.length > 0) {
                addEvidenceSection(data.evidence_rows);
            }
            if (finding.audit_history && finding.audit_history.length > 0) {
                addAuditSection(finding.audit_history);
            }
            if (finding.technique_ids && finding.technique_ids.length > 0) {
                addTechniqueSection(finding.technique_ids);
            }

            // Copy as markdown button
            const copyBtn = h("button", null, "Copy as markdown");
            css(copyBtn, {
                background: "#21262d",
                border: "1px solid #30363d",
                color: "#e6edf3",
                borderRadius: "6px",
                padding: "4px 10px",
                cursor: "pointer",
                marginTop: "16px"
            });
            copyBtn.addEventListener("click", () => {
                const md = markdownOf(finding, displayState, severity);
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(md).then(() => {
                        showCopiedFeedback(copyBtn);
                    });
                } else {
                    const ta = h("textarea", null, md);
                    ta.style.position = "fixed";
                    ta.style.left = "-9999px";
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand("copy");
                    document.body.removeChild(ta);
                    showCopiedFeedback(copyBtn);
                }
            });
            content.appendChild(copyBtn);

        } catch (e) {
            renderError(`Failed to load finding ${id}: ${e.message}`);
        }
    }

    function addSection(title, text, prewrap) {
        const titleEl = h("h3", null, title);
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const body = h("div", null, text);
        css(body, {
            marginBottom: "12px",
            whiteSpace: prewrap ? "pre-wrap" : "normal"
        });
        content.appendChild(body);
    }

    function addListSection(title, items) {
        const titleEl = h("h3", null, title);
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const ul = h("ul", null);
        css(ul, { margin: "0 0 12px 0", paddingLeft: "20px" });
        for (const item of items) {
            const li = h("li", null, item);
            ul.appendChild(li);
        }
        content.appendChild(ul);
    }

    function addReproductionSection(repro) {
        const titleEl = h("h3", null, "Reproduction");
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        if (repro.steps && repro.steps.length > 0) {
            const ol = h("ol", null);
            css(ol, { margin: "0 0 8px 0", paddingLeft: "20px" });
            for (const step of repro.steps) {
                const li = h("li", null, step);
                ol.appendChild(li);
            }
            content.appendChild(ol);
        }
        if (repro.environment_notes) {
            const notes = h("div", null, `Environment: ${repro.environment_notes}`);
            css(notes, { color: "#8b949e", fontSize: "13px", marginBottom: "12px" });
            content.appendChild(notes);
        }
    }

    function addValidationSection(val) {
        const titleEl = h("h3", null, "Validation");
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const div = h("div", null);
        css(div, { marginBottom: "12px" });
        if (val.status) {
            div.appendChild(h("div", null, `Status: ${val.status}`));
        }
        if (val.validator_ref) {
            div.appendChild(h("div", null, `Validator: ${val.validator_ref}`));
        }
        if (val.independent !== undefined) {
            div.appendChild(h("div", null, `Independent: ${val.independent ? "yes" : "no"}`));
        }
        if (val.record_ref) {
            div.appendChild(h("div", null, `Record: ${val.record_ref}`));
        }
        content.appendChild(div);
    }

    function addReviewerSection(decision) {
        const titleEl = h("h3", null, "Reviewer decision");
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const div = h("div", null);
        css(div, { marginBottom: "12px" });
        if (decision.decision) {
            div.appendChild(h("div", null, `Decision: ${decision.decision}`));
        }
        if (decision.confidence) {
            div.appendChild(h("div", null, `Confidence: ${decision.confidence}`));
        }
        if (decision.severity_rationale) {
            div.appendChild(h("div", null, `Severity rationale: ${decision.severity_rationale}`));
        }
        if (decision.rationale) {
            div.appendChild(h("div", null, `Rationale: ${decision.rationale}`));
        }
        if (decision.evidence_refs && decision.evidence_refs.length > 0) {
            const ul = h("ul", null);
            css(ul, { margin: "4px 0 0 0", paddingLeft: "20px" });
            for (const ref of decision.evidence_refs) {
                const li = h("li", null, ref);
                ul.appendChild(li);
            }
            div.appendChild(ul);
        }
        content.appendChild(div);
    }

    function addEvidenceSection(rows) {
        const titleEl = h("h3", null, "Evidence");
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const table = h("table", null);
        css(table, {
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "12px",
            marginBottom: "12px"
        });
        content.appendChild(table);

        const thead = h("thead", null);
        table.appendChild(thead);
        const headerRow = h("tr", null);
        thead.appendChild(headerRow);
        for (const text of ["Seq", "Ledger ref", "Kind", "Actor", "Action", "Artifact", ""]) {
            const th = h("th", null, text);
            css(th, {
                padding: "6px 8px",
                textAlign: "left",
                borderBottom: "1px solid #30363d",
                color: "#8b949e",
                fontWeight: "bold"
            });
            headerRow.appendChild(th);
        }

        const tbody = h("tbody", null);
        table.appendChild(tbody);
        for (const row of rows) {
            const tr = h("tr", null);
            tbody.appendChild(tr);

            const seqCell = h("td", null, row.seq != null ? String(row.seq) : "");
            css(seqCell, { padding: "4px 8px", borderBottom: "1px solid #30363d", fontFamily: "ui-monospace, monospace" });
            tr.appendChild(seqCell);

            const ledgerCell = h("td", null, row.ledger_ref || "");
            css(ledgerCell, { padding: "4px 8px", borderBottom: "1px solid #30363d", fontFamily: "ui-monospace, monospace" });
            tr.appendChild(ledgerCell);

            const kindCell = h("td", null, row.kind || "");
            css(kindCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            tr.appendChild(kindCell);

            const actorCell = h("td", null, row.actor || "");
            css(actorCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            tr.appendChild(actorCell);

            const actionCell = h("td", null, row.action || "");
            css(actionCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            tr.appendChild(actionCell);

            const artifactCell = h("td", null, row.artifact_sha256 ? row.artifact_sha256.substring(0, 12) + "…" : "");
            css(artifactCell, { padding: "4px 8px", borderBottom: "1px solid #30363d", fontFamily: "ui-monospace, monospace" });
            tr.appendChild(artifactCell);

            const unresolvedCell = h("td", null);
            css(unresolvedCell, { padding: "4px 8px", borderBottom: "1px solid #30363d" });
            if (row.unresolved) {
                unresolvedCell.appendChild(badge("#d7263d", "unresolved"));
            }
            tr.appendChild(unresolvedCell);
        }
    }

    function addAuditSection(history) {
        const titleEl = h("h3", null, "Audit history");
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const div = h("div", null);
        css(div, { marginBottom: "12px" });
        for (const entry of history) {
            const line = h("div", null);
            css(line, {
                marginBottom: "4px",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px"
            });
            const parts = [];
            if (entry.timestamp) parts.push(entry.timestamp);
            if (entry.actor) parts.push(`— ${entry.actor}`);
            if (entry.action) parts.push(`— ${entry.action}`);
            if (entry.detail) parts.push(`— ${entry.detail}`);
            line.textContent = parts.join(" ");
            div.appendChild(line);
        }
        content.appendChild(div);
    }

    function addTechniqueSection(ids) {
        const titleEl = h("h3", null, "Technique IDs");
        css(titleEl, {
            color: "#8b949e",
            fontSize: "12px",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            margin: "12px 0 4px 0"
        });
        content.appendChild(titleEl);

        const row = h("div", null);
        css(row, {
            display: "flex",
            gap: "6px",
            flexWrap: "wrap",
            marginBottom: "12px"
        });
        for (const id of ids) {
            const chip = h("span", null, id);
            css(chip, {
                background: "#21262d",
                border: "1px solid #30363d",
                borderRadius: "12px",
                padding: "2px 8px",
                fontSize: "12px",
                fontFamily: "ui-monospace, monospace"
            });
            row.appendChild(chip);
        }
        content.appendChild(row);
    }

    function showCopiedFeedback(btn) {
        const original = btn.textContent;
        btn.textContent = "Copied.";
        setTimeout(() => {
            btn.textContent = original;
        }, 2000);
    }

    function markdownOf(finding, displayState, severity) {
        let md = `## ${finding.finding_id || "unknown"} — ${finding.title || "Untitled"}\n\n`;
        const badges = [];
        if (severity) badges.push(severity);
        if (displayState) badges.push(displayState);
        if (finding.source) badges.push(finding.source);
        if (badges.length > 0) {
            md += badges.join(" · ") + "\n\n";
        }
        if (finding.binary) {
            md += `binary ${finding.binary}\n\n`;
        }
        if (finding.function) {
            md += `function ${finding.function}\n\n`;
        }
        if (finding.description) {
            md += `### Description\n${finding.description}\n\n`;
        }
        if (finding.expected_behavior) {
            md += `### Expected behavior\n${finding.expected_behavior}\n\n`;
        }
        if (finding.observed_behavior) {
            md += `### Observed behavior\n${finding.observed_behavior}\n\n`;
        }
        if (finding.impact) {
            md += `### Impact\n${finding.impact}\n\n`;
        }
        if (finding.remediation) {
            md += `### Remediation\n${finding.remediation}\n\n`;
        }
        if (finding.prerequisites && finding.prerequisites.length > 0) {
            md += "### Prerequisites\n";
            for (const p of finding.prerequisites) {
                md += `- ${p}\n`;
            }
            md += "\n";
        }
        if (finding.reproduction && finding.reproduction.steps && finding.reproduction.steps.length > 0) {
            md += "### Reproduction\n";
            for (let i = 0; i < finding.reproduction.steps.length; i++) {
                md += `${i + 1}. ${finding.reproduction.steps[i]}\n`;
            }
            if (finding.reproduction.environment_notes) {
                md += `\nEnvironment: ${finding.reproduction.environment_notes}\n`;
            }
            md += "\n";
        }
        return md;
    }

    async function refreshDetail(id) {
        try {
            const json = await fetchJson(`api/pack/halo-re/data/findings/${id}.json`);
            const data = JSON.parse(json);
            if (data.finding) {
                renderDetail(id);
            } else {
                state.detailId = null;
                renderList();
            }
        } catch (e) {
            // Finding may have been deleted
            state.detailId = null;
            renderList();
        }
    }

    // Live updates
    function startLiveUpdates() {
        state.timer = setInterval(loadList, 15000);

        const token = getToken();
        if (token) {
            try {
                state.es = new EventSource(`/api/events?t=${encodeURIComponent(token)}`);
                state.es.addEventListener("message", (e) => {
                    try {
                        const msg = JSON.parse(e.data);
                        if (msg.event === "pack_event" && msg.data && msg.data.pack === "halo-re") {
                            loadList();
                        }
                    } catch (err) {
                        // Ignore parse errors
                    }
                });
            } catch (err) {
                // EventSource not available or failed
            }
        }
    }

    // Initial load
    refreshBtn.addEventListener("click", loadList);
    loadList();
    startLiveUpdates();

    // Cleanup function
    return () => {
        if (state.timer) clearInterval(state.timer);
        if (state.es) state.es.close();
        el.removeChild(root);
    };
}