# Browser guest

The broker serves this guest at its HTTPS root. It receives the Android host's picture/audio and sends approved controller inputs over WebRTC; it does not run an emulator, download a ROM, sign into RomM or expose host saves.

Enter a current invitation, display name and role, then wait for host approval. Choose shared Player 1, dedicated Player 2 or watch-only. Invitations may arrive as an `#invite=...` URL fragment; it is removed from the current URL/history and is not sent to the server as a request URL. The client does not store invitations or peer credentials in local/session storage. Leaving requires a new explicit join and approval.

Click or Tab to the video for keyboard play: arrows or W/A/S/D move, Z/J is A, X/K is B, Enter is Start, right Shift is Select. A focused game button supports holding Space or Enter. Input releases on focus loss, page hiding, disconnect and leaving; form controls suspend gameplay keys. Use **Enable audio** if the browser requires a user gesture.

**Controls** opens the physical-controller mapper. Press a controller button to expose it through the browser Gamepad API, choose the controller, then use Set, + Add (up to six bindings per action), Clear or Guided setup. Center sticks and release buttons between prompts. Saving supports this session, this game + controller model, or this controller model across games. Persisted profiles are browser-local and bounded; identical controller models share persistent profiles but can have distinct session overrides.

**Players** shows the current game, locally visible physical controllers and the host-approved virtual slot. It does not discover the host's physical inventory. Changing a local binding cannot change network role or port. To change slots, leave and request a new role with fresh approval. Opening the mapper suspends local gameplay and requires neutral input on return.

**Hide controls** retains a reachable Show controls button. Edit layout stores touch positions for this game or all games. Video quality, FPS display, compact icon toolbar and backdrop appearance are local preferences. Quality counters do not replace checking the actual picture and sound.

The exact asset allowlist and self-origin content policy are in `broker/broker.py`. There is no CORS relaxation, private config download, arbitrary file route or host credential route. See [LAN setup](../docs/setup.md) and [validation status](../docs/validation.md).
