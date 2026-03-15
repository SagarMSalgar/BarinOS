/**
 * BrainOS — Gmail: Email Intelligence panel.
 * Injects "Email intel" button; on click sends visible email context to backend and shows panel.
 */
(function () {
  if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.id) return;

  function getEmailContext() {
    var title = document.title || '';
    var bodyText = '';
    try {
      var main = document.querySelector('[role="main"]') || document.querySelector('.nH.bkK') || document.body;
      if (main) bodyText = (main.innerText || main.textContent || '').trim();
      if (!bodyText) bodyText = (document.body.innerText || document.body.textContent || '').trim();
      if (bodyText.length > 15000) bodyText = bodyText.slice(0, 15000);
    } catch (e) {}
    return { subject: title, body: bodyText };
  }

  function injectButton() {
    if (document.getElementById('brainos-gmail-btn')) return;
    var btn = document.createElement('button');
    btn.id = 'brainos-gmail-btn';
    btn.className = 'brainos-gmail-intel-btn';
    btn.textContent = 'Email intel';
    btn.addEventListener('click', function () {
      btn.disabled = true;
      document.dispatchEvent(new CustomEvent('brainos-show-email-loading'));
      var ctx = getEmailContext();
      chrome.runtime.sendMessage({
        action: 'emailAnalyze',
        subject: ctx.subject,
        body: ctx.body
      }, function (response) {
        btn.disabled = false;
        document.dispatchEvent(new CustomEvent('brainos-show-email-result', {
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
