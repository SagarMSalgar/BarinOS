/**
 * BrainOS — Google Calendar: Meeting preparation brief.
 * Injects "Get meeting brief" button; uses page title or selection as meeting title and fetches brief from KB.
 */
(function () {
  if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.id) return;

  function getMeetingTitle() {
    var sel = window.getSelection();
    var t = (sel && sel.toString() || '').trim();
    if (t) return t;
    return (document.title || 'Meeting').replace(/\s*-\s*Google Calendar$/, '').trim();
  }

  function injectButton() {
    if (document.getElementById('brainos-calendar-brief-btn')) return;
    var btn = document.createElement('button');
    btn.id = 'brainos-calendar-brief-btn';
    btn.className = 'brainos-calendar-brief-btn';
    btn.textContent = 'Get meeting brief';
    btn.addEventListener('click', function () {
      var title = getMeetingTitle();
      btn.disabled = true;
      document.dispatchEvent(new CustomEvent('brainos-show-meeting-loading'));
      chrome.runtime.sendMessage({
        action: 'meetingPrep',
        meeting_title: title,
        attendee_names: []
      }, function (response) {
        btn.disabled = false;
        document.dispatchEvent(new CustomEvent('brainos-show-meeting-result', {
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
