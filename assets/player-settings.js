/* Native frontend preferences. No core mutation, network requests or storage credentials. */
(() => {
  'use strict';
  let settings = {scale: 'fit', filter: 'nearest', volume: 80, muted: false}, lastCore = null;
  function apply(value) {
    if (!value || !['fit', 'stretch'].includes(value.scale) || !['nearest', 'linear'].includes(value.filter) || !Number.isInteger(value.volume) || value.volume < 0 || value.volume > 100 || typeof value.muted !== 'boolean') return false;
    settings = {...value}; render(true); return true;
  }
  function render(force = false) {
    const video = document.getElementById('remoteVideo');
    if (video) {
      video.style.setProperty('object-fit', settings.scale === 'stretch' ? 'fill' : 'contain', 'important');
      video.style.imageRendering = settings.filter === 'nearest' ? 'pixelated' : 'auto';
      video.volume = settings.muted ? 0 : settings.volume / 100;
    }
    const core = window.EJS_emulator;
    if (core?.canvas) core.canvas.style.imageRendering = settings.filter === 'nearest' ? 'pixelated' : 'auto';
    if (core?.setVolume && (force || core !== lastCore)) { core.setVolume(settings.muted ? 0 : settings.volume / 100); lastCore = core; }
  }
  window.boogiePlayerSettings = {apply};
  const timer = setInterval(render, 500);
  window.addEventListener('pagehide', () => clearInterval(timer));
})();
