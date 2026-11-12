"""Test-only HTTPS provider: fixed synthetic response, no external network."""
import http.server
import os
import ssl

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data=b'{"mock":"ok","offline":true}'
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self,*args):
        pass

server=http.server.ThreadingHTTPServer(("0.0.0.0",8443),Handler)
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/certs/provider.crt","/certs/provider.key")
server.socket=ctx.wrap_socket(server.socket,server_side=True)
server.serve_forever()
