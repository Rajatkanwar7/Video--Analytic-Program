"""A bounded ONVIF discovery/Media1/Media2 client; not an ONVIF conformance claim."""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring

SOAP = "http://www.w3.org/2003/05/soap-envelope"
DEVICE = "http://www.onvif.org/ver10/device/wsdl"
MEDIA = "http://www.onvif.org/ver10/media/wsdl"
MEDIA2 = "http://www.onvif.org/ver20/media/wsdl"
SCHEMA = "http://www.onvif.org/ver10/schema"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
TOKEN = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0"


def child(element, namespace, name, text=None):
    node = SubElement(element,f"{{{namespace}}}{name}")
    node.text = text
    return node


def text_at(element, name, default=""):
    found = element.find(f".//{{*}}{name}")
    return found.text or default if found is not None else default


def service_url(value):
    value = value.strip()
    if "://" not in value:
        value = "http://"+value.rstrip("/")+"/onvif/device_service"
    parsed = urlsplit(value)
    if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.fragment:
        raise ValueError("Enter the ONVIF device address, for example http://192.168.1.10/onvif/device_service.")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Invalid ONVIF port.")
    if parsed.path in ("", "/"):
        value = urlunsplit((parsed.scheme,parsed.netloc,"/onvif/device_service",parsed.query,""))
    return value


def same_device_url(value, base, schemes=("http","https")):
    p,b = urlsplit(value),urlsplit(base)
    if p.scheme not in schemes or p.username or p.fragment or not p.hostname:
        raise ValueError("The device returned an unsupported service address.")
    if p.hostname in ("0.0.0.0","::"):
        host = f"[{b.hostname}]" if ":" in b.hostname else b.hostname
        value = urlunsplit((p.scheme,host+(f":{p.port}" if p.port else ""),p.path,p.query,""))
        p = urlsplit(value)
    if p.hostname.casefold() != b.hostname.casefold():
        raise ValueError("The device advertised another host. Verify that stream address and add it manually.")
    if b.scheme == "https" and p.scheme == "http":
        raise ValueError("The device advertised an unencrypted service from an HTTPS connection.")
    return value


def envelope(namespace, action, username="", password="", offset=0):
    root = Element(f"{{{SOAP}}}Envelope")
    if username:
        header = child(root,SOAP,"Header")
        security = child(header,WSSE,"Security")
        security.set(f"{{{SOAP}}}mustUnderstand","1")
        token = child(security,WSSE,"UsernameToken")
        child(token,WSSE,"Username",username)
        nonce = os.urandom(20)
        created = (datetime.now(timezone.utc)+timedelta(seconds=offset)).isoformat(timespec="seconds").replace("+00:00","Z")
        digest = base64.b64encode(hashlib.sha1(nonce+created.encode()+password.encode()).digest()).decode()
        node = child(token,WSSE,"Password",digest); node.set("Type",TOKEN+"#PasswordDigest")
        node = child(token,WSSE,"Nonce",base64.b64encode(nonce).decode())
        node.set("EncodingType","http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary")
        child(token,WSU,"Created",created)
    return root, child(child(root,SOAP,"Body"),namespace,action)


@dataclass
class StreamProfile:
    name: str
    token: str
    url: str
    encoding: str = ""
    resolution: str = ""
    media_namespace: str = MEDIA
    media_endpoint: str = ""
    clock_offset: float = 0


class OnvifClient:
    def __init__(self, endpoint, username, password, session=None):
        import requests
        self.endpoint = service_url(endpoint)
        self.username,self.password = username,password
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.offset = 0

    def close(self):
        self.session.close()

    def call(self, endpoint, namespace, action, populate=None, authenticated=True):
        import requests
        from requests.auth import HTTPDigestAuth
        endpoint = same_device_url(endpoint,self.endpoint)
        root,body = envelope(namespace,action,self.username if authenticated else "",self.password,self.offset)
        if populate:
            populate(body)
        response = None
        try:
            response = self.session.post(endpoint,data=tostring(root,encoding="utf-8",xml_declaration=True),
                headers={"Content-Type":f'application/soap+xml; charset=utf-8; action="{namespace}/{action}"'},
                auth=HTTPDigestAuth(self.username,self.password) if authenticated and self.username else None,
                timeout=(4,8),allow_redirects=False,stream=True)
            if response.status_code in (401,403):
                raise ValueError("ONVIF login rejected. Check the ONVIF account, permissions and camera clock.")
            if not 200 <= response.status_code < 300:
                raise ValueError(f"ONVIF {action} was not accepted (HTTP {response.status_code}).")
            payload = bytearray()
            deadline = time.monotonic()+20
            for part in response.iter_content(16384):
                payload.extend(part)
                if len(payload) > 2*1024*1024 or time.monotonic()>deadline:
                    raise ValueError("ONVIF response exceeded the supported size.")
            document = fromstring(bytes(payload))
            if document.find(f".//{{{SOAP}}}Fault") is not None:
                raise ValueError(f"The camera rejected ONVIF {action}. Check ONVIF support and account permissions.")
            return document
        except requests.RequestException:
            raise ValueError("ONVIF connection failed. Check the IP, ONVIF port and HTTPS certificate.") from None
        finally:
            if response is not None:
                response.close()

    def stream_uri(self, profile):
        ns = profile.media_namespace
        self.offset = profile.clock_offset
        def populate(body):
            if ns == MEDIA:
                setup = child(body,ns,"StreamSetup")
                child(setup,SCHEMA,"Stream","RTP-Unicast")
                child(child(setup,SCHEMA,"Transport"),SCHEMA,"Protocol","RTSP")
                child(body,ns,"ProfileToken",profile.token)
            else:
                child(body,ns,"Protocol","RTSP")
                child(body,ns,"ProfileToken",profile.token)
        uri = text_at(self.call(profile.media_endpoint,ns,"GetStreamUri",populate),"Uri")
        uri = same_device_url(uri,self.endpoint,schemes=("rtsp","rtsps"))
        p = urlsplit(uri)
        login = f"{quote(self.username,safe='')}:{quote(self.password,safe='')}@" if self.username else ""
        return urlunsplit((p.scheme,login+p.netloc,p.path,p.query,""))

    def profiles(self, resolve=True):
        try:
            clock = self.call(self.endpoint,DEVICE,"GetSystemDateAndTime",authenticated=False)
            utc = clock.find(".//{*}UTCDateTime")
            if utc is not None:
                values = [int(text_at(utc,n)) for n in ("Year","Month","Day","Hour","Minute","Second")]
                self.offset = (datetime(*values,tzinfo=timezone.utc)-datetime.now(timezone.utc)).total_seconds()
        except (ValueError,TypeError):
            pass
        endpoints = {}
        try:
            services = self.call(self.endpoint,DEVICE,"GetServices",lambda b: child(b,DEVICE,"IncludeCapability","false"))
            for node in services.findall(".//{*}Service"):
                ns = text_at(node,"Namespace")
                if ns in (MEDIA,MEDIA2):
                    endpoints[ns] = same_device_url(text_at(node,"XAddr"),self.endpoint)
        except ValueError:
            pass
        if not endpoints:
            caps = self.call(self.endpoint,DEVICE,"GetCapabilities",lambda b: child(b,DEVICE,"Category","Media"))
            media = caps.find(".//{*}Media")
            if media is not None:
                endpoints[MEDIA] = same_device_url(text_at(media,"XAddr"),self.endpoint)
        results, errors = [],[]
        for ns in (MEDIA2,MEDIA):
            if ns not in endpoints:
                continue
            endpoint = endpoints[ns]
            try:
                document = self.call(endpoint,ns,"GetProfiles")
                for profile in document.findall(".//{*}Profiles")[:128]:
                    token = profile.get("token", "")
                    if not token:
                        continue
                    width,height = text_at(profile,"Width"),text_at(profile,"Height")
                    item = StreamProfile(text_at(profile,"Name",token),token,"",text_at(profile,"Encoding"),
                                         f"{width} × {height}" if width and height else "",ns,endpoint,self.offset)
                    if resolve:
                        item.url = self.stream_uri(item)
                    results.append(item)
                if results:
                    break
            except ValueError as exc:
                errors.append(str(exc))
        if not results:
            raise ValueError(errors[-1] if errors else "No supported RTSP profiles found. Add the device's RTSP URL manually.")
        return results


def parse_discovery(payload, message_id):
    root = fromstring(payload)
    related = text_at(root,"RelatesTo")
    if related and related != message_id:
        return []
    results = []
    for match in root.findall(".//{*}ProbeMatch"):
        for address in text_at(match,"XAddrs").split():
            try:
                endpoint = service_url(address)
            except ValueError:
                continue
            name = next((unquote(s.rsplit("/",1)[-1]) for s in text_at(match,"Scopes").split()
                         if "/name/" in s),urlsplit(endpoint).hostname)
            results.append({"name":name,"endpoint":endpoint})
    return results


def discover(interface="", seconds=3):
    if not .1 <= seconds <= 10:
        raise ValueError("Discovery duration must be between 0.1 and 10 seconds.")
    message_id = "uuid:"+str(uuid.uuid4())
    request = f'''<s:Envelope xmlns:s="{SOAP}" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><s:Header><a:MessageID>{message_id}</a:MessageID><a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To><a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action></s:Header><s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body></s:Envelope>'''
    found = {}
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP) as connection:
        connection.bind((interface,0))
        connection.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,1)
        if interface:
            connection.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton(interface))
        connection.sendto(request.encode(),("239.255.255.250",3702))
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline and len(found) < 100:
            connection.settimeout(max(.01,deadline-time.monotonic()))
            try:
                payload,_ = connection.recvfrom(65536)
                for device in parse_discovery(payload,message_id):
                    found[device["endpoint"]] = device
            except socket.timeout:
                break
            except Exception as exc:
                if isinstance(exc,OSError):
                    raise
                # Ignore malformed unauthenticated discovery packets.
                continue
    return list(found.values())
