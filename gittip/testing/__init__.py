"""Helpers for testing Gittip.
"""
from __future__ import print_function, unicode_literals

import datetime
import unittest
from decimal import Decimal
from os.path import join, dirname, realpath

import pytz
from aspen import resources
from aspen.testing import AspenHarness
from gittip.billing.payday import Payday
from gittip.models.participant import Participant
from psycopg2 import IntegrityError, InternalError


TOP = realpath(join(dirname(dirname(__file__)), '..'))
SCHEMA = open(join(TOP, "schema.sql")).read()

DUMMY_GITHUB_JSON = u'{"html_url":"https://github.com/whit537","type":"User",'\
'"public_repos":25,"blog":"http://whit537.org/","gravatar_id":"fb054b407a6461'\
'e417ee6b6ae084da37","public_gists":29,"following":15,"updated_at":"2013-01-1'\
'4T13:43:23Z","company":"Gittip","events_url":"https://api.github.com/users/w'\
'hit537/events{/privacy}","repos_url":"https://api.github.com/users/whit537/r'\
'epos","gists_url":"https://api.github.com/users/whit537/gists{/gist_id}","em'\
'ail":"chad@zetaweb.com","organizations_url":"https://api.github.com/users/wh'\
'it537/orgs","hireable":false,"received_events_url":"https://api.github.com/u'\
'sers/whit537/received_events","starred_url":"https://api.github.com/users/wh'\
'it537/starred{/owner}{/repo}","login":"whit537","created_at":"2009-10-03T02:'\
'47:57Z","bio":"","url":"https://api.github.com/users/whit537","avatar_url":"'\
'https://secure.gravatar.com/avatar/fb054b407a6461e417ee6b6ae084da37?d=https:'\
'//a248.e.akamai.net/assets.github.com%2Fimages%2Fgravatars%2Fgravatar-user-4'\
'20.png","followers":90,"name":"Chad Whitacre","followers_url":"https://api.g'\
'ithub.com/users/whit537/followers","following_url":"https://api.github.com/u'\
'sers/whit537/following","id":134455,"location":"Pittsburgh, PA","subscriptio'\
'ns_url":"https://api.github.com/users/whit537/subscriptions"}'
# JSON data as returned from github for whit537 ;)

GITHUB_USER_UNREGISTERED_LGTEST = u'{"public_repos":0,"html_url":"https://git'\
'hub.com/lgtest","type":"User","repos_url":"https://api.github.com/users/lgte'\
'st/repos","gravatar_id":"d41d8cd98f00b204e9800998ecf8427e","following":0,"pu'\
'blic_gists":0,"updated_at":"2013-01-04T17:24:57Z","received_events_url":"htt'\
'ps://api.github.com/users/lgtest/received_events","gists_url":"https://api.g'\
'ithub.com/users/lgtest/gists{/gist_id}","events_url":"https://api.github.com'\
'/users/lgtest/events{/privacy}","organizations_url":"https://api.github.com/'\
'users/lgtest/orgs","avatar_url":"https://secure.gravatar.com/avatar/d41d8cd9'\
'8f00b204e9800998ecf8427e?d=https://a248.e.akamai.net/assets.github.com%2Fima'\
'ges%2Fgravatars%2Fgravatar-user-420.png","login":"lgtest","created_at":"2012'\
'-05-24T20:09:07Z","starred_url":"https://api.github.com/users/lgtest/starred'\
'{/owner}{/repo}","url":"https://api.github.com/users/lgtest","followers":0,"'\
'followers_url":"https://api.github.com/users/lgtest/followers","following_ur'\
'l":"https://api.github.com/users/lgtest/following","id":1775515,"subscriptio'\
'ns_url":"https://api.github.com/users/lgtest/subscriptions"}'
# JSON data as returned from github for unregistered user ``lgtest``

DUMMY_BOUNTYSOURCE_JSON = u'{"slug": "6-corytheboyd","updated_at": "2013-05-2'\
'4T01:45:20Z","last_name": "Boyd","id": 6,"last_seen_at": "2013-05-24T01:45:2'\
'0Z","email": "corytheboyd@gmail.com","fundraisers": [],"frontend_path": "#us'\
'ers/6-corytheboyd","display_name": "corytheboyd","frontend_url": "https://ww'\
'w.bountysource.com/#users/6-corytheboyd","created_at": "2012-09-14T03:28:07Z'\
'","first_name": "Cory","bounties": [],"image_url": "https://secure.gravatar.'\
'com/avatar/bdeaea505d059ccf23d8de5714ae7f73?d=https://a248.e.akamai.net/asse'\
'ts.github.com%2Fimages%2Fgravatars%2Fgravatar-user-420.png"}'
# JSON data as returned from bountysource for corytheboyd! hello, whit537 ;)


class Harness(AspenHarness, unittest.TestCase):

    def __init__(self, *a, **kw):
        unittest.TestCase.__init__(self, *a, **kw)
        AspenHarness.__init__( self
                             , www_root=str(realpath(join(TOP, 'www')))
                             , project_root=str(TOP)
                              )

    def setUp(self):
        self.db = self.website.db
        self._tablenames = self.db.all("SELECT tablename FROM pg_tables "
                                       "WHERE schemaname='public'")
        self.clear_tables(self.db, self._tablenames[:])

    def tearDown(self):
        self.clear_tables(self.db, self._tablenames[:])

    @staticmethod
    def clear_tables(db, tablenames):
        while tablenames:
            tablename = tablenames.pop()
            try:
                # I tried TRUNCATE but that was way slower for me.
                db.run("DELETE FROM %s CASCADE" % tablename)
            except (IntegrityError, InternalError):
                tablenames.insert(0, tablename)

    def make_participant(self, username, **kw):
        participant = Participant.with_random_username()
        participant.change_username(username)

        # brute force update for use in testing
        for k,v in kw.items():
            if k == 'claimed_time':
                if v == 'now':
                    v = datetime.datetime.now(pytz.utc)
            self.db.run("UPDATE participants SET {}=%s WHERE username=%s" \
                        .format(k), (v, participant.username))
        participant.set_attributes(**kw)

        return participant

    def make_payday(self, *transfers):

        with self.db.get_cursor() as cursor:
            last_end = datetime.datetime(year=2012, month=1, day=1)
            last_end = cursor.one("SELECT ts_end FROM paydays ORDER BY ts_end DESC LIMIT 1", default=last_end)
            ts_end = last_end + datetime.timedelta(days=7)
            ts_start = ts_end - datetime.timedelta(hours=1)
            transfer_volume = Decimal(0)
            active = set()
            for i, (f, t, amount) in enumerate(transfers):
                cursor.run("INSERT INTO transfers (timestamp, tipper, tippee, amount)"
                              "VALUES (%s, %s, %s, %s)",
                              (ts_start + datetime.timedelta(seconds=i), f, t, amount))
                transfer_volume += Decimal(amount)
                active.add(f)
                active.add(t)
            cursor.run("INSERT INTO paydays (ts_start, ts_end, nactive, transfer_volume) VALUES (%s, %s, %s, %s)",
                    (ts_start, ts_end, len(active), transfer_volume))


class GittipPaydayTest(Harness):

    def setUp(self):
        super(GittipPaydayTest, self).setUp()
        self.payday = Payday(self.db)


# Helpers for managing test data.
# ===============================

def load_simplate(path):
    """Given an URL path, return resource.
    """
    from aspen.http.request import Request
    request = Request(uri=path)
    return resources.get(request)
