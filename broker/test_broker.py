import argparse
import io
from email.message import Message
from types import SimpleNamespace
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from broker import APIError, MAX_BODY, MAX_CANDIDATE, MAX_SDP, Room, Handler, private_bind, write_configuration


class FakeClock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class BrokerTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.room = Room(self.clock, self.clock)
        self.host = self.room.host_key

    def join(self, role='player', name='Deck guest', ip='192.168.1.2'):
        return self.room.join({'invite': self.room.invite_key, 'displayName': name, 'role': role}, ip)

    def approved(self, role='player'):
        peer = self.join(role)
        self.room.approve(self.host, {'peerId': peer['peerId'], 'role': role})
        return peer

    def error(self, status, code, fn, *args):
        with self.assertRaises(APIError) as result:
            fn(*args)
        self.assertEqual((result.exception.status, result.exception.code), (status, code))

    def test_secrets_and_configuration(self):
        config = self.room.configuration('https://127.0.0.1:9443', 'abc')
        self.assertEqual(config['playerPort'], 1)
        self.assertEqual(len({self.host, self.room.invite_key, self.room.session_id}), 3)
        self.assertGreaterEqual(len(self.host), 40)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'private.json'
            write_configuration(file, config)
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(file.read_text()), config)
            with self.assertRaises(FileExistsError): write_configuration(file, config)
            link = Path(directory) / 'link'
            link.symlink_to(file)
            with self.assertRaises(FileExistsError): write_configuration(link, config)

    def test_pending_then_approval(self):
        p = self.join()
        events = self.room.events(self.host)['events']
        self.assertEqual(events[0]['type'], 'join_request')
        self.assertEqual(events[0]['requestedRole'], 'player')
        self.assertNotIn('peerCredential', str(events))
        self.error(403, 'approval_required', self.room.signal, p['peerCredential'],
                   {'target': 'host', 'type': 'offer', 'sdp': 'v=0'})
        grant = self.room.approve(self.host, {'peerId': p['peerId'], 'role': 'player'})
        self.assertEqual(grant['playerPort'], 1)
        self.assertEqual(self.room.events(p['peerCredential'])['events'][0]['type'], 'approved')

    def test_only_host_can_approve_stop_or_remove_others(self):
        p, q = self.join(), self.join()
        self.error(401, 'unauthorized', self.room.approve, p['peerCredential'], {'peerId': q['peerId'], 'role': 'player'})
        self.error(401, 'unauthorized', self.room.stop, p['peerCredential'], {})
        self.error(403, 'cannot_remove_other_peer', self.room.leave, p['peerCredential'], {'peerId': q['peerId']})

    def test_spectator_cannot_be_escalated(self):
        p = self.join('spectator')
        self.error(403, 'spectator_cannot_escalate', self.room.approve, self.host,
                   {'peerId': p['peerId'], 'role': 'player'})
        grant = self.room.approve(self.host, {'peerId': p['peerId'], 'role': 'spectator'})
        self.assertIsNone(grant['playerPort'])

    def test_player2_unique_authoritative_port_and_role_consent(self):
        shared = self.approved()
        self.assertEqual(self.room.approve(self.host, {'peerId': shared['peerId'], 'role': 'player'})['port'], 0)
        self.error(403, 'requested_role_mismatch', self.room.approve, self.host, {'peerId': shared['peerId'], 'role': 'player2'})
        one, two = self.join('player2'), self.join('player2')
        grant = self.room.approve(self.host, {'peerId': one['peerId'], 'role': 'player2'})
        self.assertEqual((grant['port'], grant['playerPort'], grant['mode']), (1, 2, 'two-player'))
        self.error(409, 'player_slot_occupied', self.room.approve, self.host, {'peerId': two['peerId'], 'role': 'player2'})
        self.assertEqual(self.room.peers[two['peerId']].role, 'pending')
        self.room.signal(one['peerCredential'], {'target': 'host', 'type': 'offer', 'sdp': 'v=0'})
        self.room.approve(self.host, {'peerId': one['peerId'], 'role': 'spectator'})
        self.assertEqual(self.room.approve(self.host, {'peerId': two['peerId'], 'role': 'player2'})['port'], 1)
        self.room.leave(self.host, {'peerId': two['peerId']})
        three = self.join('player2')
        self.assertEqual(self.room.approve(self.host, {'peerId': three['peerId'], 'role': 'player2'})['port'], 1)

    def test_player2_idle_release_and_client_port_rejected(self):
        one = self.approved('player2')
        self.clock.advance(31)
        two = self.join('player2')
        self.assertNotIn(one['peerId'], self.room.peers)
        self.assertEqual(self.room.approve(self.host, {'peerId': two['peerId'], 'role': 'player2'})['port'], 1)
        self.error(400, 'invalid_fields', self.room.join,
                   {'invite': self.room.invite_key, 'displayName': 'guest', 'role': 'player2', 'port': 0}, '192.168.1.5')
        observer = self.join('spectator')
        self.error(403, 'spectator_cannot_escalate', self.room.approve, self.host,
                   {'peerId': observer['peerId'], 'role': 'player2'})

    def test_host_star_bidirectional_signals(self):
        p, q = self.approved(), self.approved('spectator')
        offer = {'target': p['peerId'], 'type': 'offer', 'sdp': 'v=0\r\ns=host'}
        self.room.signal(self.host, offer)
        events = self.room.events(p['peerCredential'])['events']
        self.assertEqual(events[-1]['from'], 'host')
        self.assertEqual(events[-1]['signal']['sdp'], offer['sdp'])
        self.room.signal(p['peerCredential'], {'target': 'host', 'type': 'answer', 'sdp': 'v=0'})
        self.assertEqual(self.room.events(self.host)['events'][-1]['from'], p['peerId'])
        self.error(403, 'host_star_only', self.room.signal, p['peerCredential'],
                   {'target': q['peerId'], 'type': 'offer', 'sdp': 'v=0'})
        self.error(404, 'peer_not_found', self.room.signal, self.host,
                   {'target': 'missing', 'type': 'offer', 'sdp': 'v=0'})

    def test_ice_and_payload_bounds(self):
        p = self.approved()
        packet = {'target': 'host', 'type': 'candidate', 'candidate': {'candidate': 'candidate:abc', 'sdpMid': '0', 'sdpMLineIndex': 0}}
        self.room.signal(p['peerCredential'], packet)
        self.assertEqual(self.room.events(self.host)['events'][-1]['signal']['candidate'], packet['candidate'])
        packet['candidate']['candidate'] = 'x' * MAX_CANDIDATE
        self.error(413, 'candidate_too_large', self.room.signal, p['peerCredential'], packet)
        self.error(413, 'sdp_too_large', self.room.signal, p['peerCredential'],
                   {'target': 'host', 'type': 'offer', 'sdp': 'x' * (MAX_SDP + 1)})
        self.error(400, 'invalid_fields', self.room.signal, p['peerCredential'],
                   {'target': 'host', 'type': 'offer', 'sdp': 'v=0', 'rom': 'nope'})

    def test_leave_and_revoke_invalidate_credential(self):
        for host_remove in (False, True):
            p = self.approved()
            self.room.leave(self.host if host_remove else p['peerCredential'], {'peerId': p['peerId']} if host_remove else {})
            self.error(401, 'unauthorized', self.room.events, p['peerCredential'])
            self.assertEqual(self.room.events(self.host)['events'][-1]['type'], 'peer_left')

    def test_host_reset_keeps_pairing_but_revokes_all_peers(self):
        pending = self.join()
        p2 = self.approved('player2')
        spectator = self.approved('spectator')
        old_sequence = self.room.sequence
        invite, host, room_id = self.room.invite_key, self.host, self.room.session_id
        self.error(401, 'unauthorized', self.room.reset, p2['peerCredential'], {})
        self.error(400, 'invalid_fields', self.room.reset, host, {'peerId': p2['peerId']})
        self.clock.advance(601)
        result = self.room.reset(host, {})
        self.assertTrue(result['reset'])
        self.assertEqual((self.room.host_key, self.room.invite_key, self.room.session_id), (host, invite, room_id))
        self.assertFalse(self.room.stopped)
        self.assertEqual(self.room.host_events, __import__('collections').deque())
        self.assertGreaterEqual(self.room.sequence, old_sequence)
        for peer in (pending, p2, spectator):
            self.error(401, 'unauthorized', self.room.events, peer['peerCredential'])
        fresh = self.join('player2')
        events = self.room.events(host, old_sequence)['events']
        self.assertTrue(events)
        self.assertTrue(all(e['id'] > old_sequence for e in events))
        self.assertEqual(self.room.approve(host, {'peerId': fresh['peerId'], 'role': 'player2'})['port'], 1)

    def test_reset_cannot_revive_a_stopped_room(self):
        self.room.stop(self.host, {})
        self.error(410, 'session_stopped', self.room.reset, self.host, {})

    def test_stop_revokes_everyone(self):
        p = self.approved()
        invite = self.room.invite_key
        self.room.stop(self.host, {})
        self.error(410, 'session_stopped', self.room.events, p['peerCredential'])
        self.error(410, 'session_stopped', self.room.events, self.host)
        self.error(410, 'session_stopped', self.room.join, {'invite': invite, 'displayName': 'Late', 'role': 'player'}, '192.168.1.3')
        self.assertEqual(self.room.peers, {})

    def test_invite_and_idle_expiry(self):
        p = self.join()
        self.clock.advance(29)
        self.room.events(p['peerCredential'])  # heartbeat refresh
        self.clock.advance(29)
        self.room.events(self.host)
        self.assertIn(p['peerId'], self.room.peers)
        self.clock.advance(2)
        self.error(401, 'unauthorized', self.room.events, p['peerCredential'])
        self.assertEqual(self.room.events(self.host)['events'][-1]['reason'], 'idle_timeout')
        self.clock.advance(600)
        self.error(403, 'invitation_expired', self.join)

    def test_join_credentials_and_name_validation(self):
        self.error(403, 'invalid_invitation', self.room.join,
                   {'invite': 'wrong', 'displayName': 'Guest', 'role': 'player'}, '192.168.1.2')
        self.error(403, 'invalid_invitation', self.room.join,
                   {'invite': '💥', 'displayName': 'Guest', 'role': 'player'}, '192.168.1.2')
        self.error(401, 'unauthorized', self.room.events, '💥')
        self.error(400, 'invalid_display_name', self.join, 'player', 'Guest\nadmin')
        self.error(400, 'invalid_role', self.join, 'admin')

    def test_rate_caps_room_size_and_candidate_count(self):
        p = self.approved()
        for _ in range(239):
            self.room.signal(p['peerCredential'], {'target': 'host', 'type': 'answer', 'sdp': 'v=0'})
        self.room.signal(p['peerCredential'], {'target': 'host', 'type': 'answer', 'sdp': 'v=0'})
        self.error(429, 'rate_limited', self.room.signal, p['peerCredential'], {'target': 'host', 'type': 'answer', 'sdp': 'v=0'})
        self.room.peers[p['peerId']].candidates = 256
        self.clock.advance(61)
        # Expiry is intentional: cannot send using an abandoned credential.
        self.error(401, 'unauthorized', self.room.signal, p['peerCredential'], {'target': 'host', 'type': 'candidate', 'candidate': {'candidate': ''}})
        for _ in range(8): self.join()
        self.error(409, 'room_full', self.join)

    def test_event_ack_and_long_poll_notification(self):
        self.join()
        first = self.room.events(self.host)
        self.assertEqual(len(first['events']), 1)
        self.assertEqual(self.room.events(self.host, first['cursor'])['events'], [])
        done = []
        thread = threading.Thread(target=lambda: done.append(self.room.events(self.host, first['cursor'], 0.5)))
        thread.start()
        time.sleep(0.02)
        self.join()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(done[0]['events'][0]['type'], 'join_request')
        self.error(400, 'invalid_cursor', self.room.events, self.host, 0, 6)
        self.error(400, 'invalid_cursor', self.room.events, self.host, 0, float('nan'))

    def test_bind_addresses_are_explicit_private_ipv4(self):
        for address in ['127.0.0.1', '192.168.50.25', '10.0.0.2', '172.16.0.1']:
            self.assertEqual(private_bind(address), address)
        for address in ['0.0.0.0', '8.8.8.8', 'localhost', '::', '169.254.1.2', '224.0.0.1']:
            with self.assertRaises(argparse.ArgumentTypeError): private_bind(address)


class RequestParsingTest(unittest.TestCase):
    def handler(self, payload=b'{}', content_type='application/json', length=None):
        handler = Handler.__new__(Handler)
        handler.headers = Message()
        handler.headers['Content-Type'] = content_type
        handler.headers['Content-Length'] = str(len(payload) if length is None else length)
        handler.rfile = io.BytesIO(payload)
        return handler

    def check_error(self, handler, code):
        with self.assertRaises(APIError) as result: handler._body()
        self.assertEqual(result.exception.code, code)

    def test_json_and_duplicate_fields(self):
        self.assertEqual(self.handler(b'{"role":"player"}')._body(), {'role': 'player'})
        self.check_error(self.handler(b'{"role":"player","role":"spectator"}'), 'invalid_json')
        self.check_error(self.handler(b'{"nested":{"x":1,"x":2}}'), 'invalid_json')
        self.check_error(self.handler(b'{"bad":NaN}'), 'invalid_json')
        self.check_error(self.handler(b'\xff'), 'invalid_json')

    def test_bounded_and_complete_body(self):
        self.check_error(self.handler(b'{}', length=MAX_BODY + 1), 'body_too_large')
        self.check_error(self.handler(b'{}', length='9' * 100), 'body_too_large')
        self.check_error(self.handler(b'{}', length=4), 'incomplete_body')
        self.check_error(self.handler(b'{}', content_type='text/plain'), 'json_required')
        handler = self.handler()
        handler.headers['Content-Length'] = '2'
        self.check_error(handler, 'content_length_required')
        handler = self.handler()
        handler.headers['Transfer-Encoding'] = 'chunked'
        self.check_error(handler, 'transfer_encoding_not_supported')

    def test_authorization_requires_one_bearer_header(self):
        handler = self.handler()
        with self.assertRaises(APIError): handler._credential()
        handler.headers['Authorization'] = 'Bearer abc'
        self.assertEqual(handler._credential(), 'abc')
        handler.headers['Authorization'] = 'Bearer def'
        with self.assertRaises(APIError): handler._credential()

    def test_wire_dispatch_no_socket(self):
        room = Room()
        body = json.dumps({'invite': room.invite_key, 'displayName': 'Guest', 'role': 'player'}).encode()
        handler = self.handler(body)
        handler.server = SimpleNamespace(room=room)
        handler.client_address = ('192.168.1.2', 1234)
        handler.command, handler.path = 'POST', '/join'
        peer = handler._dispatch()
        self.assertEqual(peer['status'], 'pending')
        handler.command, handler.path = 'GET', '/events?after=0&wait=0'
        handler.headers['Authorization'] = 'Bearer ' + room.host_key
        result = handler._dispatch()
        self.assertEqual(result['events'][0]['type'], 'join_request')
        handler.path = '/events?wait=6'
        with self.assertRaises(APIError) as error: handler._dispatch()
        self.assertEqual(error.exception.code, 'invalid_cursor')
        handler.path = '/events?wait=0&wait=1'
        with self.assertRaises(APIError): handler._dispatch()


if __name__ == '__main__': unittest.main()
