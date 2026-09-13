import base64
import hashlib
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import unquote,urlsplit
from xml.etree.ElementTree import fromstring

from jailwatch.vms.onvif import (DEVICE,MEDIA,MEDIA2,SOAP,WSSE,WSU,OnvifClient,
                                envelope,parse_discovery,same_device_url,service_url)


class OnvifTests(unittest.TestCase):
    def test_ws_security_digest_matches_nonce_time_and_password(self):
        root,_=envelope(DEVICE,"GetServices","operator","private password")
        nonce=base64.b64decode(root.find(f".//{{{WSSE}}}Nonce").text)
        created=root.find(f".//{{{WSU}}}Created").text
        digest=root.find(f".//{{{WSSE}}}Password").text
        self.assertEqual(digest,base64.b64encode(hashlib.sha1(nonce+created.encode()+b"private password").digest()).decode())

    def test_advertised_other_host_cannot_receive_credentials(self):
        with self.assertRaisesRegex(ValueError,"another host"):
            same_device_url("http://192.0.2.2/onvif/media","http://192.0.2.1/onvif/device_service")
        self.assertEqual(same_device_url("rtsp://0.0.0.0:554/live","http://192.0.2.1/",("rtsp",)),"rtsp://192.0.2.1:554/live")
        with self.assertRaises(ValueError):
            service_url("file:///private")

    def test_discovery_matches_request_and_rejects_external_entities(self):
        xml=b'<Envelope><RelatesTo>uuid:test</RelatesTo><ProbeMatch><XAddrs>http://192.0.2.1/onvif/device_service</XAddrs><Scopes>onvif://www.onvif.org/name/North%20gate</Scopes></ProbeMatch></Envelope>'
        self.assertEqual(parse_discovery(xml,"uuid:test")[0]["name"],"North gate")
        self.assertEqual(parse_discovery(xml,"uuid:other"),[])
        with self.assertRaises(Exception):
            parse_discovery(b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><Envelope>&x;</Envelope>',"uuid:test")

    def test_media1_and_media2_roundtrip_against_local_soap_device(self):
        for namespace in (MEDIA,MEDIA2):
            calls=[]
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):
                    pass
                def do_POST(self):
                    body=self.rfile.read(int(self.headers["Content-Length"]))
                    document=fromstring(body)
                    action=list(document.find(f"{{{SOAP}}}Body"))[0]
                    name=action.tag.rsplit("}",1)[-1]; calls.append(name)
                    if name=="GetServices":
                        value=f'<Service><Namespace>{namespace}</Namespace><XAddr>http://127.0.0.1:{self.server.server_port}/media</XAddr></Service>'
                    elif name=="GetProfiles":
                        value='<Profiles token="channel1"><Name>North gate</Name><VideoEncoderConfiguration><Encoding>H264</Encoding><Resolution><Width>1920</Width><Height>1080</Height></Resolution></VideoEncoderConfiguration></Profiles>'
                    elif name=="GetStreamUri":
                        value='<MediaUri><Uri>rtsp://127.0.0.1:554/channel1</Uri></MediaUri>'
                        self.assert_token = action.find(f"{{{namespace}}}ProfileToken")
                        if self.assert_token is None or self.assert_token.text!="channel1":
                            self.send_error(400); return
                    else:
                        value=''
                    payload=f'<s:Envelope xmlns:s="{SOAP}"><s:Body>{value}</s:Body></s:Envelope>'.encode()
                    self.send_response(200); self.send_header("Content-Type","application/soap+xml")
                    self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
            server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            client=OnvifClient(f"http://127.0.0.1:{server.server_port}/onvif/device_service","operator","p@ss")
            try:
                profiles=client.profiles()
                self.assertEqual(profiles[0].name,"North gate")
                self.assertEqual(unquote(urlsplit(profiles[0].url).password),"p@ss")
                self.assertIn("GetStreamUri",calls)
            finally:
                client.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)
