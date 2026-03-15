/**
 * BrainOS — Google Docs: Live Document Assistant (verify claims).
 * Injects "Verify with BrainOS" button; on selection + click sends sentences to verify-claims and shows panel.
 */
(function () {
  if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.id) return;

  var DOCS_UI_PATTERNS = [
    /^\s*Share\s/i, /Try Gemini/i, /\bFile\b.*\bEdit\b.*\bView\b/i, /Insert.*Format.*Tools/i,
    /Extensions?\s*Help/i, /Heading\s*\d/i, /Arial\s*\d*\s*Editing/i, /^\d[\d\s]{10,}$/m,
    /Document tabs?\s*Tab\s*\d/i, /Verify with BrainOS/i, /screen reader/i, /keyboard shortcuts/i,
    /Banner hidden/i, /^\s*\d+\s+\d+\s+\d+/m, /To enable screen reader/i, /press Ctrl/i
  ];

  function isLikelyUI(line) {
    var t = (line || '').trim();
    if (t.length < 3) return true;
    if (t.length > 200 && !/[.!?]/.test(t)) return true;
    for (var i = 0; i < DOCS_UI_PATTERNS.length; i++) {
      if (DOCS_UI_PATTERNS[i].test(t)) return true;
    }
    if (/^\d[\s\d]+$/.test(t) && t.length > 5) return true;
    return false;
  }

  function stripDocsUI(text) {
    if (!text || !text.trim()) return '';
    var lines = text.split(/\r?\n/);
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) continue;
      if (isLikelyUI(line)) continue;
      out.push(line);
    }
    return out.join('\n').trim();
  }

  function getDocContentOnly() {
    try {
      var el = document.querySelector('.kix-appview-editor') ||
        document.querySelector('.kix-page-paginated') ||
        document.querySelector('[role="textbox"]') ||
        document.querySelector('.docs-editor-container .contents') ||
        document.querySelector('#contents .kix-lineview');
      if (el) return (el.innerText || el.textContent || '').trim().slice(0, 12000);
      var all = document.querySelectorAll('[contenteditable="true"]');
      var parts = [];
      for (var i = 0; i < all.length; i++) {
        var t = (all[i].innerText || all[i].textContent || '').trim();
        if (t.length > 50 && !/^[\d\s]+$/.test(t)) parts.push(t);
      }
      if (parts.length) return parts.join('\n').slice(0, 12000);
    } catch (e) {}
    return '';
  }

  function getSelectedOrVisibleText() {
    var sel = window.getSelection();
    var text = (sel && sel.toString() || '').trim();
    if (text && text.length > 10) return stripDocsUI(text) || text;
    try {
      var docText = getDocContentOnly();
      if (docText) return stripDocsUI(docText).slice(0, 8000);
      var body = document.body;
      if (body) return stripDocsUI((body.innerText || body.textContent || '').trim()).slice(0, 8000);
    } catch (e) {}
    return '';
  }

  function splitIntoClaims(text) {
    if (!text || !text.trim()) return [];
    var cleaned = stripDocsUI(text);
    if (!cleaned) return [];
    var sentences = cleaned.split(/(?<=[.!?])\s+/).filter(function (s) {
      s = s.trim();
      return s.length > 15 && !isLikelyUI(s);
    });
    if (sentences.length === 0) {
      var chunks = cleaned.split(/\n+/).filter(function (s) { return s.trim().length > 15 && !isLikelyUI(s.trim()); });
      return chunks.slice(0, 25);
    }
    return sentences.slice(0, 25);
  }

  function injectButton() {
    if (document.getElementById('brainos-docs-verify-btn')) return;
    var btn = document.createElement('button');
    btn.id = 'brainos-docs-verify-btn';
    btn.className = 'brainos-docs-verify-btn';
    btn.textContent = 'Verify with BrainOS';
    btn.addEventListener('click', function () {
      var text = getSelectedOrVisibleText();
      if (!text) {
        alert('Select some text in the document first, or use the button to verify the visible content.');
        return;
      }
      btn.disabled = true;
      document.dispatchEvent(new CustomEvent('brainos-show-verify-loading'));
      var claims = splitIntoClaims(text);
      chrome.runtime.sendMessage({
        action: 'verifyClaims',
        claims: claims
      }, function (response) {
        btn.disabled = false;
        document.dispatchEvent(new CustomEvent('brainos-show-verify-result', {
          detail: {
            data: response && response.data ? response.data : null,
            error: response && response.error ? response.error : (chrome.runtime.lastError && chrome.runtime.lastError.message) || null
          }
        }));
      });
    });
    var root = document.getElementById('brainos-root');
    (root || document.body).appendChild(btn);
  }

  var observer = new MutationObserver(function () {
    if (document.body) injectButton();
  });
  if (document.body) injectButton();
  else observer.observe(document.documentElement, { childList: true, subtree: true });
})();
