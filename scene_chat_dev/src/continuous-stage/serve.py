"""仅服务独立原型与指定角色图片；从任意目录运行本文件。"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PEOPLE = {'沈知韫', '苏婉青', '徐念薇'}
FILES = {'index.html', 'stage.css', 'stage.js', 'compare.html', 'compare.css', 'compare.js'}

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        parts = path.strip('/').split('/')
        if path == '/':
            target = HERE / 'compare.html'
        elif len(parts) == 1 and parts[0] in FILES:
            target = HERE / parts[0]
        elif len(parts) == 3 and parts[0] == 'assets' and parts[1] in PEOPLE and parts[2] in {'fullbody.png', 'fullbody2.png', 'into.png'}:
            target = ROOT / 'txt文件' / 'image' / parts[1] / parts[2]
        else:
            self.send_error(404)
            return
        if not target.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', self.guess_type(str(target)))
        self.send_header('Content-Length', str(target.stat().st_size))
        self.send_header('Cache-Control', 'private, max-age=3600' if parts[0] == 'assets' else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            with target.open('rb') as stream:
                self.copyfile(stream, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self):
        self.send_error(405)

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    print('独立叙事原型：http://127.0.0.1:8766', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8766), Handler).serve_forever()
