(function () {
  chrome.storage.sync.get(['apiBase', 'apiKey', 'tenantId', 'namespace'], (items) => {
    document.getElementById('apiBase').value = items.apiBase || '';
    document.getElementById('apiKey').value = items.apiKey || '';
    document.getElementById('tenantId').value = items.tenantId || 'default';
    document.getElementById('namespace').value = items.namespace || 'main';
  });
  document.getElementById('save').addEventListener('click', () => {
    const apiBase = document.getElementById('apiBase').value.trim();
    const apiKey = document.getElementById('apiKey').value.trim();
    const tenantId = document.getElementById('tenantId').value.trim() || 'default';
    const namespace = document.getElementById('namespace').value.trim() || 'main';
    chrome.storage.sync.set({ apiBase, apiKey, tenantId, namespace }, () => {
      alert('Settings saved.');
    });
  });
})();
