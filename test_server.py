#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ローカルテスト用CGIサーバー（本番環境では不要）
python test_server.py で起動し、http://localhost:8080/ にアクセス
"""
import http.server
import os
import sys

PORT = 8080
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class CGIHandler(http.server.CGIHTTPRequestHandler):
    cgi_directories = ["/"]

    def is_cgi(self):
        script_path = self.path.split("?")[0]
        if script_path.endswith(".py"):
            self.cgi_info = ("", self.path[1:])
            return True
        return False

if __name__ == "__main__":
    server = http.server.HTTPServer(("", PORT), CGIHandler)
    print("Test server running at http://localhost:{}".format(PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
