document.getElementById('open-options').addEventListener('click', function () {
  chrome.runtime.openOptionsPage();
});

function setStatus(msg) {
  var el = document.getElementById('status');
  if (el) el.textContent = msg;
}

document.getElementById('add-page').addEventListener('click', function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs[0];
    if (!tab || !tab.id) {
      setStatus('No active tab.');
      return;
    }
    setStatus('Getting page text…');
    chrome.tabs.sendMessage(tab.id, { action: 'getPageText' }, function (response) {
      if (chrome.runtime.lastError || !response) {
        setStatus('Could not read page (try refreshing the tab).');
        return;
      }
      var text = (response.text || '').trim();
      if (!text) {
        setStatus('No text found on this page.');
        return;
      }
      chrome.storage.sync.get(['apiBase', 'apiKey', 'tenantId', 'namespace'], function (items) {
        var apiBase = (items.apiBase || '').trim();
        if (!apiBase) {
          setStatus('Set API URL in Settings first.');
          return;
        }
        setStatus('Sending to BrainOS…');
        var url = apiBase.replace(/\/$/, '') + '/api/ingest';
        var headers = { 'Content-Type': 'application/json' };
        if (items.apiKey) headers['Authorization'] = 'Bearer ' + items.apiKey;
        fetch(url, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({
            tenant_id: items.tenantId || 'default',
            namespace: (items.namespace || 'main').trim() || 'main',
            document_name: (response.title || tab.url || 'Page').replace(/^https?:\/\//, '').slice(0, 100),
            content: text
          })
        })
          .then(function (res) {
            if (!res.ok) return res.text().then(function (t) { throw new Error(t || res.statusText); });
            return res.json();
          })
          .then(function () {
            setStatus('Page added to BrainOS.');
          })
          .catch(function (err) {
            setStatus('Error: ' + (err.message || 'Failed'));
          });
      });
    });
  });
});

document.getElementById('add-research').addEventListener('click', function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs[0];
    if (!tab || !tab.id) {
      setStatus('No active tab.');
      return;
    }
    chrome.tabs.sendMessage(tab.id, { action: 'getPageText' }, function (response) {
      if (chrome.runtime.lastError || !response) {
        setStatus('Could not read page.');
        return;
      }
      chrome.storage.local.get(['researchSources'], function (local) {
        var list = local.researchSources || [];
        list.push({
          url: tab.url,
          title: response.title || tab.title || '',
          text: (response.text || '').slice(0, 15000)
        });
        if (list.length > 30) list = list.slice(-30);
        chrome.storage.local.set({ researchSources: list }, function () {
          setStatus('Added to research (' + list.length + ' sources).');
          document.getElementById('research-count').textContent = list.length + ' source(s) in research.';
        });
      });
    });
  });
});

document.getElementById('synthesise').addEventListener('click', function () {
  chrome.storage.local.get(['researchSources'], function (local) {
    var list = local.researchSources || [];
    if (list.length === 0) {
      setStatus('Add pages to research first.');
      return;
    }
    setStatus('Synthesising…');
    chrome.runtime.sendMessage({
      action: 'researchSynthesize',
      sources: list.map(function (s) { return (s.title || '') + '\n\n' + (s.text || ''); })
    }, function (response) {
      if (chrome.runtime.lastError) {
        setStatus('Error: ' + (chrome.runtime.lastError.message || 'Failed'));
        return;
      }
      if (response && response.error) {
        setStatus('Error: ' + response.error);
        return;
      }
      setStatus('Done. See panel on page.');
    });
  });
});

document.getElementById('check-watch').addEventListener('click', function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs[0];
    if (!tab || !tab.id) {
      setStatus('No active tab.');
      return;
    }
    setStatus('Checking…');
    chrome.tabs.sendMessage(tab.id, { action: 'getPageText' }, function (response) {
      if (chrome.runtime.lastError || !response) {
        setStatus('Could not read page.');
        return;
      }
      chrome.runtime.sendMessage({
        action: 'checkWatchPage',
        url: tab.url,
        content: response.text || ''
      }, function (res) {
        if (chrome.runtime.lastError) {
          setStatus('Error.');
          return;
        }
        setStatus(res && res.error ? res.error : 'Check done. See panel on page.');
      });
    });
  });
});

chrome.storage.local.get(['researchSources'], function (local) {
  var n = (local.researchSources || []).length;
  var el = document.getElementById('research-count');
  if (el) el.textContent = n + ' source(s) in research.';
});

chrome.storage.sync.get(['apiBase', 'tenantId', 'namespace'], function (items) {
  var apiBase = (items.apiBase || '').trim();
  if (!apiBase) return;
  var tenantId = items.tenantId || 'default';
  var namespace = (items.namespace || 'main').trim() || 'main';
  var url = apiBase.replace(/\/$/, '') + '/api/extension/watched-pages?tenant_id=' + encodeURIComponent(tenantId) + '&namespace=' + encodeURIComponent(namespace) + '&user_key=default';
  fetch(url).then(function (r) { return r.json(); }).then(function (data) {
    var list = data.watched || [];
    var el = document.getElementById('watched-list');
    if (!el) return;
    if (list.length === 0) {
      el.textContent = 'No watched pages. Right-click a page → "Watch this page (BrainOS)".';
      return;
    }
    el.textContent = list.slice(0, 10).map(function (w) { return w.url; }).join('\n') + (list.length > 10 ? '\n... and ' + (list.length - 10) + ' more' : '');
  }).catch(function () {
    var el = document.getElementById('watched-list');
    if (el) el.textContent = '';
  });
});
