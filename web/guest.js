/* Private same-origin browser guest. No host credentials or game files. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const roles = {player: 0, player2: 1, spectator: null};
  let generation = 0, credential = '', peerId = '', role = '', port = null;
  let active = false, joining = false, ready = false, approved = false, cursor = 0, pumping = false;
  let showControls = true;
  try { showControls = localStorage.getItem('mayo.controls.visible') !== 'false'; } catch (_) {}
  let iconsOnly=false;try{iconsOnly=localStorage.getItem('mayo.toolbar.icons-only')==='true';}catch(_){}
  function refreshToolbarLabels(){
    const toggle=$('toolbarLabels');
    if(toggle){const text=iconsOnly?'Show labels':'Icons only';if(toggle.textContent!==text)toggle.textContent=text;toggle.setAttribute('aria-pressed',String(iconsOnly));}
    for(const button of $('guestTools').querySelectorAll?.('button')||[]){
      const label=button.id==='toolbarLabels'?(iconsOnly?'Show toolbar button labels':'Switch toolbar to icons only'):button.textContent.trim();
      if(label){button.setAttribute('aria-label',label);button.setAttribute('title',label);}
    }
    $('guest').classList.toggle('toolbar-icons-only',iconsOnly);
  }
  if($('toolbarLabels'))$('toolbarLabels').onclick=()=>{iconsOnly=!iconsOnly;try{localStorage.setItem('mayo.toolbar.icons-only',String(iconsOnly));}catch(_){}refreshToolbarLabels();};
  if(typeof MutationObserver==='function'){const labelsObserver=new MutationObserver(refreshToolbarLabels);labelsObserver.observe($('guestTools'),{childList:true,subtree:true,characterData:true});window.addEventListener('pagehide',()=>labelsObserver.disconnect());}
  refreshToolbarLabels();
  const status = value => { $('connectionStatus').textContent = value; };
  const validCredential = value => typeof value === 'string' && /^[A-Za-z0-9_-]{20,128}$/.test(value);
  const validRole = value => Object.hasOwn(roles, value);
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  function controlsVisible(value) {
    approved = Boolean(value && active);
    window.boogieControllerMapper?.setSession({active, approved, role, port});
    if($('controllerMapper'))$('controllerMapper').textContent=role==='player2'?'Map Player 2':'Map shared P1';
    const canControl = approved && role !== 'spectator';
    window.boogieLayout?.setEnabled(canControl);
    $('toggleControls').hidden = !canControl;
    $('toggleControls').textContent = showControls ? 'Hide controls' : 'Show controls';
    $('toggleControls').setAttribute('aria-pressed', String(showControls));
    $('guest').classList.toggle('controls-hidden', !showControls);
    if (!canControl) releaseKeyboard();
    $('guest').hidden = !active;
    $('touchBoard').hidden = !approved || role === 'spectator';
    $('editLayout').hidden = !approved || role === 'spectator';
    $('joinPanel').hidden = active;
    $('leaveSession').hidden = !active && !joining;
    $('joinButton').disabled = !ready || active || joining;
    refreshToolbarLabels();
    if (active && approved) window.dispatchEvent(new Event('resize'));
  }
  async function api(route, data, auth = credential, {keepalive = false} = {}) {
    if (!/^\/(join|leave|signal|events\?after=\d+&wait=2|client-info)$/.test(route)) throw Error('Unsupported operation');
    const headers = {'Accept': 'application/json'};
    if (auth) headers.Authorization = 'Bearer ' + auth;
    let body;
    if (data !== undefined) { body = JSON.stringify(data); headers['Content-Type'] = 'application/json'; }
    if (body && new TextEncoder().encode(body).length > 73728) throw Error('Message too large');
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(route, {method: data === undefined ? 'GET' : 'POST', headers, body,
        credentials: 'omit', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer',
        signal: controller.signal, keepalive});
      const reader = response.body.getReader();
      let length = 0, chunks = [];
      while (true) { const {value, done} = await reader.read(); if (done) break; length += value.length;
        if (length > 262144) { await reader.cancel(); throw Error('Broker response too large'); } chunks.push(value); }
      const bytes = new Uint8Array(length); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const result = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
      if (!response.ok) throw Error(['invitation_expired','invalid_invitation','session_stopped','unauthorized','room_full','player_slot_occupied'].includes(result.error) ? result.error.replaceAll('_', ' ') : 'Broker request failed');
      return result;
    } finally { clearTimeout(timeout); }
  }
  function stop(message, notify = true) {
    const old = credential;
    ++generation; active = false; joining = false; credential = ''; peerId = ''; cursor = 0;
    window.boogieEvent?.({type: 'stop'});
    window.boogieNativePads?.([null, null, null, null]);
    window.boogieVideoPanel?.close();
    window.boogieControllerMapper?.resetSession();
    window.boogieLayout?.setGame(null);
    $('enableAudio').hidden = false;
    $('invitation').value = '';
    controlsVisible(false); status(message);
    if (notify && old) void api('/leave', {}, old, {keepalive: true}).catch(() => {});
  }
  function event(value, current) {
    if (current !== generation || !active || !value || typeof value !== 'object') return;
    if (value.type === 'approved') {
      const assigned = value.port === undefined && value.role === 'player' ? 0 : value.port;
      if (value.peerId !== peerId || !validRole(value.role) || assigned !== roles[value.role]) { stop('Invalid host approval; join again.'); return; }
      role = value.role; port = assigned;
      $('enableAudio').hidden = false;
      window.boogieEvent?.({type: 'session', selfId: peerId, host: false, role, port});
      window.boogieEvent?.({type: 'peer-approved', peerId: 'host', role, port});
      controlsVisible(true);
      status(role === 'spectator' ? 'Approved to watch · waiting for game video' : 'Approved · player ' + (port + 1) + ' · waiting for video');
    } else if (value.type === 'signal') {
      if (value.from !== 'host' || !value.signal) return;
      const signal = value.signal, message = {type: 'signal', peerId: 'host'};
      if (signal.type === 'candidate') message.candidate = signal.candidate;
      else if (signal.type === 'offer' || signal.type === 'answer') message[signal.type] = {type: signal.type, sdp: signal.sdp};
      else return;
      window.boogieEvent?.(message);
    } else if (value.type === 'resync_required') stop('Session needs fresh approval. Join again.');
  }
  async function poll(current, auth) {
    let errors = 0;
    while (active && current === generation) {
      try {
        const result = await api('/events?after=' + cursor + '&wait=2', undefined, auth);
        if (current !== generation || !active) return;
        if (!Array.isArray(result.events) || result.events.length > 64) throw Error('Invalid events');
        for (const value of result.events) {
          if (!Number.isSafeInteger(value.id) || value.id <= cursor) throw Error('Invalid event cursor');
          cursor = value.id; event(value, current);
        }
        errors = 0;
        // Immediate mock/empty replies must not become a busy loop.
        if (!result.events.length) await delay(100);
      } catch (_) {
        if (current !== generation || !active) return;
        if (++errors >= 3) { stop('Connection lost; controls released. Rejoin for fresh approval.'); return; }
        await delay(500);
      }
    }
  }
  // Compact tools can wrap on narrow screens; keep FPS and touch controls below them.
  let toolsHeight = 0;
  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(() => {
      const measured = Math.max(0, Math.min(480, Math.ceil($('guestTools').getBoundingClientRect().height)));
      if (!measured || measured === toolsHeight) return;
      toolsHeight = measured; $('guest').style.setProperty('--tools-height', measured + 'px');
      window.dispatchEvent(new Event('resize'));
    });
    observer.observe($('guestTools'));
    window.addEventListener('pagehide', () => observer.disconnect());
  }
  $('joinForm').addEventListener('submit', async e => {
    e.preventDefault(); if (!ready || active || joining) return;
    let invite = $('invitation').value;
    $('invitation').value = '';
    const requested = $('joinRole').value, name = $('displayName').value.trim();
    if (!/^[\x21-\x7e]{1,128}$/.test(invite) || !validRole(requested) || !name || name.length > 40 || /[\x00-\x1f\x7f]/.test(name)) { invite = ''; status('Enter an invitation, name and supported role.'); return; }
    const current = ++generation; joining = true; controlsVisible(false); status('Requesting host approval…');
    try {
      const pending = api('/join', {invite, displayName: name, role: requested}, ''); invite = '';
      const response = await pending;
      if (!validCredential(response.peerCredential) || typeof response.peerId !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(response.peerId)) throw Error('Invalid broker join');
      if (current !== generation) { void api('/leave', {}, response.peerCredential).catch(() => {}); return; }
      credential = response.peerCredential; peerId = response.peerId; role = requested; port = roles[requested]; cursor = 0;
      joining = false; active = true;
      window.boogieEvent?.({type: 'session', selfId: peerId, host: false, role, port});
      controlsVisible(false); status('Waiting for the host to approve you…');
      void poll(current, credential);
    } catch (error) { if (current === generation) stop('Could not join: ' + error.message, false); }
    finally { invite = ''; }
  });
  $('leaveSession').onclick = () => stop('Left the session. Join again with a current invitation.');
  $('toggleControls').onclick = () => {
    if (!approved || role === 'spectator') return;
    window.boogieLayout?.cancel(); window.boogieLayout?.release();
    showControls = !showControls;
    try { localStorage.setItem('mayo.controls.visible', String(showControls)); } catch (_) {}
    controlsVisible(true);
  };
  // Keep keyboard and pointer holds independent when both use the same action.
  const pointerActions = new Set(), keyboardHolds = new Map(), rawTouch = window.boogieTouch;
  const publishAction = action => rawTouch?.(action, pointerActions.has(action) || [...keyboardHolds.values()].includes(action));
  window.boogieTouch = (action, down) => {
    if (!Number.isInteger(action) || action < 0 || action > 15 || typeof down !== 'boolean') return;
    if (down) pointerActions.add(action); else pointerActions.delete(action);
    publishAction(action);
  };
  function releaseKeyboard() {
    const actions = new Set(keyboardHolds.values()); keyboardHolds.clear();
    for (const action of actions) publishAction(action);
  }
  const keys = {ArrowUp:4, ArrowDown:5, ArrowLeft:6, ArrowRight:7, KeyW:4, KeyS:5, KeyA:6, KeyD:7,
    KeyZ:8, KeyJ:8, KeyX:0, KeyK:0, Enter:3, ShiftRight:2};
  window.addEventListener('keydown', e => {
    if (!approved || role === 'spectator' || window.boogieLayout?.editing() || window.boogieControllerMapper?.editing() || window.boogieBackdrop?.editing?.() || !$('videoPanel').hidden || e.altKey || e.ctrlKey || e.metaKey) { releaseKeyboard(); return; }
    const target = e.target, control = target?.closest?.('[data-control]');
    if (!control && target?.closest?.('input,textarea,select,button,[contenteditable="true"]')) return;
    const action = control && ['Space','Enter'].includes(e.code) ? Number(control.dataset.action) : keys[e.code];
    if (!Number.isInteger(action)) return;
    e.preventDefault(); if (keyboardHolds.has(e.code)) return;
    keyboardHolds.set(e.code, action); publishAction(action);
  });
  window.addEventListener('keyup', e => {
    if (!keyboardHolds.has(e.code)) return;
    e.preventDefault(); const action = keyboardHolds.get(e.code); keyboardHolds.delete(e.code); publishAction(action);
  });
  window.addEventListener('boogie-mapper-editing', () => {
    const actions = new Set([...pointerActions, ...keyboardHolds.values()]);
    pointerActions.clear(); keyboardHolds.clear();
    for (const action of actions) publishAction(action);
  });
  for (const id of ['editLayout', 'videoQuality']) $(id).addEventListener('click', () => window.boogieControllerMapper?.close(), true);
  window.addEventListener('blur', releaseKeyboard);
  document.addEventListener('visibilitychange', () => { if (document.hidden) releaseKeyboard(); });
  document.addEventListener('focusin', e => { if (!e.target?.closest?.('[data-control]')) releaseKeyboard(); });

  window.BoogieNative = {postMessage(raw) {
    if (typeof raw !== 'string' || raw.length > 73728 || !active) return;
    let message; try { message = JSON.parse(raw); } catch (_) { return; }
    if (!message || typeof message !== 'object' || Array.isArray(message)) return;
    if (message.type === 'approved-metadata' && approved && /^sha256:[a-f0-9]{64}$/.test(message.gameKey)) {
      window.boogieControllerMapper?.setGame(message.gameKey, message.gameTitle);
    } else if (message.type==='mapping-setup-request' && approved && role!=='spectator' && message.role===role && message.port===port) {
      window.boogieControllerMapper?.hostRequest?.(message);
    } else if (message.type === 'signal' && message.target === 'host') {
      const signal = {target: 'host'};
      if (message.offer) { signal.type = 'offer'; signal.sdp = message.offer.sdp; }
      else if (message.answer) { signal.type = 'answer'; signal.sdp = message.answer.sdp; }
      else if (message.candidate) { signal.type = 'candidate'; signal.candidate = message.candidate; }
      else return;
      const current = generation, auth = credential;
      void api('/signal', signal, auth).catch(() => { if (current === generation && active) status('Signaling interrupted; retrying connection.'); });
    } else if (message.type === 'status' && message.connected > 0) status(role === 'spectator' ? 'Watching the host game' : 'Connected · player ' + (port + 1));
  }};
  function samplePads() {
    if (active && !pumping) {
      pumping = true;
      try {
        const rawPads = Array.from(navigator.getGamepads?.() || []);
        const mapped = window.boogieControllerMapper?.sample(rawPads);
        const pads = mapped || rawPads.filter(Boolean).slice(0, 4).map(pad => ({id: String(pad.id).slice(0, 128),
          buttons: Array.from({length: 17}, (_, i) => Math.max(0, Math.min(1, Number(pad.buttons[i]?.value) || 0))),
          axes: Array.from({length: 4}, (_, i) => Math.max(-1, Math.min(1, Number(pad.axes[i]) || 0)))}));
        while (pads.length < 4) pads.push(null);
        window.boogieNativePads?.(document.hidden ? [null, null, null, null] : pads);
      } finally { pumping = false; }
    }
    requestAnimationFrame(samplePads);
  }
  window.addEventListener('pagehide', () => stop('Session closed.'));
  // Fragments do not reach HTTP logs; remove this one from the address/history.
  let fragmentInvite = new URLSearchParams(location.hash.slice(1)).get('invite');
  if (location.hash) { history.replaceState(null, '', location.pathname); status('Invitation fragment removed from the address.'); }
  if (fragmentInvite && /^[\x21-\x7e]{1,128}$/.test(fragmentInvite)) $('invitation').value = fragmentInvite;
  fragmentInvite = null;
  controlsVisible(false); requestAnimationFrame(samplePads);
  void (async () => {
    try {
      if (location.protocol !== 'https:' || !window.isSecureContext) throw Error('Open this guest on the trusted HTTPS broker.');
      const info = await api('/client-info', undefined, '');
      if (info.protocolVersion !== 1 || !Array.isArray(info.roles) || !validRole('player') || !info.roles.includes('player') || !info.roles.includes('spectator')) throw Error('Incompatible broker protocol.');
      $('joinRole').querySelector('[value="player2"]').disabled = !info.roles.includes('player2') || info.ports?.player2 !== 1;
      ready = true; $('compatibility').textContent = 'Protocol 1 · same-origin HTTPS · fresh host approval required';
      controlsVisible(false); status($('invitation').value ? 'Invitation loaded in memory. Choose your role and Join.' : 'Ready for a private LAN invitation.');
    } catch (error) { $('compatibility').textContent = error.message; status('Cannot join this broker.'); }
  })();
})();
