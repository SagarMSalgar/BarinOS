/**
 * BrainOS — WhatsApp Web: capture chat to KB, Ask about WhatsApp.
 * Injects "Capture to BrainOS" button; captures visible chat text and ingests. Opens Ask panel for questions.
 */
(function () {
  if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.id) return;

  function getChatText() {
    var text = '';
    try {
      var main = document.querySelector('[data-testid="conversation-panel-body"]') ||
        document.querySelector('[role="main"]') ||
        document.querySelector('.two') ||
        document.querySelector('#main');
      if (main) text = (main.innerText || main.textContent || '').trim();
      if (!text) {
        var panes = document.querySelectorAll('[class*="message"], [class*="Message"], [data-testid*="cell"]');
        panes.forEach(function (el) {
          text += (el.innerText || el.textContent || '') + '\n';
        });
        text = text.trim();
      }
      if (text.length > 50000) text = text.slice(0, 50000);
    } catch (e) {}
    return text;
  }

  function getChatTitle() {
    try {
      var h = document.querySelector('[data-testid="conversation-info-header-chat-title"]') ||
        document.querySelector('header [title]');
      if (h) return (h.getAttribute('title') || h.innerText || h.textContent || '').trim();
    } catch (e) {}
    return 'Chat ' + new Date().toISOString().slice(0, 10);
  }

  function injectButton() {
    if (document.getElementById('brainos-wa-capture')) return;
    var btn = document.createElement('button');
    btn.id = 'brainos-wa-capture';
    btn.className = 'brainos-gmail-intel-btn';
    btn.textContent = 'Capture to BrainOS';
    btn.style.top = '60px';
    btn.addEventListener('click', function () {
      var text = getChatText();
      var title = getChatTitle();
      if (!text) {
        alert('No chat content visible. Scroll to load messages and try again.');
        return;
      }
      btn.disabled = true;
      chrome.storage.sync.get(['apiBase', 'apiKey', 'tenantId', 'namespace'], function (items) {
        var apiBase = (items.apiBase || '').trim();
        if (!apiBase) {
          alert('Set API URL in BrainOS Settings first.');
          btn.disabled = false;
          return;
        }
        var url = apiBase.replace(/\/$/, '') + '/api/ingest';
        var headers = { 'Content-Type': 'application/json' };
        if (items.apiKey) headers['Authorization'] = 'Bearer ' + items.apiKey;
        fetch(url, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({
            tenant_id: items.tenantId || 'default',
            namespace: (items.namespace || 'main').trim() || 'main',
            document_name: 'WhatsApp - ' + title + ' - ' + new Date().toISOString().slice(0, 10),
            content: text
          })
        })
          .then(function (res) {
            if (!res.ok) return res.text().then(function (t) { throw new Error(t || res.statusText); });
            return res.json();
          })
          .then(function () {
            btn.disabled = false;
            alert('Chat captured to BrainOS. You can ask questions about it in any channel or the extension.');
          })
          .catch(function (err) {
            btn.disabled = false;
            alert('Error: ' + (err.message || 'Failed'));
          });
      });
    });
    document.body.appendChild(btn);
  }

  function onMessage(request, sender, sendResponse) {
    if (request.action === 'captureWhatsAppMessage') {
      var payload = request.payload || {};
      chrome.runtime.sendMessage({
        action: 'extensionApi',
        path: '/api/ingest',
        body: {
          tenant_id: payload.tenant_id || 'default',
          namespace: payload.namespace || 'main',
          document_name: payload.document_name || 'WhatsApp capture',
          content: payload.content || '',
          external_id: payload.external_id || null
        }
      }, function (response) {
        sendResponse(response || { ok: false, error: 'No response' });
      });
      return true;
    }
  }

  var observer = new MutationObserver(function () {
    if (document.body) injectButton();
  });
  if (document.body) injectButton();
  else observer.observe(document.documentElement, { childList: true, subtree: true });

  chrome.runtime.onMessage.addListener(onMessage);
})();
