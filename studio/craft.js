const STATUS_COLORS = {
  planned: "#8a8f98",
  studying: "#2f6feb",
  building: "#e6a817",
  checking: "#9a6700",
  ready: "#1a7f37",
  abandoned: "#6e7781",
};

const STATUS_ORDER = {
  ready: 0,
  building: 1,
  checking: 2,
  studying: 3,
  planned: 4,
  abandoned: 5,
};

const STUDIES_URL = "api/pack/halo-re/data/craft/studies.json";

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (k === "style") {
        Object.assign(el.style, v);
      } else {
        el.setAttribute(k, v);
      }
    }
  }
  for (const c of children) {
    if (c === null || c === undefined) continue;
    if (typeof c === "string" || typeof c === "number") {
      el.append(String(c));
    } else {
      el.append(c);
    }
  }
  return el;
}

function css(el, styleObj) {
  Object.assign(el.style, styleObj);
}

function badge(color, text) {
  const dot = h("span", {
    style: {
      display: "inline-block",
      width: "8px",
      height: "8px",
      borderRadius: "999px",
      background: color,
      marginRight: "6px",
      verticalAlign: "middle",
    },
  });
  return h("span", { style: { whiteSpace: "nowrap", marginRight: "10px", display: "inline-flex", alignItems: "center" } }, dot, text);
}

function fetchJson(path) {
  const token = sessionStorage.getItem("halo-studio-token");
  const headers = {};
  if (token) {
    headers["Authorization"] = "Bearer " + token;
  }
  return fetch(path, { headers }).then((r) => {
    if (!r.ok) {
      throw new Error("HTTP " + r.status + " fetching " + path);
    }
    return r.text();
  });
}

function sortStudies(rows) {
  return [...rows].sort((a, b) => {
    const oa = STATUS_ORDER[a.status] ?? 99;
    const ob = STATUS_ORDER[b.status] ?? 99;
    if (oa !== ob) return oa - ob;
    const ta = a.updated ? new Date(a.updated).getTime() : 0;
    const tb = b.updated ? new Date(b.updated).getTime() : 0;
    return tb - ta;
  });
}

function matchesFilters(row, search, statusFilter, modeFilter) {
  if (statusFilter && statusFilter !== "all" && row.status !== statusFilter) return false;
  if (modeFilter && modeFilter !== "all" && row.mode !== modeFilter) return false;
  if (search) {
    const s = search.toLowerCase();
    const fields = [row.study_id, row.target, row.stack, row.agent].filter(Boolean).map((f) => f.toLowerCase());
    if (!fields.some((f) => f.includes(s))) return false;
  }
  return true;
}

function getStudyUrl(id) {
  return "api/pack/halo-re/data/craft/" + id + ".json";
}

function openRawUrl(id) {
  const token = sessionStorage.getItem("halo-studio-token");
  let url = getStudyUrl(id);
  if (token) {
    url = url + "?t=" + encodeURIComponent(token);
  }
  window.open(url);
}

function copyMarkdown(study) {
  let md = "## " + study.study_id + "\n\n";
  const sections = [
    ["Status", study.status],
    ["Mode", study.mode],
    ["Target kind", study.target_kind],
    ["Target", study.target],
    ["Stack requested", study.stack],
    ["Output folder", study.output],
    ["Agent", study.agent],
    ["Notes", study.notes],
  ];
  if (study.check) {
    if (study.check.mismatches !== undefined) {
      sections.push(["Check", study.check.mismatches + " mismatches" + (study.check.note ? ": " + study.check.note : "")]);
    } else if (study.check.note) {
      sections.push(["Check", study.check.note]);
    }
  }
  sections.push(["Created", study.created]);
  sections.push(["Updated", study.updated]);
  for (const [label, value] of sections) {
    if (value) {
      md += "### " + label + "\n" + value + "\n\n";
    }
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(md);
  } else {
    const ta = h("textarea", { style: { position: "absolute", left: "-9999px" } });
    ta.value = md;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  return md;
}

function mount(el, api) {
  const root = h("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      height: "100%",
      minHeight: "0",
      color: "#e6edf3",
      fontSize: "13px",
    },
  });
  el.append(root);

  let studies = [];
  let generated = "";
  let lastText = "";
  let search = "";
  let statusFilter = "all";
  let modeFilter = "all";
  let selectedIndex = -1;
  let currentDetail = null;
  let detailLoading = false;
  let detailError = null;
  let listError = null;
  let listLoading = true;
  let searchFocused = false;

  const header = h("div", {
    style: {
      padding: "12px 16px",
      borderBottom: "1px solid #30363d",
      display: "flex",
      alignItems: "center",
      gap: "12px",
      flexWrap: "wrap",
    },
  });
  root.append(header);

  const title = h("h2", { style: { margin: 0, fontSize: "16px", fontWeight: 600 } }, "Craft studies");
  header.append(title);

  const counts = h("span", { style: { color: "#8b949e", fontSize: "12px" } });
  header.append(counts);

  const generatedLabel = h("span", { style: { color: "#8b949e", fontSize: "12px" } });
  header.append(generatedLabel);

  const refreshBtn = h("button", {
    style: {
      background: "#21262d",
      border: "1px solid #30363d",
      color: "#e6edf3",
      borderRadius: "6px",
      padding: "4px 10px",
      cursor: "pointer",
      fontSize: "12px",
      marginLeft: "auto",
    },
  }, "Refresh");
  header.append(refreshBtn);

  const listWrapper = h("div", {
    style: {
      flex: "1",
      overflow: "auto",
      minHeight: "0",
      display: "flex",
      flexDirection: "column",
    },
  });
  root.append(listWrapper);

  const filterBar = h("div", {
    style: {
      padding: "10px 16px",
      borderBottom: "1px solid #30363d",
      display: "flex",
      gap: "10px",
      alignItems: "center",
      flexWrap: "wrap",
    },
  });
  listWrapper.append(filterBar);

  const searchInput = h("input", {
    type: "text",
    placeholder: "Search studies...",
    style: {
      background: "#0d1117",
      border: "1px solid #30363d",
      color: "#e6edf3",
      borderRadius: "6px",
      padding: "4px 8px",
      fontSize: "12px",
      flex: "1",
      minWidth: "150px",
    },
  });
  searchInput.addEventListener("input", () => {
    search = searchInput.value;
    selectedIndex = -1;
    renderList();
  });
  searchInput.addEventListener("focus", () => { searchFocused = true; });
  searchInput.addEventListener("blur", () => { searchFocused = false; });
  filterBar.append(searchInput);

  const statusSelect = h("select", {
    style: {
      background: "#0d1117",
      border: "1px solid #30363d",
      color: "#e6edf3",
      borderRadius: "6px",
      padding: "4px 8px",
      fontSize: "12px",
    },
  });
  const allStatusOpt = h("option", { value: "all" }, "All statuses");
  statusSelect.append(allStatusOpt);
  for (const s of ["planned", "studying", "building", "checking", "ready", "abandoned"]) {
    statusSelect.append(h("option", { value: s }, s));
  }
  statusSelect.addEventListener("change", () => {
    statusFilter = statusSelect.value;
    selectedIndex = -1;
    renderList();
  });
  filterBar.append(statusSelect);

  const modeSelect = h("select", {
    style: {
      background: "#0d1117",
      border: "1px solid #30363d",
      color: "#e6edf3",
      borderRadius: "6px",
      padding: "4px 8px",
      fontSize: "12px",
    },
  });
  modeSelect.append(h("option", { value: "all" }, "All modes"));
  modeSelect.append(h("option", { value: "clean-room" }, "clean-room"));
  modeSelect.append(h("option", { value: "deep" }, "deep"));
  modeSelect.addEventListener("change", () => {
    modeFilter = modeSelect.value;
    selectedIndex = -1;
    renderList();
  });
  filterBar.append(modeSelect);

  const tableContainer = h("div", { style: { flex: "1", overflow: "auto", minHeight: "0" } });
  listWrapper.append(tableContainer);

  const detailContainer = h("div", {
    style: {
      flex: "1",
      overflow: "auto",
      minHeight: "0",
      padding: "16px",
      display: "none",
    },
  });
  root.append(detailContainer);

  function updateCounts() {
    const ready = studies.filter((s) => s.status === "ready").length;
    const inProgress = studies.filter((s) => ["planned", "studying", "building", "checking"].includes(s.status)).length;
    counts.textContent = studies.length + " studies · " + ready + " ready · " + inProgress + " in progress";
    if (generated) {
      generatedLabel.textContent = "generated " + new Date(generated).toLocaleString();
    }
  }

  function renderList() {
    tableContainer.replaceChildren();
    if (listLoading) {
      tableContainer.append(h("div", { style: { padding: "20px", color: "#8b949e" } }, "Loading studies..."));
      return;
    }
    if (listError) {
      const errDiv = h("div", { style: { padding: "20px", color: "#8b949e" } });
      errDiv.append(h("p", { style: { margin: "0 0 10px" } }, listError));
      const retryBtn = h("button", {
        style: {
          background: "#21262d",
          border: "1px solid #30363d",
          color: "#e6edf3",
          borderRadius: "6px",
          padding: "4px 10px",
          cursor: "pointer",
          fontSize: "12px",
        },
      }, "Retry");
      retryBtn.addEventListener("click", fetchStudies);
      errDiv.append(retryBtn);
      tableContainer.append(errDiv);
      return;
    }
    if (studies.length === 0) {
      tableContainer.append(h("div", { style: { padding: "20px", color: "#8b949e" } }, "No craft studies yet. Record one with tools/craft_studies.py (see the craft-anything-study skill) and it appears here."));
      return;
    }

    const filtered = studies.filter((s) => matchesFilters(s, search, statusFilter, modeFilter));
    if (filtered.length === 0) {
      tableContainer.append(h("div", { style: { padding: "20px", color: "#8b949e" } }, "No studies match the filters."));
      return;
    }

    const sorted = sortStudies(filtered);

    const table = h("table", {
      style: {
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "12px",
      },
      tabindex: "0",
    });

    const thead = h("thead");
    const headerRow = h("tr", {
      style: {
        position: "sticky",
        top: "0",
        background: "#0d1117",
        zIndex: "1",
      },
    });
    for (const col of ["Status", "Mode", "ID", "Target", "Stack", "Agent", "Updated", ""]) {
      headerRow.append(h("th", {
        style: {
          padding: "8px 10px",
          textAlign: "left",
          borderBottom: "1px solid #30363d",
          color: "#8b949e",
          fontWeight: 500,
          fontSize: "11px",
          textTransform: "uppercase",
        },
      }, col));
    }
    thead.append(headerRow);
    table.append(thead);

    const tbody = h("tbody");
    sorted.forEach((study, idx) => {
      const row = h("tr", {
        style: {
          cursor: "pointer",
          borderBottom: "1px solid #30363d",
        },
        "data-idx": idx,
      });
      if (idx === selectedIndex) {
        row.style.background = "rgba(88,166,255,0.16)";
      }
      row.addEventListener("mouseenter", () => {
        if (idx !== selectedIndex) row.style.background = "rgba(88,166,255,0.08)";
      });
      row.addEventListener("mouseleave", () => {
        if (idx !== selectedIndex) row.style.background = "";
      });
      row.addEventListener("click", () => openDetail(study));

      const statusCell = h("td", { style: { padding: "8px 10px" } });
      statusCell.append(badge(STATUS_COLORS[study.status] || "#8b949e", study.status));
      row.append(statusCell);

      const modeCell = h("td", { style: { padding: "8px 10px" } });
      if (study.mode === "deep") {
        modeCell.append(badge("#e6a817", "deep"));
      } else {
        modeCell.append(h("span", { style: { color: "#8b949e" } }, "clean-room"));
      }
      row.append(modeCell);

      const idCell = h("td", {
        style: {
          padding: "8px 10px",
          fontFamily: "ui-monospace, monospace",
          color: "#58a6ff",
          cursor: "pointer",
        },
      }, study.study_id);
      idCell.addEventListener("click", (e) => {
        e.stopPropagation();
        openDetail(study);
      });
      row.append(idCell);

      row.append(h("td", { style: { padding: "8px 10px", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, study.target || ""));
      row.append(h("td", { style: { padding: "8px 10px", maxWidth: "150px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, study.stack || ""));
      row.append(h("td", { style: { padding: "8px 10px", maxWidth: "100px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, study.agent || ""));
      row.append(h("td", {
        style: {
          padding: "8px 10px",
          fontFamily: "ui-monospace, monospace",
          color: "#8b949e",
          fontSize: "11px",
        },
      }, study.updated ? new Date(study.updated).toLocaleString() : ""));

      const actionsCell = h("td", { style: { padding: "8px 10px" } });
      const openBtn = h("button", {
        style: {
          background: "#21262d",
          border: "1px solid #30363d",
          color: "#e6edf3",
          borderRadius: "6px",
          padding: "2px 8px",
          cursor: "pointer",
          fontSize: "11px",
        },
      }, "Open");
      openBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openDetail(study);
      });
      actionsCell.append(openBtn);
      row.append(actionsCell);

      tbody.append(row);
    });
    table.append(tbody);

    table.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, sorted.length - 1);
        renderList();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        renderList();
      } else if (e.key === "Enter" && selectedIndex >= 0) {
        openDetail(sorted[selectedIndex]);
      }
    });

    tableContainer.append(table);
  }

  function openDetail(study) {
    currentDetail = study;
    detailLoading = true;
    detailError = null;
    listWrapper.style.display = "none";
    detailContainer.style.display = "block";
    renderDetail();
    fetchJson(getStudyUrl(study.study_id)).then((text) => {
      const fresh = JSON.parse(text);
      currentDetail = fresh;
      detailLoading = false;
      renderDetail();
    }).catch((err) => {
      detailLoading = false;
      detailError = err.message;
      renderDetail();
    });
  }

  function backToList() {
    currentDetail = null;
    detailLoading = false;
    detailError = null;
    listWrapper.style.display = "flex";
    detailContainer.style.display = "none";
  }

  function renderDetail() {
    detailContainer.replaceChildren();
    if (detailLoading) {
      detailContainer.append(h("div", { style: { color: "#8b949e" } }, "Loading study..."));
      return;
    }
    if (detailError) {
      const errDiv = h("div", { style: { color: "#8b949e" } });
      errDiv.append(h("p", { style: { margin: "0 0 10px" } }, detailError));
      const retryBtn = h("button", {
        style: {
          background: "#21262d",
          border: "1px solid #30363d",
          color: "#e6edf3",
          borderRadius: "6px",
          padding: "4px 10px",
          cursor: "pointer",
          fontSize: "12px",
        },
      }, "Retry");
      retryBtn.addEventListener("click", () => openDetail(currentDetail));
      errDiv.append(retryBtn);
      detailContainer.append(errDiv);
      return;
    }
    if (!currentDetail) return;

    const s = currentDetail;

    const topBar = h("div", {
      style: {
        display: "flex",
        gap: "10px",
        marginBottom: "16px",
        alignItems: "center",
        flexWrap: "wrap",
      },
    });
    const backBtn = h("button", {
      style: {
        background: "#21262d",
        border: "1px solid #30363d",
        color: "#e6edf3",
        borderRadius: "6px",
        padding: "4px 10px",
        cursor: "pointer",
        fontSize: "12px",
      },
    }, "← Back to studies");
    backBtn.addEventListener("click", backToList);
    topBar.append(backBtn);

    const rawBtn = h("button", {
      style: {
        background: "#21262d",
        border: "1px solid #30363d",
        color: "#e6edf3",
        borderRadius: "6px",
        padding: "4px 10px",
        cursor: "pointer",
        fontSize: "12px",
      },
    }, "Open raw JSON");
    rawBtn.addEventListener("click", () => openRawUrl(s.study_id));
    topBar.append(rawBtn);

    const copyBtn = h("button", {
      style: {
        background: "#21262d",
        border: "1px solid #30363d",
        color: "#e6edf3",
        borderRadius: "6px",
        padding: "4px 10px",
        cursor: "pointer",
        fontSize: "12px",
      },
    }, "Copy as markdown");
    copyBtn.addEventListener("click", () => {
      copyMarkdown(s);
      const orig = copyBtn.textContent;
      copyBtn.textContent = "Copied.";
      setTimeout(() => { copyBtn.textContent = orig; }, 2000);
    });
    topBar.append(copyBtn);
    detailContainer.append(topBar);

    const titleRow = h("div", { style: { marginBottom: "12px" } });
    titleRow.append(h("h2", {
      style: {
        margin: "0 0 8px",
        fontSize: "18px",
        fontWeight: 600,
        fontFamily: "ui-monospace, monospace",
      },
    }, s.study_id));
    const badgesRow = h("div", { style: { display: "flex", gap: "4px", flexWrap: "wrap" } });
    badgesRow.append(badge(STATUS_COLORS[s.status] || "#8b949e", s.status));
    if (s.mode === "deep") {
      badgesRow.append(badge("#e6a817", "deep"));
    } else {
      badgesRow.append(h("span", { style: { color: "#8b949e", marginRight: "10px" } }, "clean-room"));
    }
    if (s.target_kind) {
      badgesRow.append(h("span", { style: { color: "#8b949e", marginRight: "10px" } }, s.target_kind));
    }
    titleRow.append(badgesRow);
    detailContainer.append(titleRow);

    const sections = [
      ["Target", s.target, true],
      ["Stack requested", s.stack, false],
      ["Output folder", s.output, true],
      ["Agent", s.agent, false],
      ["Notes", s.notes, true],
    ];
    if (s.check) {
      if (s.check.mismatches !== undefined) {
        sections.push(["Check", s.check.mismatches + " mismatches" + (s.check.note ? ": " + s.check.note : ""), false]);
      } else if (s.check.note) {
        sections.push(["Check", s.check.note, false]);
      }
    }
    sections.push(["Created", s.created, false]);
    sections.push(["Updated", s.updated, false]);

    for (const [label, value, preWrap] of sections) {
      if (!value) continue;
      const section = h("div", { style: { marginBottom: "14px" } });
      section.append(h("div", {
        style: {
          color: "#8b949e",
          fontSize: "11px",
          textTransform: "uppercase",
          marginBottom: "4px",
          fontWeight: 500,
        },
      }, label));
      const content = h("div", {
        style: {
          whiteSpace: preWrap ? "pre-wrap" : "normal",
          wordBreak: "break-word",
        },
      });
      if (label === "Target" || label === "Output folder") {
        content.style.fontFamily = "ui-monospace, monospace";
      }
      content.textContent = value;
      section.append(content);
      detailContainer.append(section);
    }

    const workflow = h("div", {
      style: {
        marginTop: "20px",
        padding: "12px",
        background: "#0d1117",
        border: "1px solid #30363d",
        borderRadius: "6px",
      },
    });
    workflow.append(h("div", {
      style: {
        color: "#8b949e",
        fontSize: "11px",
        textTransform: "uppercase",
        marginBottom: "8px",
        fontWeight: 500,
      },
    }, "Workflow commands"));
    workflow.append(h("div", {
      style: { fontFamily: "ui-monospace, monospace", fontSize: "12px", marginBottom: "6px" },
    }, "craft-anything-cli doctor"));
    workflow.append(h("div", {
      style: { fontFamily: "ui-monospace, monospace", fontSize: "12px" },
    }, "craft-anything-cli rebuild " + (s.target || "<target>") + " \"" + (s.stack || "your stack") + "\""));
    detailContainer.append(workflow);
  }

  async function fetchStudies() {
    listError = null;
    if (!currentDetail) {
      listLoading = true;
      renderList();
    }
    try {
      const text = await fetchJson(STUDIES_URL);
      if (text === lastText && searchFocused && !currentDetail) {
        return;
      }
      lastText = text;
      const data = JSON.parse(text);
      const prevStudies = studies;
      studies = data.rows || [];
      generated = data.generated || "";
      listLoading = false;
      updateCounts();
      if (currentDetail) {
        const stillExists = studies.find((s) => s.study_id === currentDetail.study_id);
        if (stillExists) {
          fetchJson(getStudyUrl(currentDetail.study_id)).then((t) => {
            currentDetail = JSON.parse(t);
            renderDetail();
          }).catch(() => {
            detailError = "Study no longer exists.";
            renderDetail();
          });
        } else {
          detailError = "Study no longer exists.";
          renderDetail();
        }
      } else {
        renderList();
      }
    } catch (err) {
      listError = err.message;
      listLoading = false;
      if (!currentDetail) renderList();
    }
  }

  refreshBtn.addEventListener("click", fetchStudies);

  let pollInterval = setInterval(fetchStudies, 15000);

  let eventSource = null;
  const token = sessionStorage.getItem("halo-studio-token");
  if (token) {
    try {
      eventSource = new EventSource("/api/events?t=" + encodeURIComponent(token));
      eventSource.addEventListener("message", (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.event === "pack_event" && msg.data && msg.data.pack === "halo-re") {
            fetchStudies();
          }
        } catch (_) {}
      });
    } catch (_) {}
  }

  fetchStudies();

  return function cleanup() {
    clearInterval(pollInterval);
    if (eventSource) {
      eventSource.close();
    }
    if (root.parentNode) {
      root.parentNode.removeChild(root);
    }
  };
}

export { mount };
