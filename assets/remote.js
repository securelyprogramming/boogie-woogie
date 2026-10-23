/* Private Boogie Woogie LAN prototype. Host owns the emulator and input authority. */
(() => {
  'use strict';
  const zero = () => Array(16).fill(0);
  const state = {session: null, peers: new Map(), sources: new Map(), output: zero(), outputs: Array.from({length:4},zero), core: null,
    original: null, stream: null, canvas: null, viewportCapture:null, viewportDisabled:false, audio: null, audioNodes: new Set(),
    presentationFreezes:0,presentationGapSeconds:0,generation: 0, accepted: 0, rejected: 0, stale: 0, effects: 0, videoFrames: 0,
    audioPeak: 0, audioSignalObserved: false, lastStatus: 0, lastSent: 0, seq: 0,
    touch: zero(), native: zero(), ejs: zero(), focused: true, checkpoint:false, editing:false, nativeMapping:false, localNeutralRequired:false, lastMappingSetupAt:-Infinity, gameArtwork:null,artworkVersion:0, error: ''};
  const now = () => performance.now();
  const send = message => {
    try { window.BoogieNative?.postMessage(JSON.stringify(message)); } catch (_) {}
  };
  const fail = code => { state.error = code; status(true); };
  const validPeer = id => typeof id === 'string' && /^[a-zA-Z0-9_-]{1,80}$/.test(id);
  const gameIdentity = v => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v) ? v : null;
  const rolePort = role => role === 'player' ? 0 : role === 'player2' ? 1 : null;
  const validRole = role => ['player','player2','spectator'].includes(role);
  const validApprovedPort = (role, port) => validRole(role) && (port === rolePort(role) || (role !== 'player2' && port === undefined));
  const merge = values => {
    const result = zero();
    for (const source of values) for (let i = 0; i < 16; i++) result[i] |= source[i] ? 1 : 0;
    for (const [a, b] of [[4, 5], [6, 7]]) if (result[a] && result[b]) result[a] = result[b] = 0;
    return result;
  };
  const debug = () => {
    const incoming = state.peers.get('host')?.incoming;
    const media = state.session?.host ? state.stream : incoming;
    const video = document.getElementById('remoteVideo');
    return {active: !!state.session, host: !!state.session?.host,
    gameKey:state.session?.gameKey||null, role: state.session?.role || '', port: state.session?.port ?? null, portMasks:state.outputs.map(v=>v.reduce((a,b,i)=>a+(b?2**i:0),0)), peers: state.peers.size,
    connected: [...state.peers.values()].filter(p => p.pc.connectionState === 'connected').length,
    captureViewport:state.viewportCapture?.rectangle?.()||null,coreReady: !!state.core, videoTrack: !!media?.getVideoTracks().some(t => t.readyState === 'live'),
    audioTapConnected: state.audioNodes.size > 0,
    audioTrack: !!media?.getAudioTracks().some(t => t.readyState === 'live'),
    audioSignalObserved: state.audioSignalObserved, audioPeak: Math.round(state.audioPeak * 10000) / 10000,
    acceptedInputs: state.accepted, rejectedInputs: state.rejected, staleReleases: state.stale,
    coreInputChanges: state.effects, inputMask: state.output.reduce((a, v, i) => a + (v ? 2 ** i : 0), 0),
    presentationFreezes:state.presentationFreezes,presentationGapSeconds:state.presentationGapSeconds,videoFrames: state.videoFrames, videoWidth: video?.videoWidth || 0, videoHeight: video?.videoHeight || 0,
    audioMuted: video ? video.muted : null, focused: state.focused, error: state.error};
  };
  function status(force) {
    if (!force && now() - state.lastStatus < 1000) return;
    state.lastStatus = now(); send({type: 'status', ...debug()});
  }
  function apply() {
    if (!state.session?.host || !state.original) return;
    for (let port=0;port<4;port++) {
      const next=state.checkpoint?zero():merge([...state.sources.values()].filter(v=>v.port===port).map(v=>v.buttons));
      for(let i=0;i<16;i++)if(next[i]!==state.outputs[port][i]){state.original(port,i,next[i]);state.effects++;}
      state.outputs[port]=next;
    }
    state.output=state.outputs[0];
  }
  function setSource(id, value, port=0) {
    if(!Number.isInteger(port)||port<0||port>3)return reject();
    state.sources.set(id,{port,buttons:state.checkpoint?zero():value.slice()});apply();
  }
  function clearLocal() {
    state.touch = zero(); state.native = zero(); state.ejs = zero();
    for (const key of [...state.sources.keys()]) if (!key.startsWith('remote:')) state.sources.delete(key);
    apply(); guestSnapshot(true);
  }
  function installCore() {
    const engine = window.EJS_emulator, manager = engine?.gameManager;
    if (!state.session?.host || engine?.started !== true || !manager?.functions?.simulateInput || state.core === manager) return;
    if (state.core) detachCore();
    state.core = manager;
    const original = manager.functions.simulateInput;
    state.original = original.bind(manager.functions);
    state.wrapper = function(port, action, value) {
      if (Number.isInteger(port) && port >= 0 && port < 4 && Number.isInteger(action) && action >= 0 && action < 16 && state.session?.host) {
        const key='ejs:'+port, previous=state.sources.get(key)?.buttons || zero();
        previous[action]=value?1:0;
        setSource(key,state.focused&&!state.editing?previous:zero(),port);
        return;
      }
      return original.call(this, port, action, value);
    };
    state.rawOriginal = original; manager.functions.simulateInput = state.wrapper;
    apply();
  }
  function detachCore() {
    if (state.original) {
      for(let port=0;port<4;port++)for(let i=0;i<16;i++)if(state.outputs[port][i])state.original(port,i,0);
    }
    if (state.core && state.core.functions.simulateInput === state.wrapper) state.core.functions.simulateInput = state.rawOriginal;
    state.core = null; state.original = null; state.output = zero();state.outputs=Array.from({length:4},zero);
  }
  function tapAudio() {
    if (!state.stream) return;
    const engine = window.EJS_emulator, manager = engine?.gameManager;
    const al = (manager?.Module || engine?.Module)?.AL?.currentCtx;
    const candidates = [manager?.audioNode, ...Object.values(al?.sources || {}).map(s => s?.gain)].filter(n => n?.connect && n?.context);
    if (!state.audio && candidates.length) {
      const context = candidates[0].context;
      const destination = context.createMediaStreamDestination(), analyser = context.createAnalyser();
      analyser.fftSize = 512; analyser.connect(destination);
      state.audio = {context, destination, analyser, samples: new Float32Array(analyser.fftSize)};
      for (const track of destination.stream.getAudioTracks()) {
        state.stream.addTrack(track);
        for (const peer of state.peers.values()) if (peer.pc.connectionState !== 'closed') {
          peer.pc.addTrack(track, state.stream); offer(peer);
        }
      }
    }
    if (!state.audio) return;
    for (const node of candidates) if (node.context === state.audio.context) {
      // OpenAL can disconnect/rebuild its graph after initial startup or resume.
      // Web Audio ignores duplicate connections between the same output/input.
      try { node.connect(state.audio.analyser); state.audioNodes.add(node); } catch (_) {}
    }
    state.audio.analyser.getFloatTimeDomainData(state.audio.samples);
    let peak = 0;
    for (const value of state.audio.samples) peak = Math.max(peak, Math.abs(value));
    state.audioPeak = Math.max(state.audioPeak * .98, peak);
    if (peak > .0001) state.audioSignalObserved = true;
  }
  function ensureMedia() {
    if (!state.session?.host || !state.core) return false;
    const canvas = window.EJS_emulator?.canvas;
    if (!canvas || !canvas.width || !canvas.height || typeof canvas.captureStream !== 'function') return false;
    if(state.viewportCapture?.failed?.()){
      const retired=state.viewportCapture,previous=state.stream;
      try{
        const replacement=canvas.captureStream(30),track=replacement.getVideoTracks()[0];if(!track)throw Error('no-fallback-video');
        for(const audio of previous.getAudioTracks())replacement.addTrack(audio);
        state.viewportCapture=null;state.stream=replacement;state.canvas=canvas;state.viewportDisabled=true;window.boogieBackdrop?.clearViewport?.();
        const swaps=[];for(const peer of state.peers.values())for(const sender of peer.pc.getSenders())if(sender.track?.kind==='video'&&typeof sender.replaceTrack==='function')swaps.push(sender.replaceTrack(track));
        if(swaps.length)Promise.allSettled(swaps).then(results=>{retired.close();if(results.some(result=>result.status==='rejected'))fail('video-fallback-failed');});else retired.close();
      }catch(_){fail('canvas-capture-failed');return false;}
    }
    if (!state.stream) {
      try {
        try{const capture=!state.viewportDisabled&&window.MayoViewportCapture?.start({document,getSource:()=>window.EJS_emulator?.canvas,getMetadata:()=>{
          const engine=window.EJS_emulator;return {aspect:engine?.gameManager?.getVideoDimensions?.('aspect'),rotation:Number(engine?.getSettingValue?.('videoRotation')||0)};
        },onViewport:(source,rectangle)=>window.boogieBackdrop?.setViewport?.(source,rectangle),requestFrame:typeof requestAnimationFrame==='function'?requestAnimationFrame:null,cancelFrame:typeof cancelAnimationFrame==='function'?cancelAnimationFrame:null});
          if(capture){state.viewportCapture=capture;state.stream=capture.stream;state.canvas=capture.canvas;}
        }catch(_){}
        if(!state.stream){state.stream = canvas.captureStream(30); state.canvas = canvas;}
        if (!state.stream.getVideoTracks().length) throw Error('no-video');
      } catch (_) { state.viewportCapture?.close();state.viewportCapture=null;for(const track of state.stream?.getTracks?.()||[])track.stop();state.stream = null; fail('canvas-capture-failed'); return false; }
    }
    if(state.viewportCapture&&!state.viewportCapture.ready())return false;
    tapAudio(); return true;
  }
  function signal(peer, value) { send({type: 'signal', target: peer.id, ...value}); }
  async function offer(peer) {
    peer.needsOffer = true;
    if (!state.session?.host || peer.offering || peer.pc.signalingState !== 'stable') return;
    peer.needsOffer = false;
    peer.offering = true;
    try {
      await peer.pc.setLocalDescription(await peer.pc.createOffer());
      if (state.peers.get(peer.id) === peer) signal(peer, {offer: peer.pc.localDescription.toJSON()});
    } catch (_) { fail('offer-failed'); } finally { peer.offering = false; }
  }
  function grant(peer) {
    if (!state.session?.host || peer.dc?.readyState !== 'open') return;
    const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    peer.nonce = [...bytes].map(x => x.toString(16).padStart(2, '0')).join('');
    peer.seq = -1; peer.lastInput = now(); peer.grantAcknowledged = false; peer.awaitNeutral = true;
    peer.dc.send(JSON.stringify({t: 'grant', nonce: peer.nonce, role: peer.role, port: peer.port, gameKey:state.session.gameKey,hostLabel:state.session.hostLabel,gameTitle:state.session.gameTitle}));sendArtwork(peer);
  }
  const videoProfiles = {smooth:{maxWidth:480,maxBitrate:700000,maxFramerate:30},balanced:{maxWidth:720,maxBitrate:1200000,maxFramerate:30},sharp:{maxWidth:1920,maxBitrate:2000000,maxFramerate:30}};
  const validQuality = value => typeof value === 'string' && Object.prototype.hasOwnProperty.call(videoProfiles,value);
  async function applyQuality(peer) {
    if (!state.session?.host || state.peers.get(peer.id)!==peer || peer.qualityApplying || peer.pc.connectionState!=='connected') return;
    const sender=peer.pc.getSenders?.().find(s=>s.track?.kind==='video');
    if(!sender)return;
    const profile=peer.quality||'smooth',p=videoProfiles[profile],width=state.canvas?.width||1;
    peer.qualityApplying=true;
    let result='unsupported';
    try{const params=sender.getParameters();if(!params.encodings?.length)throw Error();for(const encoding of params.encodings){encoding.maxBitrate=Math.floor(p.maxBitrate/params.encodings.length);encoding.maxFramerate=p.maxFramerate;encoding.scaleResolutionDownBy=Math.max(1,width/p.maxWidth);}params.degradationPreference='maintain-framerate';await sender.setParameters(params);result='applied';}catch(_){}
    finally{peer.qualityApplying=false;}
    if(state.peers.get(peer.id)!==peer)return;
    peer.appliedQuality=profile;peer.qualityResult=result;peer.qualityWidth=width;
    if(peer.dc?.readyState==='open')peer.dc.send(JSON.stringify({t:'quality-applied',profile,result}));
    if(peer.quality!==profile)void applyQuality(peer);
  }
  function requestQuality() {
    if(!state.session||state.session.host)return;
    const peer=state.peers.get('host'),profile=window.boogieQualityPreference?.()||'smooth';
    if(!validQuality(profile)||!peer?.nonce||peer.dc?.readyState!=='open')return;
    peer.dc.send(JSON.stringify({t:'quality',nonce:peer.nonce,profile}));peer.lastQualitySent=now();
  }
  window.boogieRequestQuality = value => {if(validQuality(value))requestQuality();};
  window.boogieMediaStats = async () => {
    const result=[];
    for(const peer of state.peers.values()){
      const reports=await peer.pc.getStats();if(state.peers.get(peer.id)!==peer)continue;const stats=[...reports.values()];
      const pair=stats.find(r=>r.type==='candidate-pair'&&r.state==='succeeded'&&r.nominated);
      for(const r of stats)if((r.type==='inbound-rtp'||r.type==='outbound-rtp')&&(r.kind==='video'||r.mediaType==='video')){
        const out={direction:r.type==='inbound-rtp'?'inbound':'outbound',timestamp:r.timestamp,profile:peer.appliedQuality||peer.quality||'smooth',limitsResult:peer.qualityResult||'pending'};
        for(const key of ['framesDecoded','framesDropped','framesReceived','framesEncoded','framesSent','bytesReceived','bytesSent','packetsReceived','packetsSent','packetsLost','jitterBufferDelay','jitterBufferEmittedCount','totalDecodeTime','totalEncodeTime','totalInterFrameDelay','totalSquaredInterFrameDelay','freezeCount','totalFreezesDuration','framesPerSecond','frameWidth','frameHeight','qualityLimitationReason','encoderImplementation','decoderImplementation','powerEfficientEncoder','powerEfficientDecoder'])if(typeof r[key]==='number'||typeof r[key]==='string'||typeof r[key]==='boolean')out[key]=r[key];
        const codec=stats.find(c=>c.id===r.codecId);if(codec?.mimeType)out.codec=codec.mimeType;if(r.qualityLimitationDurations)out.qualityLimitationDurations={cpu:r.qualityLimitationDurations.cpu||0,bandwidth:r.qualityLimitationDurations.bandwidth||0,none:r.qualityLimitationDurations.none||0};if(r.type==='inbound-rtp'){out.presentedFrames=state.videoFrames;out.presentationFreezes=state.presentationFreezes;out.presentationGapSeconds=state.presentationGapSeconds;}if(r.type==='outbound-rtp'){out.sourceWidth=state.canvas?.width||0;out.sourceHeight=state.canvas?.height||0;const sender=peer.pc.getSenders?.().find(s=>s.track?.kind==='video');out.senderLimits=(sender?.getParameters().encodings||[]).map(e=>({maxBitrate:e.maxBitrate,maxFramerate:e.maxFramerate,scaleResolutionDownBy:e.scaleResolutionDownBy}));}out.jitterMs=(r.jitter||0)*1000;out.rttMs=(pair?.currentRoundTripTime||0)*1000;
        result.push(out);
      }
    }
    return result;
  };
  function reject() { state.rejected++; }
  function acceptInput(peer, data) {
    if (!state.session?.host || state.peers.get(peer.id) !== peer) return reject();
    const timestamp = now();
    if (timestamp - peer.rateWindow >= 1000) { peer.rateWindow = timestamp; peer.rateCount = 0; }
    if (++peer.rateCount > 120 || typeof data !== 'string' || new TextEncoder().encode(data).length > 512) return reject();
    let msg; try { msg = JSON.parse(data); } catch (_) { return reject(); }
    if(msg?.t==='art-request'){if(Object.keys(msg).sort().join(',')!=='gameKey,nonce,t'||!peer.nonce||msg.nonce!==peer.nonce||msg.gameKey!==state.session.gameKey||!gameIdentity(msg.gameKey)||timestamp-(peer.lastArtReplyAt??-Infinity)<2000)return reject();peer.lastArtReplyAt=timestamp;sendArtwork(peer);return;}
    if(msg?.t==='quality'){if(!validRole(peer.role)||msg.nonce!==peer.nonce||!peer.nonce||!validQuality(msg.profile)||timestamp-(peer.lastQualityRequest??-Infinity)<1000)return reject();peer.lastQualityRequest=timestamp;peer.grantAcknowledged=true;peer.quality=msg.profile;void applyQuality(peer);return;}
    if (state.checkpoint || !state.focused || peer.port === null || msg?.t !== 'input' || Object.hasOwn(msg,'port') || msg.nonce !== peer.nonce || !peer.nonce ||
        !Number.isSafeInteger(msg.seq) || msg.seq <= peer.seq || msg.seq < 0 ||
        !Array.isArray(msg.buttons) || msg.buttons.length !== 16 || !msg.buttons.every(v => v === 0 || v === 1)) return reject();
    peer.seq = msg.seq; peer.lastInput = timestamp; peer.grantAcknowledged = true;
    if (peer.awaitNeutral) {
      if (msg.buttons.some(Boolean)) return reject();
      peer.awaitNeutral = false;
    }
    state.accepted++;
    setSource('remote:' + peer.id, msg.buttons, peer.port);
  }
  function sendArtwork(peer){const art=state.gameArtwork;if(!state.session?.host||!art||art.gameKey!==state.session.gameKey||!peer.nonce||peer.dc?.readyState!=='open'||peer.dc.bufferedAmount>70000)return false;try{peer.dc.send(JSON.stringify({t:'game-art',nonce:peer.nonce,...art}));return true;}catch(_){return false;}}
  async function publishGameArtwork(value){
    if(!state.session?.host)return false;const art=window.MayoBackdropModel?.artwork(value);if(!art||art.gameKey!==state.session.gameKey||Object.keys(value).sort().join(',')!=='data,gameKey,height,mime,sha256,width')return false;
    const generation=state.generation,game=state.session.gameKey,version=++state.artworkVersion;try{const digest=await crypto.subtle.digest('SHA-256',art.bytes),sha=[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');if(sha!==art.sha256||generation!==state.generation||version!==state.artworkVersion||!state.session?.host||game!==state.session.gameKey)return false;}catch(_){return false;}
    if(state.gameArtwork?.sha256===art.sha256)return true;const {bytes,...safe}=art;state.gameArtwork=safe;for(const peer of state.peers.values())sendArtwork(peer);return true;
  }
  function requestArtwork(peer){if(state.session?.host||!peer.nonce||!peer.grantedGameKey||peer.artReceived||peer.artRequests>=3||now()-(peer.lastArtRequestAt??-Infinity)<2000||peer.dc?.readyState!=='open')return;try{peer.dc.send(JSON.stringify({t:'art-request',nonce:peer.nonce,gameKey:peer.grantedGameKey}));peer.artRequests=(peer.artRequests||0)+1;peer.lastArtRequestAt=now();}catch(_){} }
  async function receiveArtwork(peer,msg){
    if(state.session?.host||!peer.nonce||msg.nonce!==peer.nonce||msg.gameKey!==peer.grantedGameKey||!peer.grantedGameKey||Object.keys(msg).sort().join(',')!=='data,gameKey,height,mime,nonce,sha256,t,width')return reject();
    if(peer.artSHA===msg.sha256)return;if(now()-(peer.lastArtAttemptAt??-Infinity)<2000)return reject();const art=window.MayoBackdropModel?.artwork(msg);if(!art)return reject();peer.lastArtAttemptAt=now();const nonce=peer.nonce,game=peer.grantedGameKey,generation=state.generation,version=peer.artGeneration=(peer.artGeneration||0)+1;
    try{const digest=await crypto.subtle.digest('SHA-256',art.bytes),sha=[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');if(sha!==art.sha256||generation!==state.generation||version!==peer.artGeneration||state.peers.get('host')!==peer||peer.nonce!==nonce||peer.grantedGameKey!==game)return reject();
      const accepted=window.boogieBackdrop?.applyVerifiedGuestArtwork?.('data:image/jpeg;base64,'+art.data,game);if(accepted===false)return reject();peer.artSHA=sha;peer.artReceived=true;
    }catch(_){reject();}
  }
  function mappingSetup(peer, msg) {
    const session=state.session, game=gameIdentity(msg.gameKey), timestamp=now();
    if (!session || session.host || session.port===null || !['player','player2'].includes(session.role) ||
        !peer.nonce || msg.nonce!==peer.nonce || msg.role!==session.role || msg.port!==session.port ||
        !game || game!==peer.grantedGameKey || typeof msg.requestId!=='string' || !/^[a-f0-9]{32}$/.test(msg.requestId)) return reject();
    peer.mappingRequests ||= new Set();
    if (peer.mappingRequests.has(msg.requestId) || timestamp-(peer.lastMappingSetupAt??-Infinity)<2000) return reject();
    peer.mappingRequests.add(msg.requestId);while(peer.mappingRequests.size>32)peer.mappingRequests.delete(peer.mappingRequests.values().next().value);
    peer.lastMappingSetupAt=timestamp;
    // Only this guest's inputs are quarantined. Other players and the core keep running.
    state.localNeutralRequired=true;clearLocal();
    send({type:'mapping-setup-request',role:session.role,port:session.port,gameKey:game,requestId:msg.requestId});
  }
  function requestMappingSetup() {
    if (!state.session?.host || !gameIdentity(state.session.gameKey) || now()-state.lastMappingSetupAt<2000) return 0;
    const peers=[...state.peers.values()].filter(peer=>['player','player2'].includes(peer.role)&&peer.port===rolePort(peer.role)&&
      /^[a-f0-9]{32}$/.test(peer.nonce||'')&&peer.dc?.readyState==='open'&&peer.dc.bufferedAmount<=4096);
    if(!peers.length)return 0;
    const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);const requestId=[...bytes].map(v=>v.toString(16).padStart(2,'0')).join('');
    let count=0;for(const peer of peers)try{peer.dc.send(JSON.stringify({t:'mapping-setup',nonce:peer.nonce,requestId,
      role:peer.role,port:peer.port,gameKey:state.session.gameKey}));count++;}catch(_){}
    if(count)state.lastMappingSetupAt=now();return count;
  }
  function channel(peer, dc) {
    if (peer.dc) { dc.close(); return; }
    peer.dc = dc;
    dc.onopen = () => { if (state.session?.host) grant(peer); };
    dc.onmessage = event => {
      if(state.peers.get(peer.id)!==peer)return reject();
      if (state.session?.host) return acceptInput(peer, event.data);
      if (typeof event.data !== 'string' || new TextEncoder().encode(event.data).length > 70000) return reject();
      let msg; try { msg = JSON.parse(event.data); } catch (_) { return reject(); }
      if(msg?.t==='game-art'){void receiveArtwork(peer,msg);return;}
      if(new TextEncoder().encode(event.data).length>512)return reject();
      if (msg?.t === 'grant' && /^[a-f0-9]{32}$/.test(msg.nonce) && validRole(msg.role) && msg.role === state.session?.role &&
          msg.port === state.session.port) {
        if (peer.nonce !== msg.nonce) state.seq = 0;
        const nextGame=gameIdentity(msg.gameKey),fresh=peer.nonce!==msg.nonce||peer.grantedGameKey!==nextGame;peer.nonce=msg.nonce;peer.grantedGameKey=nextGame;state.session.gameKey=nextGame;if(fresh){peer.artSHA='';peer.artReceived=false;peer.artRequests=0;peer.lastArtRequestAt=-Infinity;peer.lastArtAttemptAt=-Infinity;window.boogieBackdrop?.clearGameArtwork?.();}requestArtwork(peer); requestQuality(); window.boogieLayout?.setGame(gameIdentity(msg.gameKey)); if(fresh && gameIdentity(msg.gameKey))send({type:"approved-metadata",gameKey:msg.gameKey,hostLabel:typeof msg.hostLabel === "string" ? msg.hostLabel.slice(0,48):"LAN host",gameTitle:typeof msg.gameTitle === "string" ? msg.gameTitle.slice(0,80):"NES game"}); guestSnapshot(true);
      } else if(msg?.t==='mapping-setup'){mappingSetup(peer,msg);} else if(msg?.t==='quality-applied'&&validQuality(msg.profile)&&['applied','unsupported'].includes(msg.result)){peer.appliedQuality=msg.profile;peer.qualityResult=msg.result;window.boogieQualityAck?.(msg.profile,msg.result);}else reject();
    };
    dc.onclose = () => { peer.nonce = ''; if(state.peers.get(peer.id)!==peer)return; state.sources.delete('remote:' + peer.id); apply(); };
  }
  function videoStream(peer, event) {
    if (state.session?.host) return;
    const video = document.getElementById('remoteVideo');
    if (!video) { fail('missing-remote-video'); return; }
    video.autoplay = true; video.playsInline = true; video.controls = false; video.muted = true;
    const stream = event.streams?.[0] || peer.incoming || new MediaStream();
    if (!event.streams?.[0] && !stream.getTracks().includes(event.track)) stream.addTrack(event.track);
    peer.incoming = stream; video.srcObject = stream; video.play().catch(() => fail('video-play-needs-gesture'));
    if (typeof video.requestVideoFrameCallback === 'function' && !peer.frameCounter) {
      peer.frameCounter = true;
      const frame = (_,metadata) => { if (state.peers.get(peer.id)!==peer||video.srcObject!==peer.incoming) return; const at=now();if(peer.lastFrameAt&&at-peer.lastFrameAt>500&&state.focused&&!document.hidden){state.presentationFreezes++;state.presentationGapSeconds+=(at-peer.lastFrameAt)/1000;}peer.lastFrameAt=at;const count=metadata?.presentedFrames;state.videoFrames+=Number.isFinite(count)?Math.max(1,count-(peer.lastPresentedFrames??count-1)):1;peer.lastPresentedFrames=count;video.requestVideoFrameCallback(frame); };
      video.requestVideoFrameCallback(frame);
    }
    let audioButton = document.getElementById('enableAudio') || document.getElementById('boogieEnableAudio');
    if (!audioButton) {
      audioButton = document.createElement('button'); audioButton.id = 'boogieEnableAudio';
      audioButton.textContent = 'Enable game audio'; audioButton.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999';
      document.body.appendChild(audioButton);
    }
    audioButton.hidden = false; // A new track/session starts muted and needs a reachable gesture.
    audioButton.onclick = () => { video.muted = false; video.play().then(() => { audioButton.hidden = true; if (state.error === 'video-play-needs-gesture') state.error = ''; }).catch(() => { video.muted = true; }); };
  }
  function makePeer(id, role, port=rolePort(role)) {
    if (state.peers.has(id)) {
      const existing = state.peers.get(id);
      if (existing.role === role && existing.port === port) return existing;
      removePeer(id); // Revoke the old capability and every held input before changing roles.
    }
    const pc = new RTCPeerConnection({iceServers: []});
    const peer = {id, role, port, pc, quality:'smooth', dc: null, nonce: '', seq: -1, lastInput: now(), rateWindow: now(), rateCount: 0, ice: [], offering: false};
    state.peers.set(id, peer);
    pc.onicecandidate = event => { if (state.peers.get(id)===peer&&event.candidate) signal(peer, {candidate: event.candidate.toJSON()}); };
    pc.onconnectionstatechange = () => {
      if(state.peers.get(id)!==peer)return;
      if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) {
        state.sources.delete('remote:' + id); apply();if(!state.session?.host){state.error='connection-interrupted';state.touch=zero();state.native=zero();window.boogieConnectionState?.('interrupted');}
      }
      if(pc.connectionState==='connected'){if(state.error==='connection-interrupted')state.error='';window.boogieConnectionState?.('connected');void applyQuality(peer);}
      status(true);
    };
    pc.onnegotiationneeded = () => { if (state.session?.host) void offer(peer); };
    pc.onsignalingstatechange = () => { if (peer.needsOffer && pc.signalingState === 'stable') void offer(peer); };
    pc.ontrack = event => {if(state.peers.get(id)===peer)videoStream(peer,event);};
    pc.ondatachannel = event => {
      if (state.session?.host || event.channel.label !== 'boogie-input') { event.channel.close(); return; }
      channel(peer, event.channel);
    };
    if (state.session.host) {
      for (const track of state.stream.getTracks()) pc.addTrack(track, state.stream);
      channel(peer, pc.createDataChannel('boogie-input', {ordered: false, maxRetransmits: 0}));
      offer(peer);
    }
    return peer;
  }
  function removePeer(id) {
    const peer = state.peers.get(id); if (!peer) return;
    state.peers.delete(id); state.sources.delete('remote:' + id); apply();
    try { peer.dc?.close(); peer.pc.close(); } catch (_) {}
  }
  async function remoteSignal(event) {
    if (!state.session || !validPeer(event.peerId)) return;
    let peer = state.peers.get(event.peerId);
    if (!peer && !state.session.host && event.peerId === 'host') peer = makePeer('host', state.session.role, state.session.port);
    if (!peer) return reject(); // Native approval is mandatory on the host.
    try {
      if (event.offer) {
        if (state.session.host || event.offer.type !== 'offer' || typeof event.offer.sdp !== 'string' || event.offer.sdp.length > 65536) return reject();
        await peer.pc.setRemoteDescription(event.offer);
        for (const ice of peer.ice.splice(0)) await peer.pc.addIceCandidate(ice);
        await peer.pc.setLocalDescription(await peer.pc.createAnswer());
        if (state.peers.get(peer.id) === peer) signal(peer, {answer: peer.pc.localDescription.toJSON()});
      } else if (event.answer) {
        if (!state.session.host || event.answer.type !== 'answer' || typeof event.answer.sdp !== 'string' || event.answer.sdp.length > 65536) return reject();
        await peer.pc.setRemoteDescription(event.answer);
        for (const ice of peer.ice.splice(0)) await peer.pc.addIceCandidate(ice);
      } else if (event.candidate) {
        const candidate = event.candidate;
        if (typeof candidate.candidate !== 'string' || candidate.candidate.length > 4096) return reject();
        if (peer.pc.remoteDescription) await peer.pc.addIceCandidate(candidate);
        else if (peer.ice.length < 64) peer.ice.push(candidate);
        else reject();
      }
    } catch (_) { fail('signal-apply-failed'); }
  }
  function guestSnapshot(force) {
    if (!state.session || state.session.host || state.session.port === null || (!force && now() - state.lastSent < 1000 / 60)) return;
    const peer = state.peers.get('host');
    if (!peer?.nonce || peer.dc?.readyState !== 'open' || peer.dc.bufferedAmount > 4096) return;
    const buttons = state.focused && !state.editing && !state.localNeutralRequired ? merge([state.touch, state.native]) : zero();
    peer.dc.send(JSON.stringify({t: 'input', nonce: peer.nonce, seq: state.seq++, buttons})); state.lastSent = now();
  }
  function padMask(pads) {
    const sources = [];
    if (!Array.isArray(pads) || pads.length !== 4) return zero();
    for (const pad of pads) {
      if (!pad || !Array.isArray(pad.buttons) || pad.buttons.length !== 17 || !Array.isArray(pad.axes) || pad.axes.length !== 4) continue;
      const mask = zero(), pressed = i => Number.isFinite(pad.buttons[i]) && pad.buttons[i] > .5;
      // Standard browser buttons -> libretro joypad IDs. NES south = A/jump, east = B/run.
      for (const [button, action] of [[0,8],[1,0],[2,9],[3,1],[4,10],[5,11],[6,12],[7,13],[8,2],[9,3],[10,14],[11,15],[12,4],[13,5],[14,6],[15,7]]) mask[action] = pressed(button) ? 1 : 0;
      if (Number.isFinite(pad.axes[0])) { if (pad.axes[0] < -.45) mask[6] = 1; if (pad.axes[0] > .45) mask[7] = 1; }
      if (Number.isFinite(pad.axes[1])) { if (pad.axes[1] < -.45) mask[4] = 1; if (pad.axes[1] > .45) mask[5] = 1; }
      sources.push(mask);
    }
    return merge(sources);
  }
  function stop() {
    for (const id of [...state.peers.keys()]) removePeer(id);
    state.sources.clear(); apply(); detachCore();
    for (const node of state.audioNodes) try { node.disconnect(state.audio.analyser); } catch (_) {}
    try { state.audio?.analyser.disconnect(); } catch (_) {}
    for (const track of state.stream?.getTracks() || []) track.stop();
    state.viewportCapture?.close();state.viewportCapture=null;state.viewportDisabled=false;state.audioNodes.clear(); state.audio = null; state.stream = null; state.canvas = null;
    state.gameArtwork=null;window.boogieBackdrop?.clearViewport?.();window.boogieBackdrop?.clearGameArtwork?.();state.nativeMapping=false;state.lastMappingSetupAt=-Infinity;state.session = null; state.pending = new Map(); state.touch = zero(); state.native = zero(); state.ejs = zero();
    const video = document.getElementById('remoteVideo'); if (video) { video.pause(); video.srcObject = null; }
    document.getElementById('boogieEnableAudio')?.remove(); state.generation++;
  }
  window.boogieEvent = event => {
    if (!event || typeof event !== 'object') return;
    if (event.type === 'stop') { stop(); status(true); return; }
    if (event.type === 'session') {
      if (!validPeer(event.selfId) || typeof event.host !== 'boolean' || !validRole(event.role) || !validApprovedPort(event.role,event.port)) return;
      if (state.session?.selfId === event.selfId && state.session.host === event.host && state.session.role === event.role && state.session.port === (event.port??rolePort(event.role))) return;
      stop(); state.session = {selfId: event.selfId, host: event.host, role: event.role, port:event.port??rolePort(event.role), gameKey:gameIdentity(event.gameKey),hostLabel:typeof event.hostLabel === "string" ? event.hostLabel.slice(0,48) : "LAN host",gameTitle:typeof event.gameTitle === "string" ? event.gameTitle.slice(0,80) : "NES game"}; state.error = '';
      state.audioPeak = 0; state.audioSignalObserved = false; state.focused = true; status(true); return;
    }
    if (!state.session) return;
    if(event.type==='native-mapping'&&typeof event.active==='boolean'){
      if(!state.session.host)return reject();
      state.nativeMapping=event.active&&state.focused&&!document.hidden;
      if(state.nativeMapping){state.localNeutralRequired=true;clearLocal();}
      return;
    }
    if (event.type === 'focus' && typeof event.active === 'boolean') {
      if (!event.active) focusLost(); else focusGained();
      return;
    }
    if (event.type === 'peer-approved' && state.session.host && validPeer(event.peerId) && event.peerId !== state.session.selfId && validApprovedPort(event.role,event.port)) {
      if (state.peers.size + state.pending.size >= 4 && !state.peers.has(event.peerId) && !state.pending.has(event.peerId)) return reject();
      const port=event.port??rolePort(event.role);
      if(port>0&&([...state.peers.values()].some(p=>p.id!==event.peerId&&p.port===port)||[...state.pending].some(([id,p])=>id!==event.peerId&&p.port===port)))return reject();
      state.pending.set(event.peerId,{role:event.role,port}); return;
    }
    if (event.type === 'peer-left' && validPeer(event.peerId)) { state.pending.delete(event.peerId); removePeer(event.peerId); return; }
    if (event.type === 'signal') void remoteSignal(event);
  };
  window.boogieNativePads = pads => {
    state.native = padMask(pads);
    if (!state.editing && !state.native.some(Boolean)) state.localNeutralRequired = false;
    if (state.session?.host) {
      // Only this authority owns physical holds: discovery reaches EJS with neutral values,
      // preventing its independently configurable mapping from firing a second action.
      const discovery = Array.isArray(pads) && pads.length === 4 ? pads.map(pad =>
        pad && Array.isArray(pad.buttons) && pad.buttons.length === 17 && Array.isArray(pad.axes) && pad.axes.length === 4 ?
          {id: typeof pad.id === 'string' ? pad.id.slice(0, 128) : 'Boogie controller', buttons: Array(17).fill(0), axes: Array(4).fill(0)} : null) : [null, null, null, null];
      window.emulatormayoGamepads?.(discovery);
      setSource('native', state.focused&&!state.editing&&!state.localNeutralRequired ? state.native : zero());
    } else guestSnapshot(true);
  };
  window.boogieTouch = (action, down) => {
    if (state.editing) return;
    if (!Number.isInteger(action) || action < 0 || action > 15 || typeof down !== 'boolean') return;
    state.touch[action] = down ? 1 : 0;
    if (state.session?.host) setSource('touch', state.focused ? state.touch : zero()); else guestSnapshot(true);
  };
  window.boogieSetEditing = active => { if(typeof active !== 'boolean')return;state.localNeutralRequired=state.localNeutralRequired||state.native.some(Boolean);state.editing=active;state.touch=zero();if(state.session?.host){for(const key of [...state.sources.keys()])if(!key.startsWith('remote:'))state.sources.delete(key);apply();}guestSnapshot(true);};
  window.boogieCheckpoint = active => {if(typeof active!=='boolean')return;state.checkpoint=active;state.localNeutralRequired=true;state.sources.clear();state.touch=zero();state.native=zero();for(const peer of state.peers.values())peer.awaitNeutral=true;apply();};
  window.boogieRemote = Object.freeze({requestMappingSetup,publishGameArtwork});
  window.boogieDebug = debug;
  state.pending = new Map();
  const focusLost = () => {
    state.nativeMapping=false;state.focused = false;
    for(const peer of state.peers.values())peer.lastFrameAt=0;
    for (const peer of state.peers.values()) peer.awaitNeutral = true;
    for (const key of [...state.sources.keys()]) if (key.startsWith('remote:')) state.sources.delete(key);
    clearLocal();
  };
  window.addEventListener('blur',()=>{if(state.session?.host&&state.nativeMapping&&state.focused&&!document.hidden){state.localNeutralRequired=true;clearLocal();return;}focusLost();});
  const focusGained=()=>{state.focused=true;for(const peer of state.peers.values())peer.lastFrameAt=0;};
  document.addEventListener('visibilitychange', () => { if (document.hidden) focusLost(); else focusGained(); });
  window.addEventListener('focus', focusGained);
  window.addEventListener('pagehide', stop);
  setInterval(() => {
    if (!state.session) return;
    installCore();
    if (state.session.host) {
      for(const peer of state.peers.values())if(peer.qualityWidth!==state.canvas?.width)void applyQuality(peer);
      if (ensureMedia()) for (const [id, assignment] of state.pending) { state.pending.delete(id); makePeer(id, assignment.role, assignment.port); }
      for (const peer of state.peers.values()) if (state.sources.has('remote:' + peer.id) && now() - peer.lastInput > 500) {
        state.sources.delete('remote:' + peer.id); state.stale++; apply();
      }
      for (const peer of state.peers.values()) if (!peer.grantAcknowledged && peer.nonce && peer.dc?.readyState === 'open' && now() - (peer.lastGrantSent || 0) > 100) {
        peer.dc.send(JSON.stringify({t:'grant', nonce:peer.nonce, role:peer.role, port:peer.port,gameKey:state.session.gameKey,hostLabel:state.session.hostLabel,gameTitle:state.session.gameTitle})); peer.lastGrantSent = now();
      }
    } else {const artPeer=state.peers.get('host');if(artPeer)requestArtwork(artPeer);if(now() - state.lastSent >= 100)guestSnapshot(false);const peer=state.peers.get('host');if(peer&&peer.appliedQuality!==(window.boogieQualityPreference?.()||'smooth')&&now()-(peer.lastQualitySent||0)>2000)requestQuality();}
    status(false);
  }, 50);
})();
