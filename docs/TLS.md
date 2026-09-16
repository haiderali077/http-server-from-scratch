# HTTPS frontend

Use `--tls-cert /path/to/cert.pem --tls-key /path/to/key.pem --port 8443`. Supply both files. The server uses Python's SSLContext, requires TLS 1.2 or later, advertises only HTTP/1.1 through ALPN, and performs handshakes in bounded workers with `--tls-handshake-timeout` (default 3 seconds). A TLS overload closes before handshake; it does not send plaintext HTTP on the encrypted port.

For a local demo, generate a temporary self-signed certificate:

```sh
mkdir -p /tmp/http-server-tls
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost \
  -addext subjectAltName=DNS:localhost \
  -keyout /tmp/http-server-tls/key.pem -out /tmp/http-server-tls/cert.pem
python3 -m src.webserver --port 8443 \
  --tls-cert /tmp/http-server-tls/cert.pem --tls-key /tmp/http-server-tls/key.pem
curl --cacert /tmp/http-server-tls/cert.pem https://localhost:8443/health
```

The client verifies the generated certificate explicitly; disabling certificate verification is unnecessary. Tests generate temporary certificates with the OpenSSL CLI and check verified HTTPS, ALPN, persistence, proxy scheme metadata, untrusted-certificate rejection, and stalled handshakes. No certificate or key is stored in Git; PEM/key files are ignored.

This is frontend TLS termination. Backend connections remain configured HTTP; backend TLS, certificate rotation, SNI virtual hosts, and mutual TLS are not implemented. Selector mode rejects TLS because TLS readiness and pending decrypted bytes require additional states. See [Python's SSL documentation](https://docs.python.org/3/library/ssl.html).
