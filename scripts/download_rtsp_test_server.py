"""Fetch a checksum-pinned test server; never included in the VMS distribution."""
import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION="v1.21.0"
DIGESTS={"windows_amd64.zip":"8a58a9b8c25ee99a96c23dc0a17f39ace3072c01d2e148329073c64ddf83493d",
         "linux_amd64.tar.gz":"e02e34c3337a35f20ac9e5aa31524566108964e6e37dbc46cf8292169f6c792b"}


def main():
    platform="windows_amd64.zip" if sys.platform=="win32" else "linux_amd64.tar.gz"
    url=f"https://github.com/bluenviron/mediamtx/releases/download/{VERSION}/mediamtx_{VERSION}_{platform}"
    with urllib.request.urlopen(url,timeout=60) as response:
        payload=response.read(80*1024*1024)
    if hashlib.sha256(payload).hexdigest()!=DIGESTS[platform]:
        raise ValueError("Test-server download checksum mismatch.")
    name="mediamtx.exe" if sys.platform=="win32" else "mediamtx"
    destination=Path("build_assets")/name; destination.parent.mkdir(exist_ok=True)
    if sys.platform=="win32":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            destination.write_bytes(archive.read(name))
    else:
        with tarfile.open(fileobj=io.BytesIO(payload),mode="r:gz") as archive:
            with archive.extractfile(name) as source:
                destination.write_bytes(source.read())
        os.chmod(destination,0o755)
    print(json.dumps({"executable":str(destination.resolve()),"version":VERSION}))


if __name__=="__main__":
    main()
