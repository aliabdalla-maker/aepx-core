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
    def do_POST(self):
        length=int(self.headers.get("Content-Length","0"))
        if length>65536:
            self.send_error(413)
            return
        self._last_body=self.rfile.read(length)
        if self.path=="/v1/chat/completions":
            data=b'{"id":"chatcmpl-offline","object":"chat.completion","created":1,"model":"mock-model","choices":[{"index":0,"message":{"role":"assistant","content":"offline-openai-ok"},"finish_reason":"stop"}]}'
        elif self.path=="/v1/messages":
            data=b'{"id":"msg_offline","type":"message","role":"assistant","model":"mock-model","content":[{"type":"text","text":"offline-anthropic-ok"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":1,"output_tokens":1}}'
        elif self.path=="/mcp":
            import json
            try:
                request=json.loads(self._last_body)
            except (ValueError, UnicodeDecodeError):
                self.send_error(400)
                return
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or "id" not in request:
                self.send_error(400)
                return
            if request.get("method")=="tools/list":
                data=json.dumps({"jsonrpc":"2.0","id":request["id"],"result":{"tools":[{"name":"offline_echo","description":"Synthetic test tool","inputSchema":{"type":"object","properties":{"value":{"type":"string"}}}}]}}).encode()
            elif request.get("method")=="tools/call" and request.get("params",{}).get("name")=="offline_echo":
                value=request["params"].get("arguments",{}).get("value","")
                data=json.dumps({"jsonrpc":"2.0","id":request["id"],"result":{"content":[{"type":"text","text":"offline:"+value}],"isError":False}}).encode()
            else:
                self.send_error(400)
                return
        else:
            self.send_error(404)
            return
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
