import json

import mock
import tornado.concurrent
import tornado.testing

from hacheck import main
from hacheck import spool
from hacheck import cache
from hacheck import handlers


class ApplicationTestCase(tornado.testing.AsyncHTTPTestCase):
    def setUp(self):
        # flush the cache before every test
        cache.configure()
        super(ApplicationTestCase, self).setUp()

    def get_app(self):
        return main.get_app()

    def test_status(self):
        response = self.fetch('/status')
        self.assertEqual('application/json; charset=UTF-8', response.headers['Content-Type'])
        result = json.loads(response.body)
        self.assertGreater(result['uptime'], 0.0)

    def test_routing(self):
        with mock.patch.object(handlers.HTTPServiceHandler, 'get') as m:
            self.fetch('/http/foo/1/status')
            m.assert_called_once_with('foo', '1', 'status')
        with mock.patch.object(handlers.TCPServiceHandler, 'get') as m:
            self.fetch('/tcp/bar/2')
            m.assert_called_once_with('bar', '2', '')

    def test_spool_checker(self):
        with mock.patch.object(spool, 'is_up', return_value=(True, {"reason": "YES"})):
            response = self.fetch('/spool/foo/1/status')
            self.assertEqual(response.code, 200)
            self.assertEqual(response.body, "YES")
        with mock.patch.object(spool, 'is_up', return_value=(False, {"service": "any", "reason": ""})):
            response = self.fetch('/spool/foo/1/status')
            self.assertEqual(response.code, 503)
            self.assertEqual(response.body, "Service any in down state: ")

    def test_calls_all_checkers(self):
        rv1 = tornado.concurrent.Future()
        rv1.set_result((200, 'OK1'))
        rv2 = tornado.concurrent.Future()
        rv2.set_result((200, 'OK2'))
        checker1 = mock.Mock(return_value=rv1)
        checker2 = mock.Mock(return_value=rv2)
        with mock.patch.object(handlers.SpoolServiceHandler, 'CHECKERS', [checker1, checker2]):
            response = self.fetch('/spool/foo/1/status')
            self.assertEqual(200, response.code)
            self.assertEqual('OK2', response.body)
            checker1.assert_called_once_with('foo', 1, 'status', io_loop=mock.ANY)
            checker2.assert_called_once_with('foo', 1, 'status', io_loop=mock.ANY)

    def test_any_failure_fails_all_first(self):
        rv1 = tornado.concurrent.Future()
        rv1.set_result((404, 'NOK1'))
        rv2 = tornado.concurrent.Future()
        rv2.set_result((200, 'OK2'))
        checker1 = mock.Mock(return_value=rv1)
        checker2 = mock.Mock(return_value=rv2)
        with mock.patch.object(handlers.SpoolServiceHandler, 'CHECKERS', [checker1, checker2]):
            response = self.fetch('/spool/foo/2/status')
            self.assertEqual(404, response.code)
            self.assertEqual('NOK1', response.body)

    def test_any_failure_fails_all_second(self):
        rv1 = tornado.concurrent.Future()
        rv1.set_result((200, 'OK1'))
        rv2 = tornado.concurrent.Future()
        rv2.set_result((404, 'NOK2'))
        checker1 = mock.Mock(return_value=rv1)
        checker2 = mock.Mock(return_value=rv2)
        with mock.patch.object(handlers.SpoolServiceHandler, 'CHECKERS', [checker1, checker2]):
            response = self.fetch('/spool/foo/2/status')
            self.assertEqual(404, response.code)
            self.assertEqual('NOK2', response.body)

    def test_option_parsing(self):
        with mock.patch('sys.argv', ['ignorethis', '--cache-time', '100.0', '--spool-root', 'foo']),\
                mock.patch.object(tornado.ioloop.IOLoop, 'instance'),\
                mock.patch.object(cache, 'configure') as cache_configure,\
                mock.patch.object(main, 'get_app'),\
                mock.patch.object(spool, 'configure') as spool_configure:
            main.main()
            spool_configure.assert_called_once_with(spool_root='foo')
            cache_configure.assert_called_once_with(cache_time=100)