(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        node.setAttribute(k, String(attrs[k]));
      });
    }
    return node;
  }

  var USER_MEMBERSHIPS = {
    alice: ["proj-alpha", "proj-beta"],
    bob: ["proj-alpha"],
    eve: [],
    admin: ["proj-alpha", "proj-beta", "proj-classified"]
  };

  var KDG_NODES = [
    // Workspaces
    { id: "ws_alpha", label: "Workspace", title: "proj-alpha", project: "proj-alpha", x: 140, y: 65, color: "#38bdf8", props: "{project_id: 'proj-alpha', owner: 'alice'}" },
    { id: "ws_beta", label: "Workspace", title: "proj-beta", project: "proj-beta", x: 440, y: 65, color: "#38bdf8", props: "{project_id: 'proj-beta', owner: 'alice'}" },
    { id: "ws_class", label: "Workspace", title: "proj-classified", project: "proj-classified", x: 740, y: 65, color: "#f43f5e", props: "{project_id: 'proj-classified', owner: 'admin'}" },

    // DataResources
    { id: "dr_alpha_acc", label: "DataResource", title: "accounts (BRONZE)", project: "proj-alpha", x: 140, y: 155, color: "#6366f1", props: "{resource_id: 'accounts', tier: 'BRONZE', format: 'PARQUET', rows: 5000}" },
    { id: "dr_beta_tx", label: "DataResource", title: "transfers (SILVER)", project: "proj-beta", x: 440, y: 155, color: "#6366f1", props: "{resource_id: 'transfers', tier: 'SILVER', format: 'PARQUET', rows: 12400}" },
    { id: "dr_class_sig", label: "DataResource", title: "sigint_Watch (GOLD)", project: "proj-classified", x: 740, y: 155, color: "#6366f1", props: "{resource_id: 'sigint_watch', tier: 'GOLD', format: 'PARQUET', rows: 820}" },

    // DataAttributes
    { id: "da_alpha_id", label: "DataAttribute", title: "acct_id (IDENTIFIER)", project: "proj-alpha", x: 95, y: 250, color: "#a855f7", props: "{name: 'acct_id', physical_type: 'VARCHAR', inferred_type: 'IDENTIFIER', cardinality: 5000}" },
    { id: "da_beta_id", label: "DataAttribute", title: "client_account (ID)", project: "proj-beta", x: 395, y: 250, color: "#a855f7", props: "{name: 'client_account', physical_type: 'VARCHAR', inferred_type: 'IDENTIFIER', cardinality: 4100}" },
    { id: "da_class_id", label: "DataAttribute", title: "target_acct (ID)", project: "proj-classified", x: 695, y: 250, color: "#a855f7", props: "{name: 'target_acct', physical_type: 'VARCHAR', inferred_type: 'IDENTIFIER', cardinality: 820}" },

    // Shared SemanticTaxonomy
    { id: "st_acct", label: "SemanticTaxonomy", title: "Concept: AccountIdentifier", project: "SHARED", x: 265, y: 355, color: "#f59e0b", props: "{concept_id: 'tax_account_id', name: 'AccountIdentifier', category: 'Identifier'}" },

    // GenericEntities
    { id: "ge_alpha_99", label: "GenericEntity", title: "ACCT-99812", project: "proj-alpha", x: 205, y: 250, color: "#10b981", props: "{value: 'ACCT-99812', entity_type: 'Identifier', project_id: 'proj-alpha'}" },
    { id: "ge_beta_99", label: "GenericEntity", title: "ACCT_99812 (Fuzzy)", project: "proj-beta", x: 505, y: 250, color: "#10b981", props: "{value: 'ACCT_99812', entity_type: 'Identifier', project_id: 'proj-beta', confidence: 0.95}" },
    { id: "ge_class_99", label: "GenericEntity", title: "ACCT-99812 (Classified)", project: "proj-classified", x: 785, y: 250, color: "#10b981", props: "{value: 'ACCT-99812', entity_type: 'Identifier', project_id: 'proj-classified'}" }
  ];

  var KDG_EDGES = [
    { from: "ws_alpha", to: "dr_alpha_acc", rel: "OWNS" },
    { from: "ws_beta", to: "dr_beta_tx", rel: "OWNS" },
    { from: "ws_class", to: "dr_class_sig", rel: "OWNS" },
    { from: "dr_alpha_acc", to: "da_alpha_id", rel: "HAS_ATTRIBUTE" },
    { from: "dr_beta_tx", to: "da_beta_id", rel: "HAS_ATTRIBUTE" },
    { from: "dr_class_sig", to: "da_class_id", rel: "HAS_ATTRIBUTE" },
    { from: "dr_alpha_acc", to: "ge_alpha_99", rel: "CONTAINS_ENTITY" },
    { from: "dr_beta_tx", to: "ge_beta_99", rel: "CONTAINS_ENTITY" },
    { from: "dr_class_sig", to: "ge_class_99", rel: "CONTAINS_ENTITY" },
    { from: "da_alpha_id", to: "st_acct", rel: "MAPS_TO" },
    { from: "da_beta_id", to: "st_acct", rel: "MAPS_TO" },
    { from: "da_class_id", to: "st_acct", rel: "MAPS_TO" },
    { from: "ge_alpha_99", to: "ge_beta_99", rel: "SAME_AS (0.95)" },
    { from: "ge_beta_99", to: "ge_class_99", rel: "SAME_AS (1.00)" }
  ];

  var LINEAGE_NODES = [
    { id: "l_bronze", label: "DataResource", title: "raw_accounts (BRONZE)", project: "proj-alpha", x: 130, y: 205, color: "#f59e0b", props: "{resource_id: 'raw_accounts', tier: 'BRONZE', project_id: 'proj-alpha', is_root: true}" },
    { id: "l_run1", label: "PipelineExecution", title: "run_clean_v1 (SUCCESS)", project: "proj-alpha", x: 320, y: 110, color: "#38bdf8", props: "{run_id: 'run-881a', pipeline_id: 'clean_accounts', status: 'SUCCESS', duration_ms: 480}" },
    { id: "l_silver", label: "DataResource", title: "clean_accounts (SILVER)", project: "proj-alpha", x: 470, y: 205, color: "#94a3b8", props: "{resource_id: 'clean_accounts', tier: 'SILVER', project_id: 'proj-alpha'}" },
    { id: "l_run2", label: "PipelineExecution", title: "run_agg_kpi (SUCCESS)", project: "proj-alpha", x: 640, y: 110, color: "#38bdf8", props: "{run_id: 'run-994c', pipeline_id: 'build_gold_kpi', status: 'SUCCESS', duration_ms: 610}" },
    { id: "l_gold", label: "DataResource", title: "gold_kpi (GOLD)", project: "proj-alpha", x: 760, y: 205, color: "#10b981", props: "{resource_id: 'gold_kpi', tier: 'GOLD', project_id: 'proj-alpha'}" }
  ];

  var LINEAGE_EDGES = [
    { from: "l_run1", to: "l_bronze", rel: "CONSUMED" },
    { from: "l_run1", to: "l_silver", rel: "PRODUCED" },
    { from: "l_silver", to: "l_bronze", rel: "DERIVED_FROM" },
    { from: "l_run2", to: "l_silver", rel: "CONSUMED" },
    { from: "l_run2", to: "l_gold", rel: "PRODUCED" },
    { from: "l_gold", to: "l_silver", rel: "DERIVED_FROM" }
  ];

  var ENTITY_OCCURRENCES = {
    "ACCT-99812": [
      { project: "proj-alpha", resource: "accounts (BRONZE)", attr: "acct_id", val: "ACCT-99812", method: "exact (1.00)" },
      { project: "proj-beta", resource: "transfers (SILVER)", attr: "client_account", val: "ACCT_99812", method: "fuzzy_dsu (0.95)" },
      { project: "proj-classified", resource: "sigint_watch (GOLD)", attr: "target_acct", val: "ACCT-99812", method: "exact (1.00)" }
    ],
    "198.51.100.24": [
      { project: "proj-alpha", resource: "firewall_logs (BRONZE)", attr: "src_ip", val: "198.51.100.24", method: "exact (1.00)" },
      { project: "proj-classified", resource: "c2_beacons (GOLD)", attr: "beacon_ip", val: "198.51.100.24", method: "exact (1.00)" }
    ],
    "dr.smith@med-alpha.org": [
      { project: "proj-beta", resource: "clinical_referrals (SILVER)", attr: "physician_email", val: "dr.smith@med-alpha.org", method: "exact (1.00)" }
    ]
  };

  var currentCaller = "alice";
  var currentGraphMode = "ontology";

  function isProjectAllowed(projId, allowedList) {
    if (projId === "SHARED") {
      return allowedList.length > 0;
    }
    return allowedList.indexOf(projId) !== -1;
  }

  function renderGraphSvg() {
    var svg = document.getElementById("kdg-graph-svg");
    var badge = document.getElementById("kdg-visible-badge");
    if (!svg) return;
    svg.replaceChildren();

    svg.appendChild(svgEl("rect", { x: 0, y: 0, width: 880, height: 410, fill: "#050811" }));

    var allowed = USER_MEMBERSHIPS[currentCaller] || [];
    if (badge) {
      badge.textContent = allowed.length + " Member Workspace(s) Visible to '" + currentCaller + "'";
      badge.className = "badge " + (allowed.length > 0 ? "badge-emerald" : "badge-rose");
    }

    var nodes = currentGraphMode === "ontology" ? KDG_NODES : LINEAGE_NODES;
    var edges = currentGraphMode === "ontology" ? KDG_EDGES : LINEAGE_EDGES;

    var nodeMap = {};
    nodes.forEach(function (n) {
      nodeMap[n.id] = n;
    });

    // Draw edges if both endpoints are allowed
    edges.forEach(function (e) {
      var n1 = nodeMap[e.from];
      var n2 = nodeMap[e.to];
      if (!n1 || !n2) return;
      var ok1 = isProjectAllowed(n1.project, allowed);
      var ok2 = isProjectAllowed(n2.project, allowed);
      if (!ok1 || !ok2) return;

      var isSameAs = e.rel.indexOf("SAME_AS") !== -1;
      var line = svgEl("line", {
        x1: n1.x,
        y1: n1.y,
        x2: n2.x,
        y2: n2.y,
        stroke: isSameAs ? "#10b981" : "#334155",
        "stroke-width": isSameAs ? "2.4" : "1.6",
        "stroke-dasharray": isSameAs ? "5,3" : ""
      });
      svg.appendChild(line);

      var midX = (n1.x + n2.x) / 2;
      var midY = (n1.y + n2.y) / 2;
      var edgeLbl = svgEl("text", {
        x: midX,
        y: midY - 4,
        fill: isSameAs ? "#10b981" : "#64748b",
        "font-size": "9.5",
        "font-weight": "700",
        "text-anchor": "middle",
        "font-family": "monospace"
      });
      edgeLbl.textContent = e.rel;
      svg.appendChild(edgeLbl);
    });

    // Draw nodes
    nodes.forEach(function (n) {
      var allowedNode = isProjectAllowed(n.project, allowed);
      if (!allowedNode) {
        // Draw redacted ghost placeholder to visually demonstrate 0% leakage to the operator
        var ghost = svgEl("rect", {
          x: n.x - 68,
          y: n.y - 20,
          width: 136,
          height: 40,
          rx: 7,
          fill: "#090d16",
          stroke: "#1e293b",
          "stroke-dasharray": "3,3"
        });
        var ghostTxt = svgEl("text", {
          x: n.x,
          y: n.y + 4,
          fill: "#334155",
          "font-size": "9.5",
          "text-anchor": "middle",
          "font-family": "monospace"
        });
        ghostTxt.textContent = "[0% TRACE: NON-MEMBER]";
        svg.appendChild(ghost);
        svg.appendChild(ghostTxt);
        return;
      }

      var g = svgEl("g", { cursor: "pointer" });
      var rect = svgEl("rect", {
        x: n.x - 74,
        y: n.y - 22,
        width: 148,
        height: 44,
        rx: 8,
        fill: "#131c31",
        stroke: n.color,
        "stroke-width": "2"
      });
      var lblTop = svgEl("text", {
        x: n.x,
        y: n.y - 5,
        fill: n.color,
        "font-size": "9.5",
        "font-weight": "700",
        "text-anchor": "middle",
        "font-family": "monospace"
      });
      lblTop.textContent = ":" + n.label;

      var lblMain = svgEl("text", {
        x: n.x,
        y: n.y + 11,
        fill: "#f8fafc",
        "font-size": "10.5",
        "font-weight": "700",
        "text-anchor": "middle",
        "font-family": "Inter, sans-serif"
      });
      lblMain.textContent = n.title;

      g.appendChild(rect);
      g.appendChild(lblTop);
      g.appendChild(lblMain);

      g.addEventListener("click", function () {
        var infoEl = document.getElementById("kdg-selected-node-info");
        if (infoEl) {
          infoEl.textContent = "Label: :" + n.label + "\nTitle: " + n.title + "\nProject Scope: " + n.project + "\nProperties: " + n.props;
        }
      });
      svg.appendChild(g);
    });
  }

  function renderEntitySearch() {
    var selectEl = document.getElementById("entity-query-select");
    var cliPreview = document.getElementById("kdg-cli-preview");
    var tbody = document.getElementById("kdg-search-results-body");
    if (!selectEl || !cliPreview || !tbody) return;

    var val = selectEl.value;
    var allowed = USER_MEMBERSHIPS[currentCaller] || [];

    cliPreview.textContent = "$ artemis discover entity --value \"" + val + "\" --fuzzy\n# Caller: " + currentCaller + " | Parameter $member_projects = " + JSON.stringify(allowed);

    var allMatches = ENTITY_OCCURRENCES[val] || [];
    var scopedMatches = allMatches.filter(function (m) {
      return allowed.indexOf(m.project) !== -1;
    });

    tbody.replaceChildren();
    if (scopedMatches.length === 0) {
      var trEmpty = el("tr");
      var tdEmpty = el("td", "", "0 matching entities found in your member projects (Non-member workspaces leave 0% trace).");
      tdEmpty.setAttribute("colspan", "5");
      tdEmpty.style.color = "#94a3b8";
      trEmpty.appendChild(tdEmpty);
      tbody.appendChild(trEmpty);
      return;
    }

    scopedMatches.forEach(function (m) {
      var tr = el("tr");
      var tdProj = el("td");
      tdProj.appendChild(el("span", "badge badge-blue", m.project));
      tr.appendChild(tdProj);
      tr.appendChild(el("td", "arch-node-meta", m.resource));
      tr.appendChild(el("td", "arch-node-meta", m.attr));
      tr.appendChild(el("td", "arch-node-meta", m.val));
      var tdMethod = el("td");
      tdMethod.appendChild(el("span", "badge badge-emerald", m.method));
      tr.appendChild(tdMethod);
      tbody.appendChild(tr);
    });
  }

  function evaluatePatternProfiler() {
    var input = document.getElementById("pattern-test-input");
    var output = document.getElementById("pattern-test-output");
    if (!input || !output) return;

    var sample = input.value.trim();
    var patterns = [
      { name: "UUID", regex: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i },
      { name: "EMAIL", regex: /^[^@\s]+@[^@\s]+\.[^@\s]+$/ },
      { name: "IP_ADDRESS", regex: /^(?:\d{1,3}\.){3}\d{1,3}$/ },
      { name: "URL", regex: /^https?:\/\/[^\s/$.?#].[^\s]*$/i },
      { name: "ISO_TIMESTAMP", regex: /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}/ },
      { name: "HASH (SHA256/MD5)", regex: /^[a-f0-9]{32,64}$/i },
      { name: "COORDINATES", regex: /^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$/ },
      { name: "PHONE", regex: /^\+?[0-9\-\s()]{8,20}$/ },
      { name: "IDENTIFIER", regex: /^[A-Z]{2,6}[-_][0-9A-Z]{3,12}$/i }
    ];

    var matched = "STRING / GENERAL_TEXT";
    var isEntityCandidate = false;
    for (var i = 0; i < patterns.length; i++) {
      if (patterns[i].regex.test(sample)) {
        matched = patterns[i].name;
        isEntityCandidate = true;
        break;
      }
    }

    output.textContent = "Input Value: \"" + sample + "\"\nInferred Pattern Type: " + matched + "\nExtract as :GenericEntity Node: " + (isEntityCandidate ? "YES (Confidence: 1.00)" : "NO (Low-specificity literal)");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var callerSelect = document.getElementById("caller-identity-select");
    if (callerSelect) {
      callerSelect.addEventListener("change", function () {
        currentCaller = callerSelect.value;
        renderGraphSvg();
        renderEntitySearch();
      });
    }

    var btnOntology = document.getElementById("view-mode-ontology");
    var btnLineage = document.getElementById("view-mode-lineage");
    if (btnOntology) {
      btnOntology.addEventListener("click", function () {
        currentGraphMode = "ontology";
        renderGraphSvg();
      });
    }
    if (btnLineage) {
      btnLineage.addEventListener("click", function () {
        currentGraphMode = "lineage";
        renderGraphSvg();
      });
    }

    var entitySelect = document.getElementById("entity-query-select");
    var btnSearch = document.getElementById("btn-run-entity-search");
    if (entitySelect) entitySelect.addEventListener("change", renderEntitySearch);
    if (btnSearch) btnSearch.addEventListener("click", renderEntitySearch);

    var patternInput = document.getElementById("pattern-test-input");
    if (patternInput) {
      patternInput.addEventListener("input", evaluatePatternProfiler);
    }

    renderGraphSvg();
    renderEntitySearch();
    evaluatePatternProfiler();
  });
})();
