# Copyright (C) 2008-2009 AG Projects. See LICENSE for details.
#

"""Synchronous versions of Engine and related classes (Invitation, Registration)

GreenXXX typically has the same methods as XXX with the exception that the methods
of XXX are synchronous, i.e. they block the calling greenlet until the job is done.

For example, GreenRegistration.register calls Registration.register and then
waits for 'registered' or 'unregistered' event. If the event received is
'unregistered', it raises RegistrationError().
"""
from __future__ import with_statement
from contextlib import contextmanager
from application import log
from application.notification import NotificationCenter
from application.python.util import Singleton

from eventlet.api import sleep
from eventlet import api, proc, coros

from sipsimple.engine import Engine
from sipsimple.core import Registration, Invitation, WaveFile
from sipsimple.green import notification, GreenBase
from sipsimple.util import NotificationHandler

__all__ = ['Error',
           'SIPError',
           'RegistrationError',
           'InvitationError',
           'SDPNegotiationError',
           'GreenEngine',
           'IncomingSessionHandler',
           'GreenRegistration',
           'Ringer',
           'GreenInvitation']


class Error(Exception):
    pass

class SIPError(Error):

    def __init__(self, **params):
        params.setdefault('code', None)
        params.setdefault('reason', None)
        params.setdefault('originator', 'remote')
        self.params = params

    def __str__(self):
        return '%s %s' % (self.params.get('code'), self.params.get('reason'))

    def __getattr__(self, item):
        try:
            return self.params[item]
        except KeyError:
            raise AttributeError('No key %r in params' % item)

class RegistrationError(SIPError):
    pass

class InvitationError(SIPError):
    pass

class ReInvitationError(InvitationError):
    pass

class SDPNegotiationError(Error):
    pass

class EngineError(Error):
    pass

class GreenEngine(GreenBase, NotificationHandler):
    __metaclass__ = Singleton
    klass = Engine

    def __init__(self):
        """Create a new instance.
        Subscribe to SIPEngineGotException and print the errors to the log.
        Subscribe to SIPEngineDidFail and convert them into an exception in the current greenlet.
        """
        GreenBase.__init__(self)
        self._subscribe_SIPEngineGotException()
        self.link_error()

    def stop(self):
        if self._thread_started:
            with self.linked_notifications(['SIPEngineDidEnd', 'SIPEngineDidFail', 'SIPEngineGotException']) as q:
                self._obj._thread_stopping = True
                q.wait()

    def link_error(self, greenlet=None):
        """Asynchonously raise an exception in `greenlet' (the current one by default) when the engine
        signals failure through SIPEngineDidFail notification.
        """
        if greenlet is None:
            greenlet = api.getcurrent()
        error_observer = notification.CallFromThreadObserver(lambda n: greenlet.throw(EngineError(str(n))))
        self.notification_center.add_observer(error_observer, 'SIPEngineDidFail')

    def _NH_SIPEngineGotException(self, engine, notification_data):
        log.error('An error in the PJSIP thread on %s:\n%s' % (notification_data.timestamp, notification_data.traceback))

    def _subscribe_SIPEngineGotException(self):
        self.notification_center.add_observer(observer=notification.NotifyFromThreadObserver(self), name='SIPEngineGotException')

    @contextmanager
    def linked_incoming(self, queue=None):
        # DEPRECATED, it's here for older scripts. for newer ones, use a notification
        if queue is None:
            queue = coros.queue()
        def wrap_and_send_to_queue(n):
            obj = GreenInvitation(__obj=n.sender)
            queue.send(obj)
        observer = notification.CallFromThreadObserver(wrap_and_send_to_queue, lambda n: n.data.state=='INCOMING')
        self.notification_center.add_observer(observer, 'SIPInvitationChangedState')
        try:
            yield queue
        finally:
            self.notification_center.remove_observer(observer, 'SIPInvitationChangedState')


def play_wav_file(filepath, *args, **kwargs):
    """Play wav file identified by filepath. Wait until playing is completed.

    Temporary WaveFile instance is created to play the file. The rest of the
    arguments (`args' and `kwargs') are passed to WaveFile.start method.
    """
    w = WaveFile(filepath)
    with notification.linked_notification(name='WaveFileDidFinishPlaying', sender=w) as q:
        w.start(*args, **kwargs)
        q.wait()
        w.stop()


class IncomingSessionHandler(object):

    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def handle(self, inv, *args, **kwargs):
        ERROR = 488
        try:
            for handler in self.handlers:
                if handler.is_acceptable(inv):
                    ERROR = None
                    return handler.handle(inv, *args, **kwargs)
        except:
            ERROR = 500
            raise
        finally:
            if ERROR is not None:
                proc.spawn_greenlet(inv.disconnect, ERROR)


class GreenRegistration(GreenBase):
    event_name = 'SIPRegistrationChangedState'
    klass = Registration

    def register(self):
        if self.state != 'registered':
            with self.linked_notification(condition = lambda n: n.data.state in ['registered', 'unregistered']) as q:
                if self.state != 'registering':
                    self._obj.register()
                n = q.wait()
                if n.data.state != 'registered':
                    raise RegistrationError(n.data.__dict__)

    def unregister(self):
        if self.state != 'unregistered':
            with self.linked_notification(condition=lambda n: n.data.state in ['unregistered', 'registered']) as q:
                if self.state != 'unregistering':
                    self._obj.unregister()
                n = q.wait()
                if n.data.state != 'unregistered':
                    log.error('Unexpected notification: %s' % (n, ))
                return n

# DEPRECATED, will be removed
class Ringer(object):

    delay = 5

    def __init__(self, play_wav_func, *args, **kwargs):
        self.play_wav = play_wav_func
        self.args = args
        self.kwargs = kwargs
        self.gthread = None
        self.count = 0

    def start(self):
        self.count += 1
        if self.gthread is None:
            self.gthread = proc.spawn_link_exception(self._run)

    def stop(self):
        self.count -= 1
        if self.count <=0 and self.gthread is not None:
            self.gthread.kill()
            self.gthread = None

    def _run(self):
        try:
            while True:
                self.play_wav(*self.args, **self.kwargs)
                sleep(self.delay)
        except proc.ProcExit:
            pass


class GreenInvitation(GreenBase):

    event_names = ['SIPInvitationChangedState', 'SIPInvitationGotSDPUpdate']
    klass = Invitation

    @property
    def confirmed(self):
        return self.state == 'CONFIRMED'

    def _wait_notifications(self, q, sdp_notification_data=None):
        """Wait for SIPInvitationChangedState(state=CONFIRMED) and SIPInvitationGotSDPUpdate notifications.
        Return tuple of 2 items - data of those 2 notifications.
        """
        confirmed_notification_data = None
        while confirmed_notification_data is None or sdp_notification_data is None:
            notification = q.wait()
            data = notification.data
            if notification.name == self.event_names[0]:
                if data.state=='CONFIRMED':
                    confirmed_notification_data = notification.data
                    if getattr(data, 'code', 200) != 200:
                        raise ReInvitationError(**data.__dict__)
                elif data.state=='DISCONNECTING':
                    raise InvitationError(originator='local')
                elif data.state=='DISCONNECTED':
                    raise InvitationError(**data.__dict__)
            elif notification.name == self.event_names[1]:
                sdp_notification_data = notification.data
                if not data.succeeded:
                    raise SDPNegotiationError('SDP negotiation failed: %s' % notification.data.error)
        return confirmed_notification_data, sdp_notification_data

    def send_invite(self, *args, **kwargs):
        """Call send_invite on the proxied object. Wait until session is established or terminated.

        Raise SessionError if session was not established.
        Raise SDPNegotiationError is SDP negotiation failed.
        """
        assert self.state=='NULL', self.state
        with self.linked_notifications() as q:
            self._obj.send_invite(*args, **kwargs)
            return self._wait_notifications(q)

    def send_reinvite(self, *args, **kwargs):
        assert self.state=='CONFIRMED', self.state # this asserts are probably should be just removed
        with self.linked_notifications() as q:
            self._obj.send_reinvite(*args, **kwargs)
            return self._wait_notifications(q)

    def disconnect(self, *args, **kwargs):
        """Call disconnect() on the proxied object. Wait until SIP session is disconnected"""
        with self.linked_notification(self.event_names[0], condition=lambda n: n.data.state=='DISCONNECTED') as q:
            if self.state in ['NULL', 'DISCONNECTED']:
                return
            if self.state != 'DISCONNECTING':
                self._obj.disconnect(*args, **kwargs)
            return q.wait()

    def accept_invite(self, *args, **kwargs):
        """Call accept_invite() on the proxied object. Wait until SIP session is confirmed.
        Raise InvitationError if session was disconnected.
        """
        assert self.state in ['INCOMING', 'EARLY'], self.state
        with self.linked_notifications() as q:
            self._obj.accept_invite(*args, **kwargs)
            return self._wait_notifications(q)

    def respond_to_reinvite(self, *args, **kwargs):
        assert self.state in ['REINVITED'], self.state
        with self.linked_notifications() as q:
            self._obj.respond_to_reinvite(*args, **kwargs)
            return self._wait_notifications(q, sdp_notification_data=False)

    def call_on_disconnect(self, func):
        # legacy function still used by the old script; use a notification in new scripts
        observer = notification.CallFromThreadObserver(func, condition=lambda n: n.data.state=='DISCONNECTED')
        notification_center = NotificationCenter()
        notification_center.add_observer(observer, self.event_names[0], self._obj)
        return Cancellable(lambda : notification_center.remove_observer(observer, self.event_names[0], self._obj))


# legacy, used only by call_on_disconnect
class Cancellable(object):

    def __init__(self, cancel_function):
        self.on_cancel = cancel_function

    def cancel(self):
        if self.on_cancel is not None:
            on_cancel = self.on_cancel
            self.on_cancel = None
            on_cancel()

