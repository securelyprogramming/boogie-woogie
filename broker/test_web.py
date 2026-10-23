"""Browser route checks without sockets or private configuration contents."""
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import broker
class PublicTests(unittest.TestCase):
 def handler(self,path,method='GET'):
  h=object.__new__(broker.Handler);h.path=path;h.command=method;h.wfile=io.BytesIO();h.out={}
  h.send_response=lambda v:setattr(h,'status',v)
  h.send_header=lambda k,v:h.out.__setitem__(k,v);h.end_headers=lambda:None
  return h
 def test_client_info_is_public_capability_only(self):
  for method in ['GET','HEAD']:
   h=self.handler('/client-info',method);self.assertTrue(h._public());self.assertEqual(h.status,200)
   self.assertEqual(h.out['Cache-Control'],'no-store');self.assertEqual(h.out['Referrer-Policy'],'no-referrer')
   if method=='GET':
    v=json.loads(h.wfile.getvalue());self.assertEqual(v['protocolVersion'],1);self.assertEqual(v['ports'],{'player':0,'player2':1,'spectator':None})
    self.assertEqual(set(v),{'protocolVersion','roles','ports','webGuest'})
   else:self.assertEqual(h.wfile.getvalue(),b'')
 def test_unknown_get_head_paths_have_no_public_mapping(self):
  for path in ['/private/session.json','/config.json','/broker.py','/../private/session.json','/%2e%2e/private/session.json','/web/guest.js?token=bad','/client-info?invite=bad','/assets/player.js','/assets/native-gamepad.js','/assets/../private/session.json']:
   for method in ['GET','HEAD']:
    h=self.handler(path,method);self.assertFalse(h._public());self.assertEqual(h.wfile.getvalue(),b'')
 def test_controller_mapper_assets_are_exact_and_have_self_only_csp(self):
  for name in ['controller-mapper-model.js','controller-mapper.js','controller-mapper.css']:
   path='/web/'+name
   self.assertIn(path,broker.PUBLIC_ASSETS)
   h=self.handler(path);self.assertTrue(h._public());self.assertEqual(h.status,200)
   self.assertGreater(len(h.wfile.getvalue()),100)
   self.assertIn("connect-src 'self'",h.out['Content-Security-Policy'])
   for bad in [path+'?credential=bad',path+'/extra']:
    self.assertFalse(self.handler(bad)._public())
 def test_explicit_asset_types_csp_and_symlink_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'guest.js';path.write_bytes(b'fixture only')
   with patch.object(broker,'PUBLIC_ASSETS',{'/web/guest.js':(path,'application/javascript; charset=utf-8')}):
    h=self.handler('/web/guest.js');self.assertTrue(h._public());self.assertEqual(h.wfile.getvalue(),b'fixture only');self.assertIn("script-src 'self'",h.out['Content-Security-Policy']);self.assertNotIn('Access-Control-Allow-Origin',h.out)
    h=self.handler('/web/guest.js','HEAD');h._public();self.assertEqual(h.wfile.getvalue(),b'')
    private=Path(d)/'private';private.write_bytes(b'never served');path.unlink();path.symlink_to(private)
    with self.assertRaises(broker.APIError):self.handler('/web/guest.js')._public()
if __name__=='__main__':unittest.main()
