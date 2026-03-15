/**
 * ZAYA Web Application Widget — embeddable in Zendesk, Salesforce, Jira, Notion, HR, etc.
 * Usage: ZAYA.init({ apiBase, apiKey?, tenantId, namespace, appType }); ZAYA.show(context);
 */
(function (global) {
  "use strict";

  var config = {
    apiBase: "",
    apiKey: "",
    tenantId: "default",
    namespace: "main",
    appType: "custom",
  };

  var root = null;
  var panel = null;
  var floatBtn = null;

  function escapeHtml(s) {
    if (s == null) return "";
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function getRoot() {
    if (root) return root;
    root = document.createElement("div");
    root.id = "zaya-widget-root";
    document.body.appendChild(root);
    return root;
  }

  function getPanel() {
    if (panel) return panel;
    var r = getRoot();
    panel = document.createElement("div");
    panel.className = "zaya-panel";
    panel.id = "zaya-panel";
    panel.innerHTML =
      '<div class="zaya-panel-header">' +
      '  <h2 id="zaya-panel-title">ZAYA</h2>' +
      '  <button class="zaya-panel-close" id="zaya-panel-close" aria-label="Close">&times;</button>' +
      "</div>" +
      '<div class="zaya-panel-body" id="zaya-panel-body"></div>' +
      '<div class="zaya-chat-input-wrap" id="zaya-chat-wrap">' +
      '  <input type="text" class="zaya-chat-input" id="zaya-chat-input" placeholder="Ask ZAYA anything…">' +
      "</div>";
    r.appendChild(panel);
    document.getElementById("zaya-panel-close").addEventListener("click", function () {
      panel.classList.remove("zaya-open");
    });
    document.getElementById("zaya-chat-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") sendChat();
    });
    return panel;
  }

  function showLoading() {
    var body = document.getElementById("zaya-panel-body");
    if (!body) return;
    body.innerHTML =
      '<div class="zaya-loading">' +
      '  <div class="zaya-spinner"></div>' +
      '  <p style="margin-top:12px">ZAYA is thinking…</p>' +
      "</div>";
  }

  function api(method, path, body) {
    var base = (config.apiBase || "").replace(/\/$/, "");
    var url = base + path;
    var headers = { "Content-Type": "application/json" };
    if (config.apiKey) headers["Authorization"] = "Bearer " + config.apiKey;
    return fetch(url, {
      method: method,
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status + " " + r.statusText);
      return r.json();
    });
  }

  function renderSupport(data) {
    var html = "";
    var rp = data.relevant_policy;
    if (rp) {
      html += '<div class="zaya-section">';
      html += '<div class="zaya-section-title">📋 Relevant policy</div>';
      html += '<div class="zaya-section-content">' + escapeHtml(rp.summary || "") + "</div>";
      if (rp.source_doc) html += '<p><small>Source: ' + escapeHtml(rp.source_doc) + "</small></p>";
      if (Array.isArray(rp.eligibility_notes) && rp.eligibility_notes.length)
        html += "<ul class=\"zaya-list\"><li>" + rp.eligibility_notes.map(function (n) { return escapeHtml(n); }).join("</li><li>") + "</li></ul>";
      if (Array.isArray(rp.exception_notes) && rp.exception_notes.length)
        html += "<p class=\"zaya-warn\">⚠️ " + rp.exception_notes.map(escapeHtml).join(" ") + "</p>";
      html += "</div>";
    }
    var sim = data.similar_past_tickets;
    if (Array.isArray(sim) && sim.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">📝 Similar past tickets</div><ul class="zaya-list">';
      sim.slice(0, 5).forEach(function (t) {
        html += "<li><strong>" + escapeHtml(t.ticket_id || "") + "</strong> — " + escapeHtml(t.resolution || t.situation || "") + (t.lesson ? " <span class=\"zaya-warn\">" + escapeHtml(t.lesson) + "</span>" : "") + "</li>";
      });
      html += "</ul></div>";
    }
    var resp = data.suggested_response;
    if (resp) {
      html += '<div class="zaya-section">';
      html += '<div class="zaya-section-title">💬 Suggested response</div>';
      html += '<div class="zaya-suggested-response">' + escapeHtml(resp).replace(/\n/g, "<br>") + "</div>";
      html += "</div>";
    }
    if (data.suggested_tags && data.suggested_tags.length)
      html += '<div class="zaya-section"><div class="zaya-section-title">Tags</div><p>' + data.suggested_tags.map(escapeHtml).join(", ") + "</p></div>";
    if (data.knowledge_gaps && data.knowledge_gaps.length)
      html += '<div class="zaya-section"><div class="zaya-section-title">⚠️ Knowledge gaps</div><ul class=\"zaya-list\"><li>' + data.knowledge_gaps.map(escapeHtml).join("</li><li>") + "</li></ul></div>";
    return html || "<p>No intelligence for this context. Try adding more documents to your knowledge base.</p>";
  }

  function renderCrm(data) {
    var html = "";
    var issues = data.open_issues;
    if (Array.isArray(issues) && issues.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">⚠️ Open issues</div><ul class="zaya-list">';
      issues.forEach(function (i) {
        html += "<li>" + escapeHtml(i.issue || "") + (i.suggestion ? " → " + escapeHtml(i.suggestion) : "") + "</li>";
      });
      html += "</ul></div>";
    }
    var comm = data.commitments_made;
    if (Array.isArray(comm) && comm.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Commitments made</div><ul class="zaya-list">';
      comm.forEach(function (c) {
        html += "<li>" + escapeHtml(c.commitment || "") + " <small>" + escapeHtml(c.status_note || "") + "</small></li>";
      });
      html += "</ul></div>";
    }
    var points = data.renewal_talking_points;
    if (Array.isArray(points) && points.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Renewal talking points</div><ul class="zaya-list">';
      points.forEach(function (p) { html += "<li>" + escapeHtml(p) + "</li>"; });
      html += "</ul></div>";
    }
    var risk = data.competitive_risk;
    if (risk && (risk.mentioned_competitor || risk.position_summary)) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Competitive risk</div><p>' + escapeHtml(risk.position_summary || risk.mentioned_competitor || "") + "</p></div>";
    }
    var actions = data.suggested_next_actions;
    if (Array.isArray(actions) && actions.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Suggested next actions</div><ul class="zaya-list">';
      actions.forEach(function (a) { html += "<li>" + escapeHtml(a) + "</li>"; });
      html += "</ul></div>";
    }
    return html || "<p>No account intelligence for this context.</p>";
  }

  function renderJira(data) {
    var html = "";
    var sim = data.similar_past_issues;
    if (Array.isArray(sim) && sim.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Similar past issues</div><ul class="zaya-list">';
      sim.slice(0, 5).forEach(function (i) {
        html += "<li><strong>" + escapeHtml(i.id || "") + "</strong> " + escapeHtml(i.title || "") + " — " + escapeHtml(i.resolution || "") + (i.relevance_note ? " <small>" + escapeHtml(i.relevance_note) + "</small>" : "") + "</li>";
      });
      html += "</ul></div>";
    }
    var runbooks = data.relevant_runbooks;
    if (Array.isArray(runbooks) && runbooks.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Relevant runbooks</div><ul class="zaya-list">';
      runbooks.forEach(function (r) {
        html += "<li>" + escapeHtml(r.name || "") + (r.section ? " § " + escapeHtml(r.section) : "") + " — " + escapeHtml(r.summary || "") + "</li>";
      });
      html += "</ul></div>";
    }
    var adrs = data.relevant_adrs;
    if (Array.isArray(adrs) && adrs.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Relevant ADRs</div><ul class="zaya-list">';
      adrs.forEach(function (a) {
        html += "<li>" + escapeHtml(a.id || "") + " " + escapeHtml(a.title || "") + " — " + escapeHtml(a.relevance || "") + "</li>";
      });
      html += "</ul></div>";
    }
    if (data.people_who_solved_similar && data.people_who_solved_similar.length)
      html += '<div class="zaya-section"><div class="zaya-section-title">People who solved similar</div><p>' + data.people_who_solved_similar.map(escapeHtml).join(", ") + "</p></div>";
    if (data.estimated_resolution)
      html += '<div class="zaya-section"><div class="zaya-section-title">Estimated resolution</div><p>' + escapeHtml(data.estimated_resolution) + "</p></div>";
    return html || "<p>No engineering context for this issue.</p>";
  }

  function renderNotion(data) {
    var html = "";
    var fresh = data.freshness_alerts;
    if (Array.isArray(fresh) && fresh.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">⚠️ Freshness</div><ul class="zaya-list">';
      fresh.forEach(function (f) {
        html += "<li>" + escapeHtml(f.line_or_section || "") + " — " + escapeHtml(f.issue || "") + "</li>";
      });
      html += "</ul></div>";
    }
    var conflicts = data.conflicts_detected;
    if (Array.isArray(conflicts) && conflicts.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">🔴 Conflicts</div><ul class="zaya-list">';
      conflicts.forEach(function (c) {
        html += "<li>Page: " + escapeHtml(c.page_says || "") + " vs " + escapeHtml(c.other_doc_name || "") + ": " + escapeHtml(c.other_doc_says || "") + "</li>";
      });
      html += "</ul></div>";
    }
    var questions = data.unanswered_questions_about_topic;
    if (Array.isArray(questions) && questions.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Unanswered questions</div><ul class="zaya-list">';
      questions.forEach(function (q) { html += "<li>" + escapeHtml(q) + "</li>"; });
      html += "</ul></div>";
    }
    return html || "<p>No wiki health data for this page.</p>";
  }

  function renderHr(data) {
    var html = "";
    if (data.policy_summary)
      html += '<div class="zaya-section"><div class="zaya-section-title">Policy</div><div class="zaya-section-content">' + escapeHtml(data.policy_summary).replace(/\n/g, "<br>") + "</div></div>";
    if (data.balance_or_eligibility && data.balance_or_eligibility.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Balance / eligibility</div><ul class="zaya-list">';
      data.balance_or_eligibility.forEach(function (b) {
        html += "<li>" + escapeHtml(b.type || "") + ": " + escapeHtml(b.value || "") + (b.note ? " — " + escapeHtml(b.note) : "") + "</li>";
      });
      html += "</ul></div>";
    }
    if (data.approval_process && data.approval_process.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Approval process</div><ol class="zaya-list">';
      data.approval_process.forEach(function (s) { html += "<li>" + escapeHtml(s) + "</li>"; });
      html += "</ol></div>";
    }
    if (data.warnings && data.warnings.length)
      html += '<div class="zaya-section"><div class="zaya-section-title">⚠️ Warnings</div><ul class="zaya-list"><li>' + data.warnings.map(escapeHtml).join("</li><li>") + "</li></ul></div>";
    return html || "<p>No HR policy data for this form.</p>";
  }

  function renderAccounting(data) {
    var html = "";
    var vs = data.vendor_status;
    if (vs) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Vendor</div><p>' + (vs.approved ? "✅ Approved" : "❌ Not approved") + (vs.source ? " — " + escapeHtml(vs.source) : "") + "</p></div>";
    }
    var rv = data.rate_variance;
    if (rv && rv.detected) {
      html += '<div class="zaya-section"><div class="zaya-section-title">⚠️ Rate variance</div><p>' + escapeHtml(rv.note || "") + "</p></div>";
    }
    var bc = data.budget_check;
    if (bc) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Budget</div><p>' + (bc.within_budget ? "✅ Within budget" : "⚠️ Check budget") + " — " + escapeHtml(bc.category || "") + "</p></div>";
    }
    if (data.compliance_notes && data.compliance_notes.length)
      html += '<div class="zaya-section"><div class="zaya-section-title">Compliance</div><ul class="zaya-list"><li>' + data.compliance_notes.map(escapeHtml).join("</li><li>") + "</li></ul></div>";
    if (data.suggested_action)
      html += '<div class="zaya-section"><div class="zaya-section-title">Suggested action</div><p>' + escapeHtml(data.suggested_action) + "</p></div>";
    return html || "<p>No verification data for this invoice.</p>";
  }

  function renderRecruitment(data) {
    var html = "";
    if (data.candidate_match && data.candidate_match.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Candidate match</div><ul class="zaya-list">';
      data.candidate_match.forEach(function (m) {
        html += "<li>" + (m.met ? "✅" : "❌") + " " + escapeHtml(m.requirement || "") + (m.note ? " — " + escapeHtml(m.note) : "") + "</li>";
      });
      html += "</ul></div>";
    }
    var cg = data.compensation_guide;
    if (cg)
      html += '<div class="zaya-section"><div class="zaya-section-title">Compensation</div><p>' + escapeHtml(cg.band || "") + " " + escapeHtml(cg.range || "") + " " + (cg.note || "") + "</p></div>";
    if (data.interview_questions && data.interview_questions.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Interview questions</div><ul class="zaya-list">';
      data.interview_questions.forEach(function (q) { html += "<li>" + escapeHtml(q) + "</li>"; });
      html += "</ul></div>";
    }
    return html || "<p>No hiring intelligence for this candidate.</p>";
  }

  function renderCustom(data) {
    var html = "";
    if (data.relevant_docs && data.relevant_docs.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Relevant docs</div><ul class="zaya-list">';
      data.relevant_docs.forEach(function (d) {
        html += "<li><strong>" + escapeHtml(d.name || "") + "</strong><p>" + escapeHtml((d.snippet || "").slice(0, 300)) + "</p></li>";
      });
      html += "</ul></div>";
    }
    if (data.key_facts && data.key_facts.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Key facts</div><ul class="zaya-list">';
      data.key_facts.forEach(function (f) { html += "<li>" + escapeHtml(f) + "</li>"; });
      html += "</ul></div>";
    }
    if (data.suggested_actions && data.suggested_actions.length) {
      html += '<div class="zaya-section"><div class="zaya-section-title">Suggested actions</div><ul class="zaya-list">';
      data.suggested_actions.forEach(function (a) { html += "<li>" + escapeHtml(a) + "</li>"; });
      html += "</ul></div>";
    }
    if (data.answer_placeholder)
      html += '<div class="zaya-section"><div class="zaya-section-title">Summary</div><p>' + escapeHtml(data.answer_placeholder).replace(/\n/g, "<br>") + "</p></div>";
    return html || "<p>No context intelligence. Ask ZAYA a question below.</p>";
  }

  function renderBody(data, appType) {
    if (data.error) return '<div class="zaya-error">' + escapeHtml(data.error) + "</div>";
    var at = (appType || data.app_type || "custom").toLowerCase();
    if (at === "zendesk" || at === "freshdesk") return renderSupport(data);
    if (at === "salesforce" || at === "hubspot") return renderCrm(data);
    if (at === "jira" || at === "linear") return renderJira(data);
    if (at === "notion" || at === "confluence") return renderNotion(data);
    if (at === "hr") return renderHr(data);
    if (at === "accounting") return renderAccounting(data);
    if (at === "recruitment") return renderRecruitment(data);
    return renderCustom(data);
  }

  function sendChat() {
    var input = document.getElementById("zaya-chat-input");
    var bodyEl = document.getElementById("zaya-panel-body");
    if (!input || !bodyEl) return;
    var q = (input.value || "").trim();
    if (!q) return;
    input.value = "";
    var chatWrap = document.getElementById("zaya-chat-wrap");
    if (chatWrap) chatWrap.style.display = "none";
    bodyEl.innerHTML = '<div class="zaya-loading"><div class="zaya-spinner"></div><p style="margin-top:12px">ZAYA is answering…</p></div>';
    api("POST", "/api/web-app/chat", {
      app_type: config.appType,
      context: window.__ZAYA_LAST_CONTEXT__ || {},
      question: q,
      tenant_id: config.tenantId,
      namespace: config.namespace,
    })
      .then(function (res) {
        if (chatWrap) chatWrap.style.display = "";
        bodyEl.innerHTML = '<div class="zaya-answer-block">' + escapeHtml(res.answer || "").replace(/\n/g, "<br>") + "</div>";
      })
      .catch(function (err) {
        if (chatWrap) chatWrap.style.display = "";
        bodyEl.innerHTML = '<div class="zaya-error">' + escapeHtml(err.message || "Request failed") + "</div>";
      });
  }

  function show(context) {
    context = context || {};
    window.__ZAYA_LAST_CONTEXT__ = context;
    var p = getPanel();
    var titleEl = document.getElementById("zaya-panel-title");
    if (titleEl) titleEl.textContent = "ZAYA — " + (config.appType || "custom");
    var bodyEl = document.getElementById("zaya-panel-body");
    if (!bodyEl) return;
    showLoading();
    p.classList.add("zaya-open");
    api("POST", "/api/web-app/intelligence", {
      app_type: config.appType,
      context: context,
      tenant_id: config.tenantId,
      namespace: config.namespace,
    })
      .then(function (data) {
        bodyEl.innerHTML = renderBody(data, config.appType);
      })
      .catch(function (err) {
        bodyEl.innerHTML = '<div class="zaya-error">' + escapeHtml(err.message || "Failed to load intelligence") + "</div>";
      });
  }

  function init(opts) {
    if (opts.apiBase) config.apiBase = opts.apiBase;
    if (opts.apiKey) config.apiKey = opts.apiKey;
    if (opts.tenantId) config.tenantId = opts.tenantId;
    if (opts.namespace) config.namespace = opts.namespace;
    if (opts.appType) config.appType = opts.appType;
    if (opts.floatingButton !== false) {
      if (!floatBtn) {
        floatBtn = document.createElement("button");
        floatBtn.className = "zaya-floating-btn";
        floatBtn.setAttribute("aria-label", "Open ZAYA");
        floatBtn.textContent = "Z";
        getRoot().appendChild(floatBtn);
        floatBtn.addEventListener("click", function () {
          show(window.__ZAYA_LAST_CONTEXT__ || {});
        });
      }
    }
    return { show: show, config: config };
  }

  global.ZAYA = {
    init: init,
    show: show,
    config: config,
  };
})(typeof window !== "undefined" ? window : this);
