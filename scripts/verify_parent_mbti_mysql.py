"""Run integration tests against a fresh, private MySQL instance (never the configured DB).

Usage: python scripts/verify_parent_mbti_mysql.py --mysqld PATH --artifacts DIRECTORY
The generated database is retained for diagnosis after shutdown. Credentials stay private.
"""
from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import pymysql
from redis import Redis
from redis.exceptions import RedisError


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysqld', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--tests', nargs='+', default=['tests/test_parent_mbti_mysql.py'], help='Test files run against this owned temporary database')
    parser.add_argument('--live-business', action='store_true', help='Disable media and use real isolated Redis plus normal mock-provider logins')
    parser.add_argument('--redis-wsl-distro', default='Ubuntu', help='WSL distribution with redis-server installed (business test only)')
    parser.add_argument('--serve-port', type=int, help='After successful business tests, serve this temporary data on localhost for UI verification')
    parser.add_argument('--serve-seconds', type=int, default=600, help='Stop the optional UI verification server after this many seconds')
    args = parser.parse_args()
    if args.serve_port and (not args.live_business or not 1 <= args.serve_port <= 65535 or args.serve_seconds <= 0):
        parser.error('--serve-port requires --live-business, a valid port and positive --serve-seconds')
    binary = args.mysqld.resolve(strict=True)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    owned = Path(tempfile.mkdtemp(prefix='parent-mbti-mysql-', dir=args.artifacts.resolve()))
    datadir = owned / 'data'
    port = free_port()
    password = secrets.token_hex(24)
    init_file = owned / 'init.sql'
    init_file.write_text("ALTER USER 'root'@'localhost' IDENTIFIED BY '" + password + "';\n"
                         "CREATE DATABASE parent_mbti_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n", encoding='utf-8')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    base = [str(binary), '--no-defaults', '--basedir=' + str(binary.parent.parent), '--datadir=' + str(datadir)]
    process = None
    connection = None
    redis_process = None
    redis_connection = None
    api_process = None
    redis_password = secrets.token_hex(24)
    redis_port = free_port()
    try:
        with (owned / 'initialize.log').open('wb') as log:
            subprocess.run(base + ['--initialize-insecure', '--console'], stdout=log, stderr=subprocess.STDOUT,
                           creationflags=flags, check=True, timeout=120)
        with (owned / 'server.log').open('wb') as log:
            process = subprocess.Popen(base + ['--console', '--bind-address=127.0.0.1', '--port=' + str(port),
                '--mysqlx=0', '--skip-log-bin', '--init-file=' + str(init_file)], stdout=log,
                stderr=subprocess.STDOUT, creationflags=flags)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Isolated MySQL exited; inspect server.log')
            try:
                connection = pymysql.connect(host='127.0.0.1', port=port, user='root', password=password,
                    database='parent_mbti_test', charset='utf8mb4', autocommit=True, connect_timeout=1,
                    cursorclass=pymysql.cursors.DictCursor)
                break
            except pymysql.MySQLError:
                time.sleep(0.25)
        if connection is None:
            raise RuntimeError('Isolated MySQL startup timed out')
        init_file.unlink()
        env = dict(os.environ, ENVIRONMENT='testing', AUTO_INIT_DB='false',
            DATABASE_URL=f'mysql+aiomysql://root:{password}@127.0.0.1:{port}/parent_mbti_test',
            REDIS_URL=f'redis://127.0.0.1:{free_port()}/0', SECRET_KEY=secrets.token_hex(32),
            RUN_PARENT_MYSQL='1', RUN_LIVE_MYSQL='1', PYTHONUTF8='1')
        if args.live_business:
            redis_config = owned / 'redis.conf'
            redis_config.write_text(f'bind 127.0.0.1\nport {redis_port}\nprotected-mode yes\n'
                f'requirepass {redis_password}\nsave ""\nappendonly no\ndaemonize no\n', encoding='utf-8')
            windows_path = str(redis_config.resolve())
            wsl_path = '/mnt/' + windows_path[0].lower() + windows_path[2:].replace('\\', '/')
            with (owned / 'redis.log').open('wb') as log:
                redis_process = subprocess.Popen(['wsl.exe', '-d', args.redis_wsl_distro, '--exec',
                    'redis-server', wsl_path], stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            redis_connection = Redis(host='127.0.0.1', port=redis_port, password=redis_password, socket_timeout=1)
            deadline = time.monotonic() + 30
            while True:
                if redis_process.poll() is not None:
                    raise RuntimeError('Isolated Redis exited; inspect redis.log')
                try:
                    redis_connection.ping()
                    break
                except RedisError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Isolated Redis startup timed out') from None
                    time.sleep(0.25)
            env.update(REDIS_URL=f'redis://:{redis_password}@127.0.0.1:{redis_port}/0',
                RUN_LIVE_BUSINESS='1', LIVE_MEDIA_MODE='disabled', SMS_PROVIDER='mock', WECHAT_PROVIDER='mock',
                LIVE_SDK_APP_ID='0', LIVE_SDK_SECRET='', LIVE_CLOUD_SECRET_ID='', LIVE_CLOUD_SECRET_KEY='',
                LIVE_CDN_PUSH_DOMAIN='', LIVE_CDN_PLAY_DOMAIN='', LIVE_CDN_PUSH_KEY='', LIVE_CDN_PLAY_KEY='',
                LIVE_TRIAL_ENABLED='false', LIVE_WECHAT_AV_VERIFIED='false', LIVE_DEVICE_PILOT_VERIFIED='false')
        # The only connection supplied to the schema bootstrap is this isolated instance.
        os.environ.update({key: env[key] for key in ['ENVIRONMENT', 'AUTO_INIT_DB', 'DATABASE_URL', 'REDIS_URL', 'SECRET_KEY']})
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from database_setup_marriage import DatabaseManager
        with connection.cursor() as cursor:
            DatabaseManager.__new__(DatabaseManager).init_all_tables(cursor)
        print('Isolated MySQL ready; running real HTTP, SQL and concurrency tests.', flush=True)
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--tb=short', '--show-capture=no', *args.tests],
            cwd=root, env=env, creationflags=flags, timeout=240, capture_output=True, text=True, encoding='utf-8')
        output = (result.stdout + result.stderr).replace(password, '[redacted]').replace(redis_password, '[redacted]')
        (owned / 'test-results.txt').write_text(output, encoding='utf-8')
        print(output)
        if result.returncode == 0 and args.serve_port:
            with (owned / 'api.log').open('wb') as log:
                api_process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                    '--host', '127.0.0.1', '--port', str(args.serve_port), '--lifespan', 'off'],
                    cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            print(f'UI verification: http://127.0.0.1:{args.serve_port}; synthetic accounts only; '
                  f'automatic shutdown in {args.serve_seconds}s. Diagnostics: {owned}', flush=True)
            try:
                api_process.wait(timeout=args.serve_seconds)
            except subprocess.TimeoutExpired:
                pass
            else:
                if api_process.returncode:
                    raise RuntimeError('Temporary API exited; inspect api.log (no existing service is stopped)')
        return result.returncode
    finally:
        if api_process and api_process.poll() is None:
            api_process.terminate()
            api_process.wait(timeout=10)
        if init_file.exists():
            init_file.unlink()
        if redis_connection:
            with contextlib.suppress(RedisError):
                redis_connection.shutdown(nosave=True)
            redis_connection.close()
        if redis_process:
            try:
                redis_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                redis_process.terminate()
        redis_config = owned / 'redis.conf'
        if redis_config.exists():
            redis_config.unlink()
        if connection:
            with contextlib.suppress(Exception), connection.cursor() as cursor:
                cursor.execute('SHUTDOWN')
            connection.close()
        if process and process.poll() is None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        print('Isolated instance stopped. Diagnostics: ' + str(owned), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
