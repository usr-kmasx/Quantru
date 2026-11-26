(() => {
  let previous;
  async function check() {
    try {
      const response = await fetch('/__version', {cache: 'no-store'});
      if (!response.ok) return;
      const version = await response.text();
      if (previous !== undefined && previous !== version) {
        if (typeof busy !== 'undefined' && (busy || input.value || selectedFiles.length || document.body.classList.contains('voice-active'))) return;
        location.reload();
      }
      previous = version;
    } catch (_) {}
    finally { setTimeout(check, 500); }
  }
  check();
})();
