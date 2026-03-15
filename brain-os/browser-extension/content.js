(function () {
  var panel = null;
  var floatBtn = null;
  var comparisonPanel = null;
  var contractPanel = null;
  var emailPanel = null;
  var meetingBriefPanel = null;
  var researchPanel = null;
  var formSuggestPanel = null;
  var watchResultPanel = null;
  var verifyClaimsPanel = null;
  var addToResearchResultPanel = null;
  var currentSelection = '';
  var lastFormSuggestions = [];

  function getBrainOSRoot() {
    var root = document.getElementById('brainos-root');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'brainos-root';
    document.body.appendChild(root);
    return root;
  }

  var LOADING_HTML = '<div class="brainos-loading-wrap"><div class="brainos-spinner"></div><p class="brainos-loading-text">BrainOS is thinking…</p></div>';

  function getPanel() {
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = 'brainos-panel';
    panel.innerHTML =
      '<div class="panel-header">' +
      '  <h3>Ask BrainOS</h3>' +
      '  <button class="panel-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="panel-body">' +
      '  <div class="context-block" id="brainos-context"></div>' +
      '  <input type="text" id="brainos-question" placeholder="Ask a question about the selected text…">' +
      '  <button class="ask-btn" id="brainos-ask">Ask</button>' +
      '  <div class="answer-block" id="brainos-answer"></div>' +
      '</div>';
    getBrainOSRoot().appendChild(panel);
    panel.querySelector('.panel-close').addEventListener('click', function () {
      panel.classList.remove('open');
    });
    panel.querySelector('#brainos-ask').addEventListener('click', sendAsk);
    panel.querySelector('#brainos-question').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') sendAsk();
    });
    return panel;
  }

  function getComparisonPanel() {
    if (comparisonPanel) return comparisonPanel;
    comparisonPanel = document.createElement('div');
    comparisonPanel.id = 'brainos-comparison-panel';
    comparisonPanel.className = 'brainos-comparison-panel';
    comparisonPanel.innerHTML =
      '<div class="comparison-header">' +
      '  <h3>BrainOS</h3>' +
      '  <button class="comparison-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="comparison-body">' +
      '  <div class="comparison-selected" id="comparison-selected"></div>' +
      '  <div class="comparison-result" id="comparison-result"></div>' +
      '  <div class="comparison-actions"><button class="comparison-ask-btn" id="comparison-ask-zaya">Ask BrainOS</button></div>' +
      '</div>';
    getBrainOSRoot().appendChild(comparisonPanel);
    comparisonPanel.querySelector('.comparison-close').addEventListener('click', function () {
      comparisonPanel.classList.remove('open');
    });
    comparisonPanel.querySelector('#comparison-ask-zaya').addEventListener('click', function () {
      var sel = document.getElementById('comparison-selected');
      var text = sel && sel.getAttribute('data-text') || currentSelection;
      if (text) {
        comparisonPanel.classList.remove('open');
        currentSelection = text;
        var p = getPanel();
        p.querySelector('#brainos-context').textContent = text.slice(0, 500) + (text.length > 500 ? '…' : '');
        p.querySelector('#brainos-question').value = '';
        p.querySelector('#brainos-answer').textContent = '';
        p.querySelector('#brainos-answer').className = 'answer-block';
        p.classList.add('open');
      }
    });
    return comparisonPanel;
  }

  function renderComparisonResult(mode, data, selectedText, error) {
    var cp = getComparisonPanel();
    var selectedEl = cp.querySelector('#comparison-selected');
    var resultEl = cp.querySelector('#comparison-result');
    selectedEl.setAttribute('data-text', selectedText || '');
    selectedEl.textContent = selectedText ? ('SELECTED TEXT:\n' + (selectedText.length > 400 ? selectedText.slice(0, 400) + '…' : selectedText)) : '';

    if (error) {
      resultEl.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      cp.classList.add('open');
      return;
    }

    var html = '';
    if (mode === 'compare') {
      var consistent = (data.consistent || []);
      var conflicts = (data.conflicts || []);
      html += '<div class="comparison-section"><strong>WHAT YOUR KNOWLEDGE BASE SAYS</strong></div>';
      if (consistent.length > 0) {
        html += '<div class="comparison-consistent">✅ CONSISTENT — ' + consistent.length + ' document(s) agree</div>';
        consistent.forEach(function (c) {
          html += '<div class="comparison-doc"><span class="doc-name">' + escapeHtml(c.document_name || '') + '</span><p>' + escapeHtml(c.snippet || '') + '</p>' + (c.note ? '<span class="doc-note">' + escapeHtml(c.note) + '</span>' : '') + '</div>';
        });
      }
      if (conflicts.length > 0) {
        html += '<div class="comparison-conflicts">⚠️ POTENTIAL CONFLICT(S)</div>';
        conflicts.forEach(function (c) {
          html += '<div class="comparison-doc conflict"><span class="doc-name">' + escapeHtml(c.document_name || '') + '</span><p>' + escapeHtml(c.snippet || '') + '</p>' + (c.note ? '<span class="doc-note">' + escapeHtml(c.note) + '</span>' : '') + (c.confidence != null ? ' <span class="confidence">Confidence: ' + Math.round(c.confidence * 100) + '%</span>' : '') + '</div>';
        });
      }
      if (consistent.length === 0 && conflicts.length === 0) {
        html += '<p class="comparison-empty">No relevant documents found in your knowledge base.</p>';
      }
    } else if (mode === 'factcheck') {
      var verdict = data.verdict || 'unverified';
      var verdictClass = verdict === 'correct' ? 'correct' : verdict === 'incorrect' ? 'incorrect' : 'unverified';
      html += '<div class="comparison-section"><strong>FACT CHECK RESULT</strong></div>';
      html += '<div class="factcheck-verdict ' + verdictClass + '">' + (verdict === 'correct' ? '✅ CORRECT' : verdict === 'incorrect' ? '❌ INCORRECT' : '❓ UNVERIFIED') + '</div>';
      if (data.explanation) html += '<p class="comparison-explanation">' + escapeHtml(data.explanation) + '</p>';
      if (data.correct_info) html += '<div class="correct-info"><strong>Your docs say:</strong><p>' + escapeHtml(data.correct_info) + '</p></div>';
      (data.sources || []).forEach(function (s) {
        html += '<div class="comparison-doc"><span class="doc-name">' + escapeHtml(s.document_name || '') + '</span><p>' + escapeHtml(s.snippet || '') + '</p></div>';
      });
    } else if (mode === 'position') {
      html += '<div class="comparison-section"><strong>YOUR POSITION</strong></div>';
      if (data.position) html += '<p class="position-text">' + escapeHtml(data.position) + '</p>';
      if (data.confidence != null) html += '<p class="confidence">Confidence: ' + Math.round(data.confidence * 100) + '%</p>';
      (data.sources || []).forEach(function (s) {
        html += '<div class="comparison-doc"><span class="doc-name">' + escapeHtml(s.document_name || '') + '</span><p>' + escapeHtml(s.snippet || '') + '</p></div>';
      });
    }
    resultEl.innerHTML = html || '<p>No result.</p>';
    cp.classList.add('open');
  }

  function escapeHtml(s) {
    if (!s) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function getGenericSidePanel(id, title, closeCb) {
    var el = document.getElementById(id);
    if (el) return el;
    el = document.createElement('div');
    el.id = id;
    el.className = 'brainos-comparison-panel brainos-generic-panel';
    el.innerHTML =
      '<div class="comparison-header">' +
      '  <h3>' + escapeHtml(title) + '</h3>' +
      '  <button class="comparison-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="comparison-body"><div class="comparison-result" id="' + id + '-body"></div></div>';
    getBrainOSRoot().appendChild(el);
    el.querySelector('.comparison-close').addEventListener('click', function () {
      el.classList.remove('open');
      if (closeCb) closeCb();
    });
    return el;
  }

  function getPanelBody(panel) {
    if (!panel) return null;
    return panel.querySelector('.comparison-result') || document.getElementById(panel.id + '-body');
  }

  function showContractReviewPanel(data, error, loading) {
    if (!contractPanel) {
      contractPanel = getGenericSidePanel('brainos-contract-panel', 'Contract review (ZAYA)', null);
    }
    var body = getPanelBody(contractPanel);
    if (!body) return;
    contractPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var html = '';
    var consistent = (data.consistent || []);
    var deviations = (data.deviations || []);
    var notIn = (data.not_in_standard || []);
    if (consistent.length) {
      html += '<div class="comparison-section"><strong>Consistent with standard</strong></div><ul>';
      consistent.forEach(function (c) { html += '<li>' + escapeHtml(typeof c === 'string' ? c : (c.clause || c.summary || '')) + '</li>'; });
      html += '</ul>';
    }
    if (deviations.length) {
      html += '<div class="comparison-section comparison-conflicts">Deviations</div>';
      deviations.forEach(function (d) {
        var o = typeof d === 'string' ? { clause: d } : d;
        html += '<div class="comparison-doc conflict"><span class="doc-name">' + escapeHtml(o.clause || '') + '</span>';
        if (o.risk) html += ' <span class="risk">' + escapeHtml(o.risk) + '</span>';
        if (o.contract_says) html += '<p>Contract: ' + escapeHtml(o.contract_says) + '</p>';
        if (o.standard_says) html += '<p>Standard: ' + escapeHtml(o.standard_says) + '</p>';
        if (o.action) html += '<p>Action: ' + escapeHtml(o.action) + '</p>';
        html += '</div>';
      });
    }
    if (notIn.length) {
      html += '<div class="comparison-section">Not in standard</div>';
      notIn.forEach(function (n) {
        var o = typeof n === 'string' ? { clause: n } : n;
        html += '<div class="comparison-doc"><span class="doc-name">' + escapeHtml(o.clause || '') + '</span><p>' + escapeHtml(o.summary || '') + '</p></div>';
      });
    }
    body.innerHTML = html || '<p>No issues found.</p>';
  }

  function showEmailPanel(data, error, loading) {
    if (!emailPanel) {
      emailPanel = getGenericSidePanel('brainos-email-panel', 'Email intelligence', null);
    }
    var body = getPanelBody(emailPanel);
    if (!body) {
      emailPanel.classList.add('open');
      return;
    }
    emailPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var html = '';
    (data.key_info || []).forEach(function (k) { html += '<p><strong>Key info:</strong> ' + escapeHtml(k) + '</p>'; });
    (data.suggested_actions || []).forEach(function (a) { html += '<p><strong>Action:</strong> ' + escapeHtml(a) + '</p>'; });
    if (data.reply_context) html += '<div class="comparison-section">Reply context</div><p class="reply-context">' + escapeHtml(data.reply_context) + '</p>';
    (data.related_doc_names || []).forEach(function (d) { html += '<span class="doc-tag">' + escapeHtml(d) + '</span> '; });
    body.innerHTML = html || '<p>No analysis.</p>';
  }

  function showMeetingBriefPanel(data, error, loading) {
    if (!meetingBriefPanel) {
      meetingBriefPanel = getGenericSidePanel('brainos-meeting-panel', 'Meeting brief', null);
    }
    var body = getPanelBody(meetingBriefPanel);
    if (!body) {
      meetingBriefPanel.classList.add('open');
      return;
    }
    meetingBriefPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var html = '';
    if (data.brief) html += '<div class="brief-text">' + escapeHtml(data.brief).replace(/\n/g, '<br>') + '</div>';
    (data.related_docs || []).forEach(function (d) { html += '<p class="doc-tag">' + escapeHtml(d) + '</p>'; });
    (data.suggested_questions || []).forEach(function (q) { html += '<p><strong>Ask:</strong> ' + escapeHtml(q) + '</p>'; });
    body.innerHTML = html || '<p>No brief.</p>';
  }

  function showResearchPanel(data, error, loading) {
    if (!researchPanel) {
      researchPanel = getGenericSidePanel('brainos-research-panel', 'Research synthesis', null);
    }
    var body = getPanelBody(researchPanel);
    if (!body) return;
    researchPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var html = '';
    (data.key_findings || []).forEach(function (f) { html += '<li>' + escapeHtml(f) + '</li>'; });
    if (html) html = '<div class="comparison-section">Key findings</div><ul>' + html + '</ul>';
    (data.agreements || []).forEach(function (a) { html += '<p>Agreement: ' + escapeHtml(a) + '</p>'; });
    (data.disagreements || []).forEach(function (d) { html += '<p>Disagreement: ' + escapeHtml(d) + '</p>'; });
    if (data.synthesis_draft) html += '<div class="comparison-section">Synthesis</div><div class="synthesis-draft">' + escapeHtml(data.synthesis_draft).replace(/\n/g, '<br>') + '</div>';
    body.innerHTML = html || '<p>No synthesis.</p>';
  }

  function applyFormSuggestions(suggestions) {
    var filled = [];
    try {
      (suggestions || []).forEach(function (s) {
        var label = ((s.field_label || s.label || '') + '').toLowerCase();
        var value = (s.suggested_value || s.value || '') + '';
        if (!value) return;
        var inputs = document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea');
        for (var i = 0; i < inputs.length; i++) {
          var inp = inputs[i];
          var n = ((inp.name || inp.id || inp.placeholder || '') + '').toLowerCase();
          if (n && (n.indexOf(label) !== -1 || label.indexOf(n) !== -1)) {
            inp.value = value;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            filled.push({ label: (s.field_label || s.label || n || 'field'), value: value });
            break;
          }
        }
      });
    } catch (e) {}
    return filled;
  }

  function showFormSuggestPanel(data, error, loading) {
    if (!formSuggestPanel) {
      formSuggestPanel = getGenericSidePanel('brainos-form-panel', 'Fill with BrainOS', null);
    }
    var body = getPanelBody(formSuggestPanel);
    if (!body) return;
    formSuggestPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var suggestions = data.suggestions || [];
    lastFormSuggestions = suggestions;
    var html = '<p><strong>' + suggestions.length + ' field(s)</strong> can be filled from your knowledge base.</p>';
    suggestions.forEach(function (s) {
      var label = (s.field_label || s.label || '') + '';
      var val = (s.suggested_value || s.value || '') + '';
      html += '<div class="form-suggest-row"><span class="form-label">' + escapeHtml(label) + '</span> → <span class="form-value">' + escapeHtml(val) + '</span></div>';
    });
    html += '<div class="comparison-actions"><button class="comparison-ask-btn" id="brainos-fill-all">Fill all</button></div>';
    html += '<div id="brainos-filled-result" class="form-filled-result"></div>';
    body.innerHTML = html;
    var btn = body.querySelector('#brainos-fill-all');
    var resultEl = body.querySelector('#brainos-filled-result');
    if (btn) {
      btn.addEventListener('click', function () {
        var filled = applyFormSuggestions(lastFormSuggestions);
        if (resultEl) {
          resultEl.innerHTML = '<div class="comparison-section">Filled on this page</div><p>' + filled.length + ' field(s) updated:</p><ul>' + filled.map(function (f) { return '<li><strong>' + escapeHtml(f.label) + '</strong> → ' + escapeHtml(f.value) + '</li>'; }).join('') + '</ul>';
          resultEl.style.display = 'block';
        }
      });
    }
  }

  function showAddToResearchResultPanel(data, error) {
    if (!addToResearchResultPanel) {
      addToResearchResultPanel = getGenericSidePanel('brainos-add-research-panel', 'Research', null);
    }
    var body = getPanelBody(addToResearchResultPanel);
    if (!body) return;
    addToResearchResultPanel.classList.add('open');
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var msg = (data && data.message) || 'Page added to research. Use "Synthesise research" in the extension popup to generate the synthesis.';
    body.innerHTML = '<p class="research-confirm">' + escapeHtml(msg) + '</p>';
  }

  function showWatchResultPanel(data, error, loading) {
    if (!watchResultPanel) {
      watchResultPanel = getGenericSidePanel('brainos-watch-panel', 'Page watch', null);
    }
    var body = getPanelBody(watchResultPanel);
    if (!body) return;
    watchResultPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var html = '<p>' + (data.message || '') + '</p>';
    if (data.changed) {
      html += '<p class="watch-changed">Content has changed since last check.</p>';
      if (data.summary) {
        html += '<div class="comparison-section"><strong>What changed</strong></div>';
        html += '<div class="watch-summary">' + escapeHtml(data.summary).replace(/\n/g, '<br>') + '</div>';
      }
    } else {
      html += '<p class="watch-unchanged">No changes since last check.</p>';
    }
    body.innerHTML = html;
  }

  function showVerifyClaimsPanel(data, error, loading) {
    if (!verifyClaimsPanel) {
      verifyClaimsPanel = getGenericSidePanel('brainos-verify-claims-panel', 'Verify claims (BrainOS)', null);
    }
    var body = getPanelBody(verifyClaimsPanel);
    if (!body) return;
    verifyClaimsPanel.classList.add('open');
    if (loading) {
      body.innerHTML = LOADING_HTML;
      return;
    }
    if (error) {
      body.innerHTML = '<div class="comparison-error">' + escapeHtml(error) + '</div>';
      return;
    }
    var list = Array.isArray(data) ? data : [];
    var html = '<div class="comparison-section"><strong>' + list.length + ' claim(s) checked</strong></div>';
    list.forEach(function (r, idx) {
      var verdict = r.supported ? 'Supported' : (r.verdict === 'incorrect' ? 'Incorrect' : 'Unverified');
      var cls = r.supported ? 'claim-supported' : 'claim-unsupported';
      html += '<div class="comparison-doc ' + cls + '">';
      html += '<span class="doc-name">' + (idx + 1) + '. ' + escapeHtml(verdict) + '</span>';
      html += '<p class="claim-text">' + escapeHtml((r.claim || '').trim()) + '</p>';
      if (r.explanation) html += '<p class="claim-explanation">' + escapeHtml(r.explanation) + '</p>';
      if (r.correct_info) html += '<p class="correct-info">Your docs say: ' + escapeHtml(r.correct_info) + '</p>';
      if (r.sources && r.sources.length) html += '<p class="claim-sources">Sources: ' + escapeHtml(r.sources.map(function (s) { return typeof s === 'string' ? s : (s.document_name || s.snippet || ''); }).join('; ')) + '</p>';
      html += '</div>';
    });
    body.innerHTML = html || '<p>No claims to show.</p>';
  }

  chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.action === 'getSelectionAndRunTextVsKb') {
      var sel = window.getSelection();
      var text = (sel && sel.toString() || '').trim();
      sendResponse({ text: text });
      return;
    }
    if (request.action === 'showComparisonResult') {
      renderComparisonResult(request.mode, request.data || {}, request.selectedText || '', request.error);
      sendResponse({});
      return;
    }
    if (request.action === 'getPageText') {
      try {
        var body = document.body;
        var text = (body && (body.innerText || body.textContent) || '').trim();
        if (text.length > 50000) text = text.slice(0, 50000);
        sendResponse({ text: text, title: document.title || '' });
      } catch (e) {
        sendResponse({ text: '', title: '', error: e.message });
      }
      return true;
    }
    if (request.action === 'showContractReview') {
      showContractReviewPanel(request.data || {}, request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'showEmailPanel') {
      showEmailPanel(request.data || {}, request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'showMeetingBrief') {
      showMeetingBriefPanel(request.data || {}, request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'showResearchPanel') {
      showResearchPanel(request.data || {}, request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'showFormSuggestPanel') {
      showFormSuggestPanel(request.data || {}, request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'showWatchResult') {
      showWatchResultPanel(request.data || {}, request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'showAddToResearchResult') {
      showAddToResearchResultPanel(request.data || {}, request.error);
      sendResponse({});
      return;
    }
    if (request.action === 'showVerifyClaimsResult') {
      showVerifyClaimsPanel(Array.isArray(request.data) ? request.data : [], request.error, request.loading);
      sendResponse({});
      return;
    }
    if (request.action === 'runContractReview') {
      chrome.runtime.sendMessage({
        action: 'extensionApi',
        path: '/api/extension/contract-review',
        body: { contract_text: request.pageText || '' }
      }, function (res) {
        if (chrome.runtime.lastError) {
          showContractReviewPanel({}, chrome.runtime.lastError.message, false);
          return;
        }
        showContractReviewPanel(res && res.data ? res.data : {}, res && res.error ? res.error : null, false);
      });
      sendResponse({});
      return true;
    }
    if (request.action === 'runWatchPage') {
      chrome.runtime.sendMessage({
        action: 'extensionApi',
        path: '/api/extension/watch-page',
        body: { url: request.url || '', action: 'add', content: request.content || '', user_key: 'default' }
      }, function (res) {
        if (chrome.runtime.lastError) {
          showWatchResultPanel({}, chrome.runtime.lastError.message, false);
          return;
        }
        showWatchResultPanel(res && res.data ? res.data : {}, res && res.error ? res.error : null, false);
      });
      sendResponse({});
      return true;
    }
    if (request.action === 'runFormSuggest') {
      chrome.runtime.sendMessage({
        action: 'extensionApi',
        path: '/api/extension/form-suggest',
        body: { field_labels: request.field_labels || [] }
      }, function (res) {
        if (chrome.runtime.lastError) {
          showFormSuggestPanel({}, chrome.runtime.lastError.message, false);
          return;
        }
        showFormSuggestPanel(res && res.data ? res.data : {}, res && res.error ? res.error : null, false);
      });
      sendResponse({});
      return true;
    }
    if (request.action === 'runResearchSynthesize') {
      chrome.runtime.sendMessage({
        action: 'extensionApi',
        path: '/api/extension/research-synthesize',
        body: { sources: request.sources || [] }
      }, function (res) {
        if (chrome.runtime.lastError) {
          showResearchPanel({}, chrome.runtime.lastError.message, false);
          return;
        }
        showResearchPanel(res && res.data ? res.data : {}, res && res.error ? res.error : null, false);
      });
      sendResponse({});
      return true;
    }
    if (request.action === 'runCheckWatchPage') {
      chrome.runtime.sendMessage({
        action: 'extensionApi',
        path: '/api/extension/watch-page',
        body: { url: request.url || '', action: 'check', content: request.content || '', user_key: 'default' }
      }, function (res) {
        if (chrome.runtime.lastError) {
          showWatchResultPanel({}, chrome.runtime.lastError.message, false);
          return;
        }
        showWatchResultPanel(res && res.data ? res.data : {}, res && res.error ? res.error : null, false);
      });
      sendResponse({});
      return true;
    }
    if (request.action === 'getFormFields') {
      var fields = [];
      try {
        var forms = document.querySelectorAll('form');
        forms.forEach(function (form) {
          ['input:not([type=hidden]):not([type=submit]):not([type=button])', 'textarea', 'select'].forEach(function (sel) {
            form.querySelectorAll(sel).forEach(function (el) {
              var label = el.getAttribute('name') || el.getAttribute('id') || el.getAttribute('placeholder') || el.getAttribute('aria-label') || '';
              if (el.type === 'checkbox' || el.type === 'radio') return;
              var labelEl = el.id && form.querySelector('label[for="' + el.id + '"]');
              if (labelEl) label = (labelEl.textContent || '').trim() || label;
              if (label) fields.push({ label: label.slice(0, 200), name: el.name, id: el.id, tagName: el.tagName });
            });
          });
        });
      } catch (e) {}
      sendResponse({ fields: fields });
      return true;
    }
  });

  function getFloatBtn() {
    if (floatBtn) return floatBtn;
    floatBtn = document.createElement('button');
    floatBtn.id = 'brainos-float-btn';
    floatBtn.textContent = 'Ask BrainOS about this';
    floatBtn.addEventListener('click', function () {
      var sel = window.getSelection();
      var text = (sel && sel.toString() || '').trim();
      if (!text) return;
      currentSelection = text;
      var p = getPanel();
      p.querySelector('#brainos-context').textContent = text.slice(0, 500) + (text.length > 500 ? '…' : '');
      p.querySelector('#brainos-question').value = '';
      p.querySelector('#brainos-answer').textContent = '';
      p.querySelector('#brainos-answer').className = 'answer-block';
      p.classList.add('open');
    });
    getBrainOSRoot().appendChild(floatBtn);
    return floatBtn;
  }

  function sendAsk() {
    var questionEl = document.getElementById('brainos-question');
    var answerEl = document.getElementById('brainos-answer');
    var btn = document.getElementById('brainos-ask');
    var question = (questionEl && questionEl.value || '').trim();
    if (!question) return;
    if (btn) btn.disabled = true;
    if (answerEl) {
      answerEl.textContent = 'Loading…';
      answerEl.className = 'answer-block loading';
    }
    chrome.runtime.sendMessage({
      action: 'ask',
      question: question,
      pasted_context: currentSelection
    }, function (response) {
      if (btn) btn.disabled = false;
      if (!answerEl) return;
      if (chrome.runtime.lastError) {
        answerEl.textContent = '';
        answerEl.className = 'answer-block error-msg';
        answerEl.textContent = chrome.runtime.lastError.message || 'Error';
        return;
      }
      if (response && response.error) {
        answerEl.textContent = response.error;
        answerEl.className = 'answer-block error-msg';
        return;
      }
      answerEl.className = 'answer-block';
      answerEl.textContent = (response && response.answer) || 'No answer.';
    });
  }

  function updateFloatBtn() {
    var sel = window.getSelection();
    var text = (sel && sel.toString() || '').trim();
    var btn = getFloatBtn();
    if (text.length > 0) {
      try {
        var r = sel.getRangeAt(0).getBoundingClientRect();
        btn.style.left = (r.left + window.scrollX) + 'px';
        btn.style.top = (r.bottom + window.scrollY + 4) + 'px';
      } catch (e) {}
      btn.classList.add('show');
    } else {
      btn.classList.remove('show');
    }
  }

  document.addEventListener('selectionchange', updateFloatBtn);
  document.addEventListener('mouseup', updateFloatBtn);

  function getFormFloatBtn() {
    var id = 'brainos-form-float-btn';
    var btn = document.getElementById(id);
    if (btn) return btn;
    btn = document.createElement('button');
    btn.id = id;
    btn.className = 'brainos-form-float-btn';
    btn.textContent = 'Fill with BrainOS';
    btn.style.display = 'none';
    btn.addEventListener('click', function () {
      var fields = [];
      try {
        document.querySelectorAll('form').forEach(function (form) {
          ['input:not([type=hidden]):not([type=submit]):not([type=button])', 'textarea', 'select'].forEach(function (sel) {
            form.querySelectorAll(sel).forEach(function (el) {
              if (el.type === 'checkbox' || el.type === 'radio') return;
              var label = el.getAttribute('name') || el.getAttribute('id') || el.getAttribute('placeholder') || '';
              var labelEl = el.id && form.querySelector('label[for="' + el.id + '"]');
              if (labelEl) label = (labelEl.textContent || '').trim() || label;
              if (label) fields.push({ label: (label + '').slice(0, 200) });
            });
          });
        });
      } catch (e) {}
      if (fields.length === 0) {
        showFormSuggestPanel({ suggestions: [] }, 'No form fields found.');
        return;
      }
      document.dispatchEvent(new CustomEvent('brainos-show-form-loading'));
      chrome.runtime.sendMessage({
        action: 'formSuggest',
        field_labels: fields.map(function (f) { return f.label; })
      }, function (response) {
        if (response && response.error) {
          showFormSuggestPanel({}, response.error);
        } else if (response && response.data) {
          showFormSuggestPanel(response.data, null);
        }
      });
    });
    document.body.appendChild(btn);
    return btn;
  }

  function updateFormFloatBtn() {
    var hasForm = document.querySelectorAll('form').length > 0;
    var btn = getFormFloatBtn();
    if (hasForm) {
      btn.style.display = 'block';
      btn.style.right = '16px';
      btn.style.bottom = '24px';
      btn.style.position = 'fixed';
      btn.style.zIndex = '2147483645';
    } else {
      btn.style.display = 'none';
    }
  }

  setTimeout(updateFormFloatBtn, 1500);

  document.addEventListener('brainos-show-email-loading', function () {
    showEmailPanel(null, null, true);
  });
  document.addEventListener('brainos-show-meeting-loading', function () {
    showMeetingBriefPanel(null, null, true);
  });
  document.addEventListener('brainos-show-verify-loading', function () {
    showVerifyClaimsPanel([], null, true);
  });
  document.addEventListener('brainos-show-form-loading', function () {
    showFormSuggestPanel(null, null, true);
  });
  document.addEventListener('brainos-show-email-result', function (e) {
    var d = e.detail || {};
    showEmailPanel(d.data || {}, d.error || null, false);
  });
  document.addEventListener('brainos-show-verify-result', function (e) {
    var d = e.detail || {};
    showVerifyClaimsPanel(Array.isArray(d.data) ? d.data : [], d.error || null, false);
  });
  document.addEventListener('brainos-show-meeting-result', function (e) {
    var d = e.detail || {};
    showMeetingBriefPanel(d.data || {}, d.error || null, false);
  });
})();
