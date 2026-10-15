import os
from waitress import serve
from ft.wsgi import application

if __name__ == '__main__':
    host=os.environ.get('FT_HOST','127.0.0.1')
    port=int(os.environ.get('FT_PORT','4180'))
    print(f'FT platform: http://{host}:{port}',flush=True)
    proxy_options = {}
    if os.environ.get('FT_TRUST_PROXY') == '1':
        # Only use behind an isolated proxy that overwrites this header.
        proxy_options = {'trusted_proxy': os.environ.get('FT_PROXY_IP', '127.0.0.1'),
                         'trusted_proxy_headers': {'x-forwarded-proto'}}
    serve(application,host=host,port=port,threads=8,
          max_request_body_size=310*1024*1024, **proxy_options)
