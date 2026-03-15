'use strict';

const DEFAULT_NAMESPACE = 'main';
const DEFAULT_TENANT = 'default';

chrome.runtime.onInstalled.addListener(function () {
  chrome.contextMenus.removeAll(function () {
    chrome.contextMenus.create({
      id: 'brainos-root',
      title: 'BrainOS',
      contexts: ['all']
    });
    chrome.contextMenus.create({
      id: 'brainos-compare',
      parentId: 'brainos-root',
      title: 'Compare with our knowledge',
      contexts: ['selection']
    });
    chrome.contextMenus.create({
      id: 'brainos-factcheck',
      parentId: 'brainos-root',
      title: 'Fact-check against our docs',
      contexts: ['selection']
    });
    chrome.contextMenus.create({
      id: 'brainos-position',
      parentId: 'brainos-root',
      title: "Find our position on this",
      contexts: ['selection']
    });
    chrome.contextMenus.create({
      id: 'brainos-contract',
      parentId: 'brainos-root',
      title: 'Review with ZAYA (contract)',
      contexts: ['page', 'selection']
    });
    chrome.contextMenus.create({
      id: 'brainos-watch',
      parentId: 'brainos-root',
      title: 'Watch this page',
      contexts: ['page']
    });
    chrome.contextMenus.create({
      id: 'brainos-form-fill',
      parentId: 'brainos-root',
      title: 'Fill form with BrainOS',
      contexts: ['page']
    });
    chrome.contextMenus.create({
      id: 'brainos-add-research',
      parentId: 'brainos-root',
      title: 'Add page to research',
      contexts: ['page']
    });
  });
});

function getStorage() {
  return new Promise(function (resolve) {
    chrome.storage.sync.get(['apiBase', 'apiKey', 'tenantId', 'namespace'], resolve);
  });
}

function apiPost(path, body) {
  return getStorage().then(function (items) {
    var apiBase = (items.apiBase || '').trim();
    var apiKey = items.apiKey || '';
    var tenantId = items.tenantId || DEFAULT_TENANT;
    var namespace = (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE;
    if (!apiBase) {
      return Promise.reject(new Error('Set API URL in extension Settings first.'));
    }
    var url = apiBase.replace(/\/$/, '') + path;
    var headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;
    return fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body)
    }).then(function (res) {
      if (!res.ok) return res.text().then(function (t) { throw new Error(t || res.statusText); });
      return res.json();
    });
  });
}

chrome.contextMenus.onClicked.addListener(function (info, tab) {
  if (!tab || !tab.id) return;
  var menuId = info.menuItemId;
  if (menuId === 'brainos-compare' || menuId === 'brainos-factcheck' || menuId === 'brainos-position') {
    var mode = menuId === 'brainos-compare' ? 'compare' : menuId === 'brainos-factcheck' ? 'factcheck' : 'position';
    chrome.tabs.sendMessage(tab.id, { action: 'getSelectionAndRunTextVsKb', mode: mode }, function (selection) {
      if (chrome.runtime.lastError) return;
      var text = (selection && selection.text || '').trim();
      if (!text) return;
      getStorage().then(function (items) {
        var tenantId = items.tenantId || DEFAULT_TENANT;
        var namespace = (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE;
        return apiPost('/api/extension/text-vs-kb', {
          selected_text: text,
          mode: mode,
          tenant_id: tenantId,
          namespace: namespace
        });
      }).then(function (data) {
        chrome.tabs.sendMessage(tab.id, { action: 'showComparisonResult', mode: mode, data: data, selectedText: text });
      }).catch(function (err) {
        chrome.tabs.sendMessage(tab.id, { action: 'showComparisonResult', mode: mode, error: err.message });
      });
    });
    return;
  }
  if (menuId === 'brainos-contract') {
    chrome.tabs.sendMessage(tab.id, { action: 'showContractReview', loading: true });
    chrome.tabs.sendMessage(tab.id, { action: 'getPageText' }, function (resp) {
      if (chrome.runtime.lastError || !resp || !resp.text) {
        chrome.tabs.sendMessage(tab.id, { action: 'showContractReview', error: 'Could not get page text.' });
        return;
      }
      chrome.tabs.sendMessage(tab.id, { action: 'runContractReview', pageText: resp.text });
    });
    return;
  }
  if (menuId === 'brainos-watch') {
    chrome.tabs.sendMessage(tab.id, { action: 'showWatchResult', loading: true });
    chrome.tabs.sendMessage(tab.id, { action: 'getPageText' }, function (resp) {
      if (chrome.runtime.lastError || !resp) return;
      chrome.tabs.sendMessage(tab.id, { action: 'runWatchPage', url: tab.url || '', content: resp.text || '' });
    });
    return;
  }
  if (menuId === 'brainos-form-fill') {
    chrome.tabs.sendMessage(tab.id, { action: 'showFormSuggestPanel', loading: true });
    chrome.tabs.sendMessage(tab.id, { action: 'getFormFields' }, function (resp) {
      if (chrome.runtime.lastError || !resp || !(resp.fields && resp.fields.length)) {
        chrome.tabs.sendMessage(tab.id, { action: 'showFormSuggestPanel', error: 'No form fields found on this page.' });
        return;
      }
      chrome.tabs.sendMessage(tab.id, { action: 'runFormSuggest', field_labels: resp.fields.map(function (f) { return f.label; }) });
    });
    return;
  }
  if (menuId === 'brainos-add-research') {
    chrome.tabs.sendMessage(tab.id, { action: 'getPageText' }, function (resp) {
      if (chrome.runtime.lastError || !resp) return;
      chrome.storage.local.get(['researchSources'], function (local) {
        var list = local.researchSources || [];
        list.push({ url: tab.url, title: resp.title || tab.title || '', text: (resp.text || '').slice(0, 15000) });
        if (list.length > 30) list = list.slice(-30);
        chrome.storage.local.set({ researchSources: list }, function () {
          chrome.tabs.sendMessage(tab.id, { action: 'showAddToResearchResult', data: { message: 'Page added to research (' + list.length + ' sources). Use "Synthesise research" in the extension popup to generate the synthesis.' } });
        });
      });
    });
    return;
  }
});

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.action === 'ask') {
    getStorage().then(function (items) {
      var apiBase = (items.apiBase || '').trim();
      var apiKey = items.apiKey || '';
      var tenantId = items.tenantId || DEFAULT_TENANT;
      var namespace = (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE;
      if (!apiBase) {
        sendResponse({ error: 'Set API URL in extension Settings first.' });
        return;
      }
      var url = apiBase.replace(/\/$/, '') + '/api/chat';
      var headers = { 'Content-Type': 'application/json' };
      if (apiKey) headers['Authorization'] = 'Bearer ' + apiKey;
      return fetch(url, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          tenant_id: tenantId,
          namespace: namespace,
          question: request.question,
          pasted_context: request.pasted_context || undefined
        })
      }).then(function (res) {
        if (!res.ok) return res.text().then(function (t) { throw new Error(t || res.statusText); });
        return res.json();
      }).then(function (data) {
        sendResponse({ answer: data.answer, citations: data.citations, confidence: data.confidence });
      }).catch(function (err) {
        sendResponse({ error: err.message || 'Request failed' });
      });
    });
    return true;
  }
  if (request.action === 'extensionApi') {
    var path = request.path;
    var body = request.body || {};
    getStorage().then(function (items) {
      body.tenant_id = body.tenant_id || items.tenantId || DEFAULT_TENANT;
      body.namespace = body.namespace || (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE;
      return apiPost(path, body);
    }).then(function (data) {
      sendResponse({ ok: true, data: data });
    }).catch(function (err) {
      sendResponse({ ok: false, error: err.message });
    });
    return true;
  }
  if (request.action === 'emailAnalyze') {
    getStorage().then(function (items) {
      return apiPost('/api/extension/email-analyze', {
        subject: request.subject || '',
        body: request.body || '',
        tenant_id: items.tenantId || DEFAULT_TENANT,
        namespace: (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE
      });
    }).then(function (data) {
      sendResponse({ ok: true, data: data });
    }).catch(function (err) {
      sendResponse({ ok: false, error: err.message });
    });
    return true;
  }
  if (request.action === 'meetingPrep') {
    getStorage().then(function (items) {
      return apiPost('/api/extension/meeting-prep', {
        meeting_title: request.meeting_title || '',
        attendee_names: request.attendee_names || [],
        tenant_id: items.tenantId || DEFAULT_TENANT,
        namespace: (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE
      });
    }).then(function (data) {
      sendResponse({ ok: true, data: data });
    }).catch(function (err) {
      sendResponse({ ok: false, error: err.message });
    });
    return true;
  }
  if (request.action === 'verifyClaims') {
    getStorage().then(function (items) {
      return apiPost('/api/extension/verify-claims', {
        claims: request.claims || [],
        tenant_id: items.tenantId || DEFAULT_TENANT,
        namespace: (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE
      });
    }).then(function (data) {
      sendResponse({ ok: true, data: data });
    }).catch(function (err) {
      sendResponse({ ok: false, error: err.message });
    });
    return true;
  }
  if (request.action === 'researchSynthesize') {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var tabId = tabs[0] && tabs[0].id;
      if (tabId) {
        chrome.tabs.sendMessage(tabId, { action: 'showResearchPanel', loading: true });
        chrome.tabs.sendMessage(tabId, { action: 'runResearchSynthesize', sources: request.sources || [] });
      }
      sendResponse({ ok: true });
    });
    return true;
  }
  if (request.action === 'formSuggest') {
    getStorage().then(function (items) {
      return apiPost('/api/extension/form-suggest', {
        field_labels: request.field_labels || [],
        tenant_id: items.tenantId || DEFAULT_TENANT,
        namespace: (items.namespace || DEFAULT_NAMESPACE).trim() || DEFAULT_NAMESPACE
      });
    }).then(function (data) {
      sendResponse({ ok: true, data: data });
    }).catch(function (err) {
      sendResponse({ ok: false, error: err.message });
    });
    return true;
  }
  if (request.action === 'checkWatchPage') {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var tabId = tabs[0] && tabs[0].id;
      if (tabId) {
        chrome.tabs.sendMessage(tabId, { action: 'showWatchResult', loading: true });
        chrome.tabs.sendMessage(tabId, { action: 'runCheckWatchPage', url: request.url || '', content: request.content || '' });
      }
      sendResponse({ ok: true });
    });
    return true;
  }
});
