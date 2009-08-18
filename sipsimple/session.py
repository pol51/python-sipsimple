# Copyright (C) 2008-2009 AG Projects. See LICENSE for details.
#

from __future__ import with_statement

from datetime import datetime
from threading import RLock

from application.notification import IObserver, Notification, NotificationCenter
from application.python.decorator import decorator, preserve_signature
from application.python.util import Singleton
from eventlet import api
from eventlet.coros import queue
from zope.interface import implements

from sipsimple.core import Invitation, SIPCoreError, SIPCoreInvalidStateError, sip_status_messages
from sipsimple.core import ContactHeader, FromHeader, RouteHeader, WarningHeader
from sipsimple.core import SDPConnection, SDPMediaStream, SDPSession
from sipsimple.engine import Engine

from sipsimple.account import AccountManager
from sipsimple.audiostream import AudioStream
from sipsimple.configuration.settings import SIPSimpleSettings
from sipsimple.msrpstream import MSRPChat, MSRPIncomingFileStream
from sipsimple.util import TimestampedNotificationData, run_in_twisted


class MediaStreamDidFailError(Exception):
    def __init__(self, stream, data):
        self.stream = stream
        self.data = data

class InvitationDidFailError(Exception):
    def __init__(self, invitation, data):
        self.invitation = invitation
        self.data = data


@decorator
def transition_state(required_state, new_state):
    def state_transitioner(func):
        @preserve_signature(func)
        def wrapper(obj, *args, **kwargs):
            with obj._lock:
                if obj.state != required_state:
                    raise RuntimeError('cannot call %s in %s state' % (func.__name__, obj.state))
                obj.state = new_state
            return func(obj, *args, **kwargs)
        return wrapper
    return state_transitioner


class Session(object):
    implements(IObserver)

    def __init__(self, account):
        self.account = account
        self.direction = None
        self.end_time = None
        self.on_hold = False
        self.proposed_streams = None
        self.route = None
        self.state = None
        self.start_time = None
        self.streams = None
        self.transport = None
        self.greenlet = None
        self._channel = queue()
        self._hold_in_progress = False
        self._invitation = None
        self._local_identity = None
        self._remote_identity = None
        self._lock = RLock()

    def init_incoming(self, invitation):
        notification_center = NotificationCenter()
        remote_sdp = invitation.sdp.proposed_remote
        self.proposed_streams = []
        if remote_sdp:
            for index, media_stream in enumerate(remote_sdp.media):
                if media_stream.port != 0:
                    stream = None
                    if media_stream.media == 'audio':
                        stream = AudioStream(self.account)
                    elif media_stream.media == 'message' and 'file-selector' in (attr.name for attr in media_stream.attributes):
                        stream = MSRPIncomingFileStream(self.account)
                    elif media_stream.media == 'message':
                        stream = MSRPChat(self.account)
                    if stream is not None and stream.validate_incoming(remote_sdp, index):
                        stream.index = index
                        self.proposed_streams.append(stream)
        if self.proposed_streams:
            self.direction = 'incoming'
            self.state = 'incoming'
            self.transport = invitation.transport
            self._invitation = invitation
            notification_center.add_observer(self, sender=invitation)
            notification_center.post_notification('SIPSessionNewIncoming', self, TimestampedNotificationData(streams=self.proposed_streams))
        else:
            invitation.send_response(488)

    @transition_state(None, 'connecting')
    @run_in_twisted
    def connect(self, to_header, routes, streams):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()
        settings = SIPSimpleSettings()

        connected = False
        received_code = 0
        received_reason = None
        unhandled_notifications = []

        self.direction = 'outgoing'
        self.proposed_streams = streams
        self.route = routes[0]
        self.transport = self.route.transport
        self._invitation = Invitation()
        self._local_identity = FromHeader(self.account.uri, self.account.display_name)
        self._remote_identity = to_header
        notification_center.add_observer(self, sender=self._invitation)
        notification_center.post_notification('SIPSessionNewOutgoing', self, TimestampedNotificationData(streams=streams))
        for stream in self.proposed_streams:
            notification_center.add_observer(self, sender=stream)
            stream.initialize(self)

        try:
            wait_count = len(self.proposed_streams)
            while wait_count > 0:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidInitialize':
                    wait_count -= 1

            local_ip = settings.sip.local_ip.normalized
            local_sdp = SDPSession(local_ip, connection=SDPConnection(local_ip), name=settings.user_agent)
            stun_addresses = []
            for index, stream in enumerate(self.proposed_streams):
                stream.index = index
                media = stream.get_local_media(for_offer=True)
                local_sdp.media.append(media)
                stun_addresses.extend((attr.value.split(' ', 5)[4] for attr in media.attributes if attr.name == 'candidate' and attr.value.startswith('S ')))
            if stun_addresses:
                local_sdp.connection.address = stun_addresses[0]
            self._invitation.send_invite(FromHeader(self.account.uri, self.account.display_name), to_header, RouteHeader(self.route.get_uri()),
                                         ContactHeader(self.account.contact[self.route.transport]), local_sdp, self.account.credentials)
            while True:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    if notification.data.succeeded:
                        local_sdp = notification.data.local_sdp
                        remote_sdp = notification.data.remote_sdp
                        break
                    else:
                        for stream in self.proposed_streams:
                            notification_center.remove_observer(self, sender=stream)
                            stream.end()
                        self._fail(originator='remote', code=received_code, reason=received_reason, error='SDP negotiation failed: %s' % notification.data.error)
                        return
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'early' and notification.data.code == 180:
                        notification_center.post_notification('SIPSessionGotRingIndication', self, TimestampedNotificationData())
                    elif notification.data.state == 'connecting':
                        received_code = notification.data.code
                        received_reason = notification.data.reason
                    elif notification.data.state == 'connected':
                        if not connected:
                            connected = True
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                                  TimestampedNotificationData(originator='local', method='INVITE', code=received_code, reason=received_reason))
                        else:
                            unhandled_notifications.append(notification)

            notification_center.post_notification('SIPSessionWillStart', self, TimestampedNotificationData())
            stream_map = dict((stream.index, stream) for stream in self.proposed_streams)
            for index, local_media in enumerate(local_sdp.media):
                remote_media = remote_sdp.media[index]
                stream = stream_map[index]
                if remote_media.port:
                    stream.start(local_sdp, remote_sdp, index)
                else:
                    notification_center.remove_observer(self, sender=stream)
                    self.proposed_streams.remove(stream)
                    del stream_map[stream.index]
                    stream.end()
            removed_streams = [stream for stream in self.proposed_streams if stream.index >= len(local_sdp.media)]
            for stream in removed_streams:
                notification_center.remove_observer(self, sender=stream)
                self.proposed_streams.remove(stream)
                del stream_map[stream.index]
                stream.end()
            wait_count = len(self.proposed_streams)
            while wait_count > 0 or not connected or self._channel:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidStart':
                    wait_count -= 1
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'early' and notification.data.code == 180:
                        notification_center.post_notification('SIPSessionGotRingIndication', self, TimestampedNotificationData())
                    elif notification.data.state == 'connecting':
                        received_code = notification.data.code
                        received_reason = notification.data.reason
                    elif notification.data.state == 'connected':
                        if not connected:
                            connected = True
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                                  TimestampedNotificationData(originator='local', method='INVITE', code=received_code, reason=received_reason))
                        else:
                            unhandled_notifications.append(notification)
        except MediaStreamDidFailError, e:
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            self._fail(originator='local', code=received_code, reason=received_reason, error='media stream failed: %s' % e.data.reason)
        except InvitationDidFailError, e:
            notification_center.remove_observer(self, sender=self._invitation)
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            self.state = 'terminated'
            if e.data.prev_state in ('connecting', 'connected'):
                notification_center.post_notification('SIPSessionWillEnd', self, TimestampedNotificationData(originator=e.data.originator))
                if e.data.originator == 'remote':
                    notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method=e.data.method, code=200, reason=sip_status_messages[200]))
                self.end_time = datetime.now()
                notification_center.post_notification('SIPSessionDidEnd', self, TimestampedNotificationData(originator=e.data.originator, end_reason=e.data.disconnect_reason))
            else:
                if e.data.originator == 'remote':
                    notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='INVITE', code=e.data.code, reason=e.data.reason))
                code = e.data.code if e.data.originator == 'remote' else 0
                reason = e.data.reason if e.data.originator == 'remote' else None
                notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator=e.data.originator, code=code, reason=reason, failure_reason=e.data.disconnect_reason))
            self.greenlet = None
        except SIPCoreError, e:
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            self._fail(originator='local', code=received_code, reason=received_reason, error='SIP core error: %s' % str(e))
        else:
            self.greenlet = None
            self.state = 'connected'
            self.streams = self.proposed_streams
            self.proposed_streams = None
            self.start_time = datetime.now()
            notification_center.post_notification('SIPSessionDidStart', self, TimestampedNotificationData(streams=self.streams))
            for notification in unhandled_notifications:
                self.handle_notification(notification)
            if self._hold_in_progress:
                self._send_hold()

    @transition_state('incoming', 'incoming')
    @run_in_twisted
    def send_ring_indication(self):
        try:
            self._invitation.send_response(180)
        except SIPCoreInvalidStateError:
            pass # The INVITE session might have already been canceled; ignore the error

    @transition_state('incoming', 'accepting')
    @run_in_twisted
    def accept(self, streams):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()
        settings = SIPSimpleSettings()

        connected = False
        unhandled_notifications = []

        if self.proposed_streams:
            for stream in self.proposed_streams:
                if stream in streams:
                    notification_center.add_observer(self, sender=stream)
                    stream.initialize(self)
                else:
                    stream.end()
        else:
            for index, stream in enumerate(streams):
                notification_center.add_observer(self, sender=stream)
                stream.index = index
                stream.initialize(self)
        self.proposed_streams = streams

        try:
            wait_count = len(self.proposed_streams)
            while wait_count > 0:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidInitialize':
                    wait_count -= 1

            local_ip = settings.sip.local_ip.normalized
            local_sdp = SDPSession(local_ip, connection=SDPConnection(local_ip), name=settings.user_agent)
            stun_addresses = []
            if self._invitation.sdp.proposed_remote:
                stream_map = dict((stream.index, stream) for stream in self.proposed_streams)
                for index, media in enumerate(self._invitation.sdp.proposed_remote.media):
                    stream = stream_map.get(index, None)
                    if stream is not None:
                        media = stream.get_local_media(for_offer=False)
                        local_sdp.media.append(media)
                        stun_addresses.extend((attr.value.split(' ', 5)[4] for attr in media.attributes if attr.name == 'candidate' and attr.value.startswith('S ')))
                    else:
                        media = SDPMediaStream.new(media)
                        media.port = 0
                        local_sdp.media.append(media)
            else:
                for stream in self.proposed_streams:
                    media = stream.get_local_media(for_offer=True)
                    local_sdp.media.append(media)
                    stun_addresses.extend((attr.value.split(' ', 5)[4] for attr in media.attributes if attr.name == 'candidate' and attr.value.startswith('S ')))
            if stun_addresses:
                local_sdp.connection.address = stun_addresses[0]
            self._invitation.send_response(200, sdp=local_sdp)
            notification_center.post_notification('SIPSessionWillStart', self, TimestampedNotificationData())
            local_sdp = self._invitation.sdp.active_local
            remote_sdp = self._invitation.sdp.active_remote
            # while entered only if initial INVITE did not contain SDP and we are waiting for the ACK which should contain it
            while remote_sdp is None or local_sdp is None:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    if notification.data.succeeded:
                        local_sdp = notification.data.local_sdp
                        remote_sdp = notification.data.remote_sdp
                        break
                    else:
                        if not connected:
                            # we could not have got a SIPInvitationGotSDPUpdate if we did not get an ACK
                            connected = True
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                                  TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason=sip_status_messages[200], ack_received=True))
                        for stream in self.proposed_streams:
                            notification_center.remove_observer(self, sender=stream)
                            stream.end()
                        self._fail(originator='remote', code=200, reason=sip_status_messages[200], error='SDP negotiation failed: %s' % notification.data.error)
                        return
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected':
                        if not connected:
                            connected = True
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason=sip_status_messages[200], ack_received=True))
                        elif notification.data.prev_state == 'connected':
                            unhandled_notifications.append(notification)
            wait_count = 0
            stream_map = dict((stream.index, stream) for stream in self.proposed_streams)
            for index, local_media in enumerate(local_sdp.media):
                remote_media = remote_sdp.media[index]
                stream = stream_map.get(index, None)
                if stream is not None:
                    if remote_media.port:
                        wait_count += 1
                        stream.start(local_sdp, remote_sdp, index)
                    else:
                        notification_center.remove_observer(self, sender=stream)
                        self.proposed_streams.remove(stream)
                        del stream_map[stream.index]
                        stream.end()
            removed_streams = [stream for stream in self.proposed_streams if stream.index >= len(local_sdp.media)]
            for stream in removed_streams:
                notification_center.remove_observer(self, sender=stream)
                self.proposed_streams.remove(stream)
                del stream_map[stream.index]
                stream.end()
            while wait_count > 0 or not connected or self._channel:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidStart':
                    wait_count -= 1
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected':
                        if not connected:
                            connected = True
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason='OK', ack_received=True))
                        elif notification.data.prev_state == 'connected':
                            unhandled_notifications.append(notification)
                else:
                    unhandled_notifications.append(notification)
        except MediaStreamDidFailError, e:
            if self._invitation.state == 'connecting':
                # pjsip's invite session object does not inform us whether the ACK was received or not
                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason='OK', ack_received='unknown'))
            elif self._invitation.state == 'connected' and not connected:
                # we didn't yet get to process the SIPInvitationChangedState (state -> connected) notification
                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason='OK', ack_received=True))
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            code = 200 if self._invitation.state not in ('incoming', 'early') else 0
            reason = sip_status_messages[200] if self._invitation.state not in ('incoming', 'early') else None
            self._fail(originator='local', code=code, reason=reason, error='media stream failed: %s' % e.data.reason)
        except InvitationDidFailError, e:
            notification_center.remove_observer(self, sender=self._invitation)
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            self.state = 'terminated'
            if e.data.prev_state in ('incoming', 'early'):
                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=487, reason='Canceled', ack_received='unknown'))
                notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='remote', code=487, reason='Canceled', failure_reason=e.data.disconnect_reason))
            elif e.data.prev_state == 'connecting' and e.data.disconnect_reason == 'missing ACK':
                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason='OK', ack_received=False))
                notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='local', code=200, reason=sip_status_messages[200], failure_reason=e.data.disconnect_reason))
            else:
                notification_center.post_notification('SIPSessionWillEnd', self, TimestampedNotificationData(originator='remote'))
                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method=e.data.method, code=200, reason='OK'))
                self.end_time = datetime.now()
                notification_center.post_notification('SIPSessionDidEnd', self, TimestampedNotificationData(originator='remote', end_reason=e.data.disconnect_reason))
            self.greenlet = None
        except SIPCoreInvalidStateError:
            # the only reason for which this error can be thrown is if invitation.send_response was called after the INVITE session was canceled by the remote party
            notification_center.remove_observer(self, sender=self._invitation)
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            self.state = 'terminated'
            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=487, reason='Canceled', ack_received='unknown'))
            notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='remote', code=487, reason='Canceled', failure_reason='user request'))
        except SIPCoreError, e:
            for stream in self.proposed_streams:
                notification_center.remove_observer(self, sender=stream)
                stream.end()
            code = 200 if self._invitation.state not in ('incoming', 'early') else 0
            reason = sip_status_messages[200] if self._invitation.state not in ('incoming', 'early') else None
            self._fail(originator='local', code=code, reason=reason, error='SIP core error: %s' % str(e))
        else:
            self.greenlet = None
            self.state = 'connected'
            self.streams = self.proposed_streams
            self.proposed_streams = None
            self.start_time = datetime.now()
            notification_center.post_notification('SIPSessionDidStart', self, TimestampedNotificationData(streams=self.streams))
            for notification in unhandled_notifications:
                self.handle_notification(notification)
            if self._hold_in_progress:
                self._send_hold()

    @transition_state('incoming', 'terminating')
    @run_in_twisted
    def reject(self, code=603):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        for stream in self.proposed_streams:
            stream.end()

        try:
            self._invitation.send_response(code)
            with api.timeout(1):
                while True:
                    notification = self._channel.wait()
                    if notification.name == 'SIPInvitationChangedState':
                        if notification.data.state == 'disconnected':
                            ack_received = notification.data.disconnect_reason != 'missing ACK'
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                                  TimestampedNotificationData(originator='remote', method='INVITE', code=code, reason=sip_status_messages[code], ack_received=ack_received))
                            break
        except SIPCoreInvalidStateError:
            # the only reason for which this error can be thrown is if invitation.send_response was called after the INVITE session was canceled by the remote party
            notification_center.remove_observer(self, sender=self._invitation)
            self.state = 'terminated'
            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=487, reason='Canceled', ack_received='unknown'))
            notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='remote', code=487, reason='Canceled', failure_reason='user request'))
        except SIPCoreError, e:
            code = 200 if self._invitation.state not in ('incoming', 'early') else 0
            reason = sip_status_messages[200] if self._invitation.state not in ('incoming', 'early') else None
            self._fail(originator='local', code=code, reason=reason, error='SIP core error: %s' % str(e))
        except api.TimeoutError:
            notification_center.remove_observer(self, sender=self._invitation)
            self.greenlet = None
            self.state = 'terminated'
            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=code, reason=sip_status_messages[code], ack_received=False))
            notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='local', code=code, reason=sip_status_messages[code], failure_reason='user request'))
        else:
            notification_center.remove_observer(self, sender=self._invitation)
            self.greenlet = None
            self.state = 'terminated'
            self.proposed_streams = None
            notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='local', code=code, reason=sip_status_messages[code], failure_reason='user request'))

    @transition_state('received_proposal', 'accepting_proposal')
    @run_in_twisted
    def accept_proposal(self, streams):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        unhandled_notifications = []

        for stream in self.proposed_streams:
            if stream in streams:
                notification_center.add_observer(self, sender=stream)
                stream.initialize(self)
            else:
                stream.end()

        try:
            wait_count = len(self.proposed_streams)
            while wait_count > 0:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidInitialize':
                    wait_count -= 1

            local_sdp = SDPSession.new(self._invitation.sdp.active_local)
            local_sdp.version += 1
            stream_map = dict((stream.index, stream) for stream in self.proposed_streams)
            for index, media in enumerate(self._invitation.sdp.proposed_remote.media):
                stream = stream_map.get(index, None)
                if stream is not None:
                    local_sdp.media.append(stream.get_local_media(for_offer=False))
                else:
                    media = SDPMediaStream.new(media)
                    media.port = 0
                    local_sdp.media.append(media)
            self._invitation.send_response(200, sdp=local_sdp)

            prev_on_hold_streams = set(stream for stream in self.streams if stream.hold_supported and stream.on_hold_by_remote)

            received_invitation_state = False
            received_sdp_update = False
            while not received_invitation_state or not received_sdp_update:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    received_sdp_update = True
                    if notification.data.succeeded:
                        local_sdp = notification.data.local_sdp
                        remote_sdp = notification.data.remote_sdp
                        for stream in self.streams:
                            stream.update(local_sdp, remote_sdp, stream.index)
                    else:
                        self._fail_proposal(originator='remote', error='SDP negotiation failed: %s' % notification.data.error)
                        return
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason=sip_status_messages[200], ack_received='unknown'))
                        received_invitation_state = True

            on_hold_streams = set(stream for stream in self.streams if stream.hold_supported and stream.on_hold_by_remote)
            if on_hold_streams != prev_on_hold_streams:
                hold_supported_streams = (stream for stream in self.streams if stream.hold_supported)
                notification_center.post_notification('SIPSessionDidChangeHoldState', self, TimestampedNotificationData(originator='remote', on_hold=bool(on_hold_streams),
                                                      partial=bool(on_hold_streams) and any(not stream.on_hold_by_remote for stream in hold_supported_streams)))

            for stream in self.proposed_streams:
                stream.start(local_sdp, remote_sdp, stream.index)
            wait_count = len(self.proposed_streams)
            while wait_count > 0 or self._channel:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidStart':
                    wait_count -= 1
                else:
                    unhandled_notifications.append(notification)
        except MediaStreamDidFailError, e:
            self._fail_proposal(originator='remote', error='media stream failed: %s' % e.data.reason)
        except InvitationDidFailError, e:
            self._fail_proposal(originator='remote', error='session ended')
            self.handle_notification(Notification('SIPInvitationChangedState', e.invitation, e.data))
        except SIPCoreError, e:
            self._fail_proposal(originator='remote', error='SIP core error: %s' % str(e))
        else:
            self.greenlet = None
            self.state = 'connected'
            notification_center.post_notification('SIPSessionGotAcceptProposal', self, TimestampedNotificationData(originator='remote', streams=self.proposed_streams))
            self.streams = self.streams + self.proposed_streams
            proposed_streams = self.proposed_streams
            self.proposed_streams = None
            notification_center.post_notification('SIPSessionDidRenegotiateStreams', self, TimestampedNotificationData(originator='remote', action='add', streams=proposed_streams))
            for notification in unhandled_notifications:
                self.handle_notification(notification)
            if self._hold_in_progress:
                self._send_hold()

    @run_in_twisted
    def reject_proposal(self, code=488):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        for stream in self.proposed_streams:
            stream.end()

        try:
            self._invitation.send_response(code)
            with api.timeout(1, None):
                while True:
                    notification = self._channel.wait()
                    if notification.name == 'SIPInvitationChangedState':
                        if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=code, reason=sip_status_messages[code], ack_received='unknown'))
        except SIPCoreError, e:
            self._fail_proposal(originator='remote', error='SIP core error: %s' % str(e))
        else:
            self.greenlet = None
            self.state = 'connected'
            notification_center.post_notification('SIPSessionGotRejectProposal', self, TimestampedNotificationData(originator='remote', code=code, reason=sip_status_messages[code], streams=self.proposed_streams))
            self.proposed_streams = None
            if self._hold_in_progress:
                self._send_hold()

    @transition_state('connected', 'sending_proposal')
    @run_in_twisted
    def add_stream(self, stream):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        received_code = None
        received_reason = None
        unhandled_notifications = []

        self.proposed_streams = [stream]
        notification_center.add_observer(self, sender=stream)
        stream.initialize(self)

        try:
            while True:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidInitialize':
                    break
                elif notification.name == 'SIPInvitationChangedState':
                    # This is actually the only reason for which this notification could be received
                    if notification.data.state == 'connected' and notification.data.sub_state == 'received_proposal':
                        self._fail_proposal(originator='local', error='received stream proposal')
                        self.handle_notification(notification)
                        return

            local_sdp = SDPSession.new(self._invitation.sdp.active_local)
            local_sdp.version += 1
            stream.index = len(local_sdp.media)
            local_sdp.media.append(stream.get_local_media(for_offer=True))
            self._invitation.send_reinvite(sdp=local_sdp)
            notification_center.post_notification('SIPSessionGotProposal', self, TimestampedNotificationData(originator='local', streams=self.proposed_streams))

            received_invitation_state = False
            received_sdp_update = False
            while not received_invitation_state or not received_sdp_update:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    received_sdp_update = True
                    if notification.data.succeeded:
                        local_sdp = notification.data.local_sdp
                        remote_sdp = notification.data.remote_sdp
                    else:
                        self._fail_proposal(originator='local', error='SDP negotiation failed: %s' % notification.data.error)
                        return
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                        received_invitation_state = True
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='INVITE', code=notification.data.code, reason=notification.data.reason))
                        if 200 <= notification.data.code < 300:
                            received_code = notification.data.code
                            received_reason = notification.data.reason
                        else:
                            notification_center.remove_observer(self, sender=stream)
                            stream.end()
                            notification_center.post_notification('SIPSessionGotRejectProposal', self, TimestampedNotificationData(originator='local', code=notification.data.code, reason=notification.data.reason, streams=self.proposed_streams))
                            self.state = 'connected'
                            self.proposed_streams = None
                            self.greenlet = None
                            return

            try:
                remote_media = remote_sdp.media[stream.index]
            except IndexError:
                self._fail_proposal(originator='local', error='SDP media missing in answer')
                return
            else:
                if remote_media.port:
                    stream.start(local_sdp, remote_sdp, stream.index)
                else:
                    notification_center.remove_observer(self, sender=stream)
                    stream.end()
                    notification_center.post_notification('SIPSessionGotRejectProposal', self, TimestampedNotificationData(originator='local', code=received_code, reason=received_reason, streams=self.proposed_streams))
                    self.state = 'connected'
                    self.proposed_streams = None
                    self.greenlet = None
                    return

            wait_count = 1
            while wait_count > 0 or self._channel:
                notification = self._channel.wait()
                if notification.name == 'MediaStreamDidStart':
                    wait_count -= 1
        except MediaStreamDidFailError, e:
            self._fail_proposal(originator='local', error='media stream failed: %s' % e.data.reason)
        except InvitationDidFailError, e:
            self._fail_proposal(originator='local', error='session ended')
            self.handle_notification(Notification('SIPInvitationChangedState', e.invitation, e.data))
        except SIPCoreError, e:
            self._fail_proposal(originator='local', error='SIP core error: %s' % str(e))
        else:
            self.greenlet = None
            self.state = 'connected'
            notification_center.post_notification('SIPSessionGotAcceptProposal', self, TimestampedNotificationData(originator='local', streams=self.proposed_streams))
            self.streams = self.streams + self.proposed_streams
            proposed_streams = self.proposed_streams
            self.proposed_streams = None
            notification_center.post_notification('SIPSessionDidRenegotiateStreams', self, TimestampedNotificationData(originator='local', action='add', streams=proposed_streams))
            for notification in unhandled_notifications:
                self.handle_notification(notification)
            if self._hold_in_progress:
                self._send_hold()

    @transition_state('connected', 'sending_proposal')
    @run_in_twisted
    def remove_stream(self, stream):
        if stream not in self.streams:
            self.state = 'connected'
            return
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        unhandled_notifications = []

        try:
            local_sdp = SDPSession.new(self._invitation.sdp.active_local)
            local_sdp.version += 1
            local_sdp.media[stream.index].port = 0
            self._invitation.send_reinvite(sdp=local_sdp)

            received_invitation_state = False
            received_sdp_update = False
            while not received_invitation_state or not received_sdp_update:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    received_sdp_update = True
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                        received_invitation_state = True
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='INVITE', code=notification.data.code, reason=notification.data.reason))
        except InvitationDidFailError, e:
            self.greenlet = None
            self.handle_notification(Notification('SIPInvitationChangedState', e.invitation, e.data))
        except SIPCoreError:
            raise #FIXME
        else:
            self.greenlet = None
            self.state = 'connected'
            notification_center.remove_observer(self, sender=stream)
            stream.end()
            self.streams.remove(stream)
            notification_center.post_notification('SIPSessionDidRenegotiateStreams', self, TimestampedNotificationData(originator='local', action='remove', streams=[stream]))
            for notification in unhandled_notifications:
                self.handle_notification(notification)
            if self._hold_in_progress:
                self._send_hold()

    @run_in_twisted
    def hold(self):
        if self.on_hold or self._hold_in_progress:
            return
        self._hold_in_progress = True
        streams = self.streams if self.streams is not None else self.proposed_streams
        if not streams:
            return
        for stream in streams:
            stream.hold()
        if self.state == 'connected':
            self._send_hold()

    @run_in_twisted
    def unhold(self):
        if not self.on_hold or not self._hold_in_progress:
            return
        self._hold_in_progress = False
        streams = self.streams if self.streams is not None else self.proposed_streams
        if not streams:
            return
        for stream in streams:
            stream.unhold()
        if self.state == 'connected':
            self._send_unhold()

    @run_in_twisted
    def end(self):
        if self.greenlet is not None:
            api.kill(self.greenlet, api.GreenletExit())
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()
        if self._invitation.state in ('disconnecting', 'disconnected'):
            return
        self.state = 'terminating'
        if self._invitation.state == 'connected':
            notification_center.post_notification('SIPSessionWillEnd', self, TimestampedNotificationData(originator='local'))
        for stream in ((self.streams or []) + (self.proposed_streams or [])):
            notification_center.remove_observer(self, sender=stream)
            stream.end()
        cancelling = self._invitation.state != 'connected'
        try:
            self._invitation.end(timeout=1)
            while True:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationChangedState' and notification.data.state == 'disconnected':
                    if cancelling:
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                              TimestampedNotificationData(originator='local', method='INVITE', code=487, reason='Canceled'))
                    else:
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                              TimestampedNotificationData(originator='local', method='BYE', code=notification.data.code, reason=notification.data.reason))
                    break
        except SIPCoreError, e:
            if cancelling:
                notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='local', code=0, reason=None, failure_reason='SIP core error: %s' % str(e)))
            else:
                self.end_time = datetime.now()
                notification_center.post_notification('SIPSessionDidEnd', self, TimestampedNotificationData(originator='local', end_reason='SIP core error: %s' % str(e)))
            return
        notification_center.remove_observer(self, sender=self._invitation)
        self.greenlet = None
        self.state = 'terminated'
        if cancelling:
            notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='local', code=487, reason='Canceled', failure_reason='user request'))
        else:
            self.end_time = datetime.now()
            notification_center.post_notification('SIPSessionDidEnd', self, TimestampedNotificationData(originator='local', end_reason='user request'))


    @property
    def local_identity(self):
        if self._invitation is not None and self._invitation.local_identity is not None:
            return self._invitation.local_identity
        else:
            return self._local_identity

    @property
    def remote_identity(self):
        if self._invitation is not None and self._invitation.remote_identity is not None:
            return self._invitation.remote_identity
        else:
            return self._remote_identity

    @property
    def remote_user_agent(self):
        return self._invitation.remote_user_agent if self._invitation is not None else None

    def _send_hold(self):
        self.state = 'sending_proposal'
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        unhandled_notifications = []

        try:
            local_sdp = SDPSession.new(self._invitation.sdp.active_local)
            local_sdp.version += 1
            for stream in self.streams:
                local_sdp.media[stream.index] = stream.get_local_media(for_offer=True)
            self._invitation.send_reinvite(sdp=local_sdp)

            received_invitation_state = False
            received_sdp_update = False
            while not received_invitation_state or not received_sdp_update:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    received_sdp_update = True
                    if notification.data.succeeded:
                        local_sdp = notification.data.local_sdp
                        remote_sdp = notification.data.remote_sdp

                        for stream in self.streams:
                            stream.update(local_sdp, remote_sdp, stream.index)
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                        received_invitation_state = True
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='INVITE', code=notification.data.code, reason=notification.data.reason))
        except InvitationDidFailError, e:
            self.greenlet = None
            self.handle_notification(Notification('SIPInvitationChangedState', e.invitation, e.data))
        except SIPCoreError, e:
            raise #FIXME
        else:
            self.greenlet = None
            self.on_hold = True
            self.state = 'connected'
            hold_supported_streams = (stream for stream in self.streams if stream.hold_supported)
            notification_center.post_notification('SIPSessionDidChangeHoldState', self, TimestampedNotificationData(originator='local', on_hold=True, partial=any(not stream.on_hold_by_local for stream in hold_supported_streams)))
            for notification in unhandled_notifications:
                self.handle_notification(notification)

    def _send_unhold(self):
        self.state = 'sending_proposal'
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()

        unhandled_notifications = []

        try:
            local_sdp = SDPSession.new(self._invitation.sdp.active_local)
            local_sdp.version += 1
            for stream in self.streams:
                local_sdp.media[stream.index] = stream.get_local_media(for_offer=True)
            self._invitation.send_reinvite(sdp=local_sdp)

            received_invitation_state = False
            received_sdp_update = False
            while not received_invitation_state or not received_sdp_update:
                notification = self._channel.wait()
                if notification.name == 'SIPInvitationGotSDPUpdate':
                    received_sdp_update = True
                    if notification.data.succeeded:
                        local_sdp = notification.data.local_sdp
                        remote_sdp = notification.data.remote_sdp

                        for stream in self.streams:
                            stream.update(local_sdp, remote_sdp, stream.index)
                elif notification.name == 'SIPInvitationChangedState':
                    if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                        received_invitation_state = True
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='INVITE', code=notification.data.code, reason=notification.data.reason))
        except InvitationDidFailError, e:
            self.greenlet = None
            self.handle_notification(Notification('SIPInvitationChangedState', e.invitation, e.data))
        except SIPCoreError, e:
            raise #FIXME
        else:
            self.greenlet = None
            self.on_hold = False
            self.state = 'connected'
            notification_center.post_notification('SIPSessionDidChangeHoldState', self, TimestampedNotificationData(originator='local', on_hold=False, partial=False))
            for notification in unhandled_notifications:
                self.handle_notification(notification)

    def _fail(self, originator, code, reason, error):
        notification_center = NotificationCenter()
        prev_inv_state = self._invitation.state
        self.state = 'terminating'
        if prev_inv_state not in (None, 'incoming', 'outgoing', 'early', 'connecting'):
            notification_center.post_notification('SIPSessionWillEnd', self, TimestampedNotificationData(originator=originator))
        if self._invitation.state not in (None, 'disconnecting', 'disconnected'):
            try:
                if self._invitation.direction == 'incoming' and self._invitation.state in ('incoming', 'early'):
                    self._invitation.send_response(500)
                else:
                    self._invitation.end()
                with api.timeout(1):
                    while True:
                        notification = self._channel.wait()
                        if notification.name == 'SIPInvitationChangedState' and notification.data.state == 'disconnected':
                            if prev_inv_state in ('connecting', 'connected'):
                                notification_center.post_notification('SIPSessionDidProcessTransaction', self,
                                                                      TimestampedNotificationData(originator='local', method='BYE', code=notification.data.code, reason=notification.data.reason))
                            elif self._invitation.direction == 'incoming' and prev_inv_state in ('incoming', 'early'):
                                ack_received = notification.data.disconnect_reason != 'missing ACK'
                                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=500, reason=sip_status_messages[500], ack_received=ack_received))
                            elif self._invitation.direction == 'outgoing' and prev_inv_state in ('outgoing', 'early'):
                                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='INVITE', code=487, reason='Canceled'))
            except SIPCoreError:
                pass
            except api.TimeoutError:
                if prev_inv_state in ('connecting', 'connected'):
                    notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='local', method='BYE', code=408, reason=sip_status_messages[408]))
        notification_center.remove_observer(self, sender=self._invitation)
        self.state = 'terminated'
        if prev_inv_state in (None, 'incoming', 'outgoing', 'early', 'connecting'):
            if self._invitation.direction == 'incoming':
                code = code or 500
                reason = reason or sip_status_messages[500]
            notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator=originator, code=code, reason=reason, failure_reason=error))
        else:
            self.end_time = datetime.now()
            notification_center.post_notification('SIPSessionDidEnd', self, TimestampedNotificationData(originator=originator, end_reason=error))
        self.greenlet = None

    def _fail_proposal(self, originator, error):
        notification_center = NotificationCenter()
        for stream in self.proposed_streams:
            notification_center.remove_observer(self, sender=stream)
            stream.end()
        if originator == 'remote' and self._invitation.sub_state != 'normal':
            self._invitation.send_response(500)
            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=500, reason=sip_status_messages[500], ack_received='unknown'))
        notification_center.post_notification('SIPSessionHadProposalFailure', self, TimestampedNotificationData(originator=originator, failure_reaon=error, streams=self.proposed_streams))
        self.state = 'connected'
        self.proposed_streams = None
        self.greenlet = None

    @run_in_twisted
    def handle_notification(self, notification):
        if self.greenlet is None:
            self.greenlet = initial_greenlet = api.getcurrent()
        else:
            initial_greenlet = None
        try:
            handler = getattr(self, '_NH_%s' % notification.name, None)
            if handler is not None:
                handler(notification)
        finally:
            if self.greenlet is initial_greenlet:
                self.greenlet = None

    def _NH_SIPInvitationChangedState(self, notification):
        notification_center = NotificationCenter()
        if self.greenlet is not None and self.greenlet is not api.getcurrent():
            if notification.data.state == 'disconnected' and notification.data.prev_state != 'disconnecting':
                self._channel.send_exception(InvitationDidFailError(notification.sender, notification.data))
            else:
                self._channel.send(notification)
        else:
            if notification.data.state == 'connected' and notification.data.sub_state == 'received_proposal':
                self.state = 'received_proposal'
                try:
                    if self._invitation.sdp.proposed_remote.version > self._invitation.sdp.active_remote.version:
                        proposed_remote_sdp = self._invitation.sdp.proposed_remote
                        active_remote_sdp = self._invitation.sdp.active_remote
                        for stream in self.streams:
                            if not stream.validate_update(proposed_remote_sdp, stream.index):
                                engine = Engine()
                                self._invitation.send_response(488, extra_headers=[WarningHeader(399, engine.user_agent, 'Failed to update media stream index %d' % stream.index)])
                                self.state = 'connected'
                                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=488, reason=sip_status_messages[488], ack_received='unknown'))
                                return
                        for attr in ('user', 'net_type', 'address_type', 'address'):
                            if getattr(proposed_remote_sdp, attr) != getattr(active_remote_sdp, attr):
                                engine = Engine()
                                self._invitation.send_response(488, extra_headers=[WarningHeader(399, engine.user_agent, 'Difference in contents of o= line')])
                                self.state = 'connected'
                                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=488, reason=sip_status_messages[488], ack_received='unknown'))
                                return
                        added_media_indexes = set()
                        removed_media_indexes = set()
                        for index, media_stream in enumerate(proposed_remote_sdp.media):
                            if index >= len(active_remote_sdp.media):
                                added_media_indexes.add(index)
                            elif media_stream.media != active_remote_sdp.media[index].media:
                                added_media_indexes.add(index)
                                removed_media_indexes.add(index)
                            elif not media_stream.port and active_remote_sdp.media[index].port:
                                removed_media_indexes.add(index)
                        removed_media_indexes.update(xrange(len(proposed_remote_sdp.media), len(active_remote_sdp.media)))
                        if added_media_indexes and removed_media_indexes:
                            engine = Engine()
                            self._invitation.send_response(488, extra_headers=[WarningHeader(399, engine.user_agent, 'Both removing AND adding a media stream is currently not supported')])
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=488, reason=sip_status_messages[488], ack_received='unknown'))
                        elif added_media_indexes:
                            self.proposed_streams = []
                            for index in added_media_indexes:
                                media_stream = proposed_remote_sdp.media[index]
                                if media_stream.port != 0:
                                    stream = None
                                    if media_stream.media == 'audio':
                                        stream = AudioStream(self.account)
                                    elif media_stream.media == 'message' and 'file-selector' in (attr.name for attr in media_stream.attributes):
                                        stream = MSRPIncomingFileStream(self.account)
                                    elif media_stream.media == 'message':
                                        stream = MSRPChat(self.account)
                                    if stream is not None and stream.validate_incoming(proposed_remote_sdp, index):
                                        stream.index = index
                                        self.proposed_streams.append(stream)
                            if self.proposed_streams:
                                notification_center.post_notification('SIPSessionGotProposal', sender=self, data=TimestampedNotificationData(originator='remote', streams=self.proposed_streams))
                                return
                            else:
                                self._invitation.send_response(488)
                                notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=488, reason=sip_status_messages[488], ack_received='unknown'))
                        else:
                            local_sdp = SDPSession.new(self._invitation.sdp.active_local)
                            local_sdp.version += 1
                            removed_streams = [stream for stream in self.streams if stream.index in removed_media_indexes]
                            prev_on_hold_streams = set(stream for stream in self.streams if stream.hold_supported and stream.on_hold_by_remote)
                            for stream in removed_streams:
                                notification_center.remove_observer(self, sender=stream)
                                stream.end()
                                self.streams.remove(stream)
                                local_sdp.media[stream.index].port = 0
                            for stream in self.streams:
                                local_sdp.media[stream.index] = stream.get_local_media(for_offer=False)
                            self._invitation.send_response(200, sdp=local_sdp)
                            notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=200, reason=sip_status_messages[200], ack_received='unknown'))


                            received_invitation_state = False
                            received_sdp_update = False
                            while not received_sdp_update or not received_invitation_state:
                                notification = self._channel.wait()
                                if notification.name == 'SIPInvitationGotSDPUpdate':
                                    received_sdp_update = True
                                    if notification.data.succeeded:
                                        local_sdp = notification.data.local_sdp
                                        remote_sdp = notification.data.remote_sdp
                                        for stream in self.streams:
                                            stream.update(local_sdp, remote_sdp, stream.index)
                                elif notification.name == 'SIPInvitationChangedState':
                                    if notification.data.state == 'connected' and notification.data.sub_state == 'normal':
                                        received_invitation_state = True
                            on_hold_streams = set(stream for stream in self.streams if stream.hold_supported and stream.on_hold_by_remote)
                            if on_hold_streams != prev_on_hold_streams:
                                hold_supported_streams = (stream for stream in self.streams if stream.hold_supported)
                                notification_center.post_notification('SIPSessionDidChangeHoldState', self, TimestampedNotificationData(originator='remote', on_hold=bool(on_hold_streams),
                                                                      partial=bool(on_hold_streams) and any(not stream.on_hold_by_remote for stream in hold_supported_streams)))
                            if removed_media_indexes:
                                notification_center.post_notification('SIPSessionDidRenegotiateStreams', self, TimestampedNotificationData(originator='remote', action='remove', streams=removed_streams))
                    else:
                        self._invitation.send_response(200, sdp=self._invitation.sdp.active_local)
                except InvitationDidFailError, e:
                    self.greenlet = None
                    self.state == 'connected'
                    self.handle_notification(Notification('SIPInvitationChangedState', e.invitation, e.data))
                except SIPCoreError:
                    raise #FIXME
                else:
                    self.state = 'connected'
            elif notification.data.state == 'disconnected':
                if self.state == 'incoming':
                    self.state = 'terminated'
                    if notification.data.originator == 'remote':
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator='remote', method='INVITE', code=487, reason='Canceled', ack_received='unknown'))
                        notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='remote', code=487, reason='Canceled', failure_reason='user request'))
                    else:
                        # There must have been an error involved
                        notification_center.post_notification('SIPSessionDidFail', self, TimestampedNotificationData(originator='local', code=0, reason=None, failure_reason=notification.data.disconnect_reason))
                else:
                    notification_center.post_notification('SIPSessionWillEnd', self, TimestampedNotificationData(originator=notification.data.originator))
                    for stream in self.streams:
                        notification_center.remove_observer(self, sender=stream)
                        stream.end()
                    self.state = 'terminated'
                    if notification.data.originator == 'remote':
                        notification_center.post_notification('SIPSessionDidProcessTransaction', self, TimestampedNotificationData(originator=notification.data.originator, method=notification.data.method, code=200, reason=sip_status_messages[200]))
                    self.end_time = datetime.now()
                    notification_center.post_notification('SIPSessionDidEnd', self, TimestampedNotificationData(originator=notification.data.originator, end_reason=notification.data.disconnect_reason))

    def _NH_SIPInvitationGotSDPUpdate(self, notification):
        if self.greenlet is not None:
            self._channel.send(notification)

    def _NH_MediaStreamDidInitialize(self, notification):
        if self.greenlet is not None:
            self._channel.send(notification)

    def _NH_MediaStreamDidStart(self, notification):
        if self.greenlet is not None:
            self._channel.send(notification)

    def _NH_MediaStreamDidFail(self, notification):
        if self.greenlet is not None:
            self._channel.send_exception(MediaStreamDidFailError(notification.sender, notification.data))


class SessionManager(object):
    __metaclass__ = Singleton
    implements(IObserver)

    def __init__(self):
        self.sessions = []

    def start(self):
        notification_center = NotificationCenter()
        notification_center.add_observer(self, 'SIPInvitationChangedState')
        notification_center.add_observer(self, 'SIPSessionNewIncoming')
        notification_center.add_observer(self, 'SIPSessionNewOutgoing')
        notification_center.add_observer(self, 'SIPSessionDidFail')
        notification_center.add_observer(self, 'SIPSessionDidEnd')

    def handle_notification(self, notification):
        if notification.name == 'SIPInvitationChangedState' and notification.data.state == 'incoming':
            account_manager = AccountManager()
            account = account_manager.find_account(notification.data.request_uri)
            if account is None:
                notification.sender.send_response(404)
                return
            notification.sender.send_response(100)
            session = Session(account)
            session.init_incoming(notification.sender)
        elif notification.name in ('SIPSessionNewIncoming', 'SIPSessionNewOutgoing'):
            self.sessions.append(notification.sender)
        elif notification.name in ('SIPSessionDidFail', 'SIPSessionDidEnd'):
            self.sessions.remove(notification.sender)


