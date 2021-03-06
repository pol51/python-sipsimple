# Copyright (C) 2009-2011 AG Projects. See LICENSE for details.
#

"""
Handling of MSRP media streams according to RFC4975, RFC4976, RFC5547
and RFC3994.

This module provides classes to parse and generate SDP related to SIP
sessions that negotiate Instant Messsaging, File Transfer and Screen
Sharing and handling of the actual media streams.
"""

__all__ = ['ChatStream', 'FileTransferStream', 'ScreenSharingStream', 'MSRPStreamError', 'ChatStreamError', 'VNCConnectionError', 'FileSelector', 'ScreenSharingHandler',
           'ScreenSharingServerHandler', 'ScreenSharingViewerHandler', 'InternalVNCViewerHandler', 'InternalVNCServerHandler', 'ExternalVNCViewerHandler', 'ExternalVNCServerHandler']

import os
import re
import random
import hashlib
import mimetypes

from abc import ABCMeta, abstractmethod, abstractproperty
from application.notification import NotificationCenter, NotificationData, IObserver
from application.python.descriptor import WriteOnceAttribute
from application.python.types import MarkerType
from application.system import host
from functools import partial
from itertools import chain
from twisted.internet.error import ConnectionDone
from zope.interface import implements

from eventlib import api
from eventlib.coros import queue
from eventlib.greenio import GreenSocket
from eventlib.proc import spawn, ProcExit
from eventlib.util import tcp_socket, set_reuse_addr
from msrplib.connect import DirectConnector, DirectAcceptor, RelayConnection, MSRPRelaySettings
from msrplib.protocol import URI, FailureReportHeader, SuccessReportHeader, ContentTypeHeader, UseNicknameHeader, parse_uri
from msrplib.session import MSRPSession, contains_mime_type, OutgoingFile
from msrplib.transport import make_response, make_report

from sipsimple.account import Account, BonjourAccount
from sipsimple.configuration.settings import SIPSimpleSettings
from sipsimple.core import SDPAttribute, SDPConnection, SDPMediaStream
from sipsimple.payloads.iscomposing import IsComposingDocument, State, LastActive, Refresh, ContentType
from sipsimple.streams import IMediaStream, MediaStreamType, StreamError, InvalidStreamError, UnknownStreamError
from sipsimple.streams.applications.chat import ChatIdentity, ChatMessage, CPIMMessage, CPIMParserError
from sipsimple.threading import run_in_twisted_thread
from sipsimple.threading.green import run_in_green_thread
from sipsimple.util import ISOTimestamp


class MSRPStreamError(StreamError): pass
class ChatStreamError(MSRPStreamError): pass

class VNCConnectionError(Exception): pass


class MSRPStreamBase(object):
    __metaclass__ = MediaStreamType

    implements(IMediaStream, IObserver)

    # Attributes that need to be defined by each MSRP stream type
    type = None
    priority = None
    use_msrp_session = False

    media_type = None
    accept_types = None
    accept_wrapped_types = None

    # These attributes are always False for any MSRP stream
    hold_supported = False
    on_hold = False
    on_hold_by_local = False
    on_hold_by_remote = False

    def __new__(cls, *args, **kw):
        if cls is MSRPStreamBase:
            raise TypeError("MSRPStreamBase cannot be instantiated directly")
        return object.__new__(cls)

    def __init__(self, direction='sendrecv'):
        self.direction = direction
        self.greenlet = None
        self.local_media = None
        self.remote_media = None
        self.msrp = None ## Placeholder for the MSRPTransport that will be set when started
        self.msrp_connector = None
        self.cpim_enabled = None ## Boolean value. None means it was not negotiated yet
        self.session = None
        self.msrp_session = None
        self.shutting_down = False
        self.local_role = None
        self.remote_role = None
        self.transport = None

        self._initialized = False
        self._done = False
        self._failure_reason = None

    @property
    def local_uri(self):
        return URI(host=host.default_ip, port=0, use_tls=self.transport=='tls', credentials=self.session.account.tls_credentials)

    def _create_local_media(self, uri_path):
        transport = "TCP/TLS/MSRP" if uri_path[-1].use_tls else "TCP/MSRP"
        attributes = [SDPAttribute("path", " ".join(str(uri) for uri in uri_path))]
        if self.direction not in [None, 'sendrecv']:
            attributes.append(SDPAttribute(self.direction, ''))
        if self.accept_types is not None:
            attributes.append(SDPAttribute("accept-types", " ".join(self.accept_types)))
        if self.accept_wrapped_types is not None:
            attributes.append(SDPAttribute("accept-wrapped-types", " ".join(self.accept_wrapped_types)))
        attributes.append(SDPAttribute("setup", self.local_role))
        local_ip = uri_path[-1].host
        connection = SDPConnection(local_ip)
        return SDPMediaStream(self.media_type, uri_path[-1].port or 12345, transport, connection=connection, formats=["*"], attributes=attributes)

    ## The public API (the IMediaStream interface)

    def get_local_media(self, remote_sdp=None, index=0):
        return self.local_media

    def new_from_sdp(self, session, remote_sdp, stream_index):
        raise NotImplementedError

    @run_in_green_thread
    def initialize(self, session, direction):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()
        notification_center.add_observer(self, sender=self)
        try:
            self.session = session
            self.transport = self.session.account.msrp.transport
            outgoing = direction=='outgoing'
            logger = NotificationProxyLogger()
            if self.session.account is BonjourAccount():
                if outgoing:
                    self.msrp_connector = DirectConnector(logger=logger)
                    self.local_role = 'active'
                else:
                    if self.transport=='tls' and None in (self.session.account.tls_credentials.cert, self.session.account.tls_credentials.key):
                        raise MSRPStreamError("Cannot accept MSRP connection without a TLS certificate")
                    self.msrp_connector = DirectAcceptor(logger=logger)
                    self.local_role = 'passive'
            else:
                if self.session.account.msrp.connection_model == 'relay':
                    if not outgoing and self.remote_role in ('actpass', 'passive'):
                        # 'passive' not allowed by the RFC but play nice for interoperability. -Saul
                        self.msrp_connector = DirectConnector(logger=logger, use_sessmatch=True)
                        self.local_role = 'active'
                    elif outgoing and not self.session.account.nat_traversal.use_msrp_relay_for_outbound:
                        self.msrp_connector = DirectConnector(logger=logger, use_sessmatch=True)
                        self.local_role = 'active'
                    else:
                        if self.session.account.nat_traversal.msrp_relay is None:
                            relay_host = relay_port = None
                        else:
                            if self.transport != self.session.account.nat_traversal.msrp_relay.transport:
                                raise MSRPStreamError("MSRP relay transport conflicts with MSRP transport setting")
                            relay_host = self.session.account.nat_traversal.msrp_relay.host
                            relay_port = self.session.account.nat_traversal.msrp_relay.port
                        relay = MSRPRelaySettings(domain=self.session.account.uri.host,
                                                  username=self.session.account.uri.user,
                                                  password=self.session.account.credentials.password,
                                                  host=relay_host,
                                                  port=relay_port,
                                                  use_tls=self.transport=='tls')
                        self.msrp_connector = RelayConnection(relay, 'passive', logger=logger, use_sessmatch=True)
                        self.local_role = 'actpass' if outgoing else 'passive'
                else:
                    if not outgoing and self.remote_role in ('actpass', 'passive'):
                        # 'passive' not allowed by the RFC but play nice for interoperability. -Saul
                        self.msrp_connector = DirectConnector(logger=logger, use_sessmatch=True)
                        self.local_role = 'active'
                    else:
                        if not outgoing and self.transport=='tls' and None in (self.session.account.tls_credentials.cert, self.session.account.tls_credentials.key):
                            raise MSRPStreamError("Cannot accept MSRP connection without a TLS certificate")
                        self.msrp_connector = DirectAcceptor(logger=logger, use_sessmatch=True)
                        self.local_role = 'actpass' if outgoing else 'passive'
            full_local_path = self.msrp_connector.prepare(self.local_uri)
            self.local_media = self._create_local_media(full_local_path)
        except Exception, e:
            notification_center.post_notification('MediaStreamDidNotInitialize', sender=self, data=NotificationData(reason=str(e)))
        else:
            self._initialized = True
            notification_center.post_notification('MediaStreamDidInitialize', sender=self)
        finally:
            self.greenlet = None

    @run_in_green_thread
    def start(self, local_sdp, remote_sdp, stream_index):
        self.greenlet = api.getcurrent()
        notification_center = NotificationCenter()
        try:
            context = 'sdp_negotiation'
            remote_media = remote_sdp.media[stream_index]
            self.remote_media = remote_media
            remote_accept_types = remote_media.attributes.getfirst('accept-types')
            # TODO: update accept_types and accept_wrapped_types from remote_media
            self.cpim_enabled = contains_mime_type(self.accept_types, 'message/cpim') and contains_mime_type(remote_accept_types.split(), 'message/cpim')
            remote_uri_path = remote_media.attributes.getfirst('path')
            if remote_uri_path is None:
                raise AttributeError("remote SDP media does not have 'path' attribute")
            full_remote_path = [parse_uri(uri) for uri in remote_uri_path.split()]
            remote_transport = 'tls' if full_remote_path[0].use_tls else 'tcp'
            if self.transport != remote_transport:
                raise MSRPStreamError("remote transport ('%s') different from local transport ('%s')" % (remote_transport, self.transport))
            if isinstance(self.session.account, Account) and self.local_role == 'actpass':
                remote_setup = remote_media.attributes.getfirst('setup', 'passive')
                if remote_setup == 'passive':
                    # If actpass is offered connectors are always started as passive
                    # We need to switch to active if the remote answers with passive
                    if self.session.account.msrp.connection_model == 'relay':
                        self.msrp_connector.mode = 'active'
                    else:
                        local_uri = self.msrp_connector.local_uri
                        logger = self.msrp_connector.logger
                        self.msrp_connector = DirectConnector(logger=logger, use_sessmatch=True)
                        self.msrp_connector.prepare(local_uri)
            context = 'start'
            self.msrp = self.msrp_connector.complete(full_remote_path)
            if self.use_msrp_session:
                self.msrp_session = MSRPSession(self.msrp, accept_types=self.accept_types, on_incoming_cb=self._handle_incoming, automatic_reports=False)
            self.msrp_connector = None
        except Exception, e:
            self._failure_reason = str(e)
            notification_center.post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context=context, reason=self._failure_reason))
        else:
            notification_center.post_notification('MediaStreamDidStart', sender=self)
        finally:
            self.greenlet = None

    def deactivate(self):
        self.shutting_down = True

    @run_in_green_thread
    def end(self):
        if not self._initialized or self._done:
            return
        self._done = True
        notification_center = NotificationCenter()
        notification_center.post_notification('MediaStreamWillEnd', sender=self)
        msrp = self.msrp
        msrp_session = self.msrp_session
        msrp_connector = self.msrp_connector
        try:
            if self.greenlet is not None:
                api.kill(self.greenlet)
            if msrp_session is not None:
                msrp_session.shutdown()
            elif msrp is not None:
                msrp.loseConnection(wait=False)
            if msrp_connector is not None:
                msrp_connector.cleanup()
        finally:
            notification_center.post_notification('MediaStreamDidEnd', sender=self, data=NotificationData(error=self._failure_reason))
            notification_center.remove_observer(self, sender=self)
            self.msrp = None
            self.msrp_session = None
            self.msrp_connector = None
            self.session = None

    def validate_update(self, remote_sdp, stream_index):
        return True #TODO

    def update(self, local_sdp, remote_sdp, stream_index):
        pass #TODO

    def hold(self):
        pass

    def unhold(self):
        pass

    def reset(self, stream_index):
        pass

    ## Internal IObserver interface

    def handle_notification(self, notification):
        handler = getattr(self, '_NH_%s' % notification.name, None)
        if handler is not None:
            handler(notification)

    ## Internal message handlers

    def _handle_incoming(self, chunk=None, error=None):
        notification_center = NotificationCenter()
        if error is not None:
            if self.shutting_down and isinstance(error.value, ConnectionDone):
                return
            self._failure_reason = error.getErrorMessage()
            notification_center.post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context='reading', reason=self._failure_reason))
        elif chunk is not None:
            method_handler = getattr(self, '_handle_%s' % chunk.method, None)
            if method_handler is not None:
                method_handler(chunk)

    def _handle_REPORT(self, chunk):
        pass

    def _handle_SEND(self, chunk):
        pass


class ChatStream(MSRPStreamBase):
    type = 'chat'
    priority = 1
    use_msrp_session = True

    media_type = 'message'
    accept_types = ['message/cpim', 'text/*', 'application/im-iscomposing+xml']
    accept_wrapped_types = ['*']

    def __init__(self, direction='sendrecv'):
        super(ChatStream, self).__init__(direction=direction)
        self.message_queue = queue()
        self.sent_messages = set()
        self.incoming_queue = {}

    @classmethod
    def new_from_sdp(cls, session, remote_sdp, stream_index):
        remote_stream = remote_sdp.media[stream_index]
        if remote_stream.media != 'message':
            raise UnknownStreamError
        expected_transport = 'TCP/TLS/MSRP' if session.account.msrp.transport=='tls' else 'TCP/MSRP'
        if remote_stream.transport != expected_transport:
            raise InvalidStreamError("expected %s transport in chat stream, got %s" % (expected_transport, remote_stream.transport))
        if remote_stream.formats != ['*']:
            raise InvalidStreamError("wrong format list specified")
        stream = cls()
        stream.remote_role = remote_stream.attributes.getfirst('setup', 'active')
        if (remote_stream.direction, stream.direction) not in (('sendrecv', 'sendrecv'), ('sendonly', 'recvonly'), ('recvonly', 'sendonly')):
            raise InvalidStreamError("mismatching directions in chat stream")
        remote_accept_types = remote_stream.attributes.getfirst('accept-types')
        if remote_accept_types is None:
            raise InvalidStreamError("remote SDP media does not have 'accept-types' attribute")
        if not any(contains_mime_type(cls.accept_types, mime_type) for mime_type in remote_accept_types.split()):
            raise InvalidStreamError("no compatible media types found")
        return stream

    @property
    def local_identity(self):
        try:
            return ChatIdentity(self.session.local_identity.uri, self.session.account.display_name)
        except AttributeError:
            return None

    @property
    def remote_identity(self):
        try:
            return ChatIdentity(self.session.remote_identity.uri, self.session.remote_identity.display_name)
        except AttributeError:
            return None

    @property
    def private_messages_allowed(self):
        try:
            return self.cpim_enabled and self.session.remote_focus and 'private-messages' in chain(*(attr.split() for attr in self.remote_media.attributes.getall('chatroom')))
        except AttributeError:
            return False

    @property
    def nickname_allowed(self):
        remote_chatroom_capabilities = chain(*(attr.split() for attr in self.remote_media.attributes.getall('chatroom')))
        try:
            return self.cpim_enabled and self.session.remote_focus and 'nickname' in remote_chatroom_capabilities
        except AttributeError:
            return False

    # TODO: chatroom, recvonly/sendonly (in start)?

    def _NH_MediaStreamDidStart(self, notification):
        spawn(self._message_queue_handler)

    def _NH_MediaStreamDidEnd(self, notification):
        self.message_queue.send_exception(ProcExit)

    def _handle_REPORT(self, chunk):
        # in theory, REPORT can come with Byte-Range which would limit the scope of the REPORT to the part of the message.
        if chunk.message_id in self.sent_messages:
            self.sent_messages.remove(chunk.message_id)
            notification_center = NotificationCenter()
            data = NotificationData(message_id=chunk.message_id, message=chunk, code=chunk.status.code, reason=chunk.status.comment)
            if chunk.status.code == 200:
                notification_center.post_notification('ChatStreamDidDeliverMessage', sender=self, data=data)
            else:
                notification_center.post_notification('ChatStreamDidNotDeliverMessage', sender=self, data=data)

    def _handle_SEND(self, chunk):
        if chunk.size == 0:
            # keep-alive
            self.msrp_session.send_report(chunk, 200, 'OK')
            return
        if self.direction=='sendonly':
            self.msrp_session.send_report(chunk, 413, 'Unwanted Message')
            return
        if chunk.segment is not None:
            self.incoming_queue.setdefault(chunk.message_id, []).append(chunk.data)
            if chunk.final:
                chunk.data = ''.join(self.incoming_queue.pop(chunk.message_id))
            else:
                self.msrp_session.send_report(chunk, 200, 'OK')
                return
        if chunk.content_type.lower() == 'message/cpim':
            try:
                message = CPIMMessage.parse(chunk.data)
            except CPIMParserError:
                self.msrp_session.send_report(chunk, 400, 'CPIM Parser Error')
                return
            else:
                if message.timestamp is None:
                    message.timestamp = ISOTimestamp.now()
                if message.sender is None:
                    message.sender = self.remote_identity
                private = self.session.remote_focus and len(message.recipients) == 1 and message.recipients[0] != self.remote_identity
        else:
            message = ChatMessage(chunk.data.decode('utf-8'), chunk.content_type, self.remote_identity, self.local_identity, ISOTimestamp.now())
            private = False
        # TODO: check wrapped content-type and issue a report if it's invalid
        self.msrp_session.send_report(chunk, 200, 'OK')
        notification_center = NotificationCenter()
        if message.content_type.lower() == IsComposingDocument.content_type:
            data = IsComposingDocument.parse(message.body)
            ndata = NotificationData(state=data.state.value,
                                     refresh=data.refresh.value if data.refresh is not None else 120,
                                     content_type=data.content_type.value if data.content_type is not None else None,
                                     last_active=data.last_active.value if data.last_active is not None else None,
                                     sender=message.sender, recipients=message.recipients, private=private)
            notification_center.post_notification('ChatStreamGotComposingIndication', sender=self, data=ndata)
        else:
            notification_center.post_notification('ChatStreamGotMessage', sender=self, data=NotificationData(message=message, private=private))

    def _on_transaction_response(self, message_id, response):
        if message_id in self.sent_messages and response.code != 200:
            self.sent_messages.remove(message_id)
            data = NotificationData(message_id=message_id, message=response, code=response.code, reason=response.comment)
            NotificationCenter().post_notification('ChatStreamDidNotDeliverMessage', sender=self, data=data)

    def _on_nickname_transaction_response(self, message_id, response):
        notification_center = NotificationCenter()
        if response.code == 200:
            notification_center.post_notification('ChatStreamDidSetNickname', sender=self, data=NotificationData(message_id=message_id, response=response))
        else:
            notification_center.post_notification('ChatStreamDidNotSetNickname', sender=self, data=NotificationData(message_id=message_id, message=response, code=response.code, reason=response.comment))

    def _message_queue_handler(self):
        notification_center = NotificationCenter()
        while True:
            message_id, message, content_type, failure_report, success_report, notify_progress = self.message_queue.wait()
            if self.msrp_session is None:
                # should we generate ChatStreamDidNotDeliver per each message in the queue here?
                break
            chunk = self.msrp_session.make_message(message, content_type=content_type, message_id=message_id)
            if failure_report is not None:
                chunk.add_header(FailureReportHeader(failure_report))
            if success_report is not None:
                chunk.add_header(SuccessReportHeader(success_report))
            try:
                self.msrp_session.send_chunk(chunk, response_cb=partial(self._on_transaction_response, message_id))
            except Exception, e:
                self._failure_reason = str(e)
                notification_center.post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context='sending', reason=self._failure_reason))
                break
            else:
                if notify_progress and success_report == 'yes' and failure_report != 'no':
                    self.sent_messages.add(message_id)
                    notification_center.post_notification('ChatStreamDidSendMessage', sender=self, data=NotificationData(message=chunk))

    @run_in_twisted_thread
    def _enqueue_message(self, message_id, message, content_type, failure_report=None, success_report=None, notify_progress=True):
        self.message_queue.send((message_id, message, content_type, failure_report, success_report, notify_progress))

    @run_in_green_thread
    def _set_local_nickname(self, nickname, message_id):
        if self.msrp_session is None:
            # should we generate ChatStreamDidNotSetNickname here?
            return
        chunk = self.msrp.make_chunk(method='NICKNAME', message_id=message_id)
        chunk.add_header(UseNicknameHeader(nickname or u''))
        try:
            self.msrp_session.send_chunk(chunk, response_cb=partial(self._on_nickname_transaction_response, message_id))
        except Exception, e:
            self._failure_reason = str(e)
            NotificationCenter().post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context='sending', reason=self._failure_reason))

    def send_message(self, content, content_type='text/plain', recipients=None, courtesy_recipients=None, subject=None, timestamp=None, required=None, additional_headers=None):
        """Send IM message. Prefer Message/CPIM wrapper if it is supported.
        If called before the connection was established, the messages will be
        queued until MediaStreamDidStart notification.

        - content (str) - content of the message;
        - remote_identity (CPIMIdentity) - "To" header of CPIM wrapper;
          if None, use the default obtained from the session
          'remote_identity' may only differ from the one obtained from the session if the remote
          party supports private messages. If it does not, ChatStreamError will be raised;
        - content_type (str) - Content-Type of wrapped message;
          (Content-Type of MSRP message is always Message/CPIM in that case)
          If Message/CPIM is not supported, Content-Type of MSRP message.

        Return generated MSRP chunk (MSRPData); to get Message-ID use its 'message_id' attribute.

        These MSRP headers are used to enable end-to-end success reports and
        to disable hop-to-hop successful responses:
        Failure-Report: partial
        Success-Report: yes
        """
        if self.direction=='recvonly':
            raise ChatStreamError('Cannot send message on recvonly stream')
        message_id = '%x' % random.getrandbits(64)
        if self.cpim_enabled:
            if not contains_mime_type(self.accept_wrapped_types, content_type):
                raise ChatStreamError('Invalid content_type for outgoing message: %r' % content_type)
            if not recipients:
                recipients = [self.remote_identity]
            elif not self.private_messages_allowed and recipients != [self.remote_identity]:
                raise ChatStreamError('The remote end does not support private messages')
            if timestamp is None:
                timestamp = ISOTimestamp.now()
            msg = CPIMMessage(content, content_type, sender=self.local_identity, recipients=recipients, courtesy_recipients=courtesy_recipients,
                              subject=subject, timestamp=timestamp, required=required, additional_headers=additional_headers)
            self._enqueue_message(message_id, str(msg), 'message/cpim', failure_report='yes', success_report='yes', notify_progress=True)
        else:
            if not contains_mime_type(self.accept_types, content_type):
                raise ChatStreamError('Invalid content_type for outgoing message: %r' % content_type)
            if recipients is not None and recipients != [self.remote_identity]:
                raise ChatStreamError('Private messages are not available, because CPIM wrapper is not used')
            if courtesy_recipients or subject or timestamp or required or additional_headers:
                raise ChatStreamError('Additional message meta-data cannot be sent, because CPIM wrapper is not used')
            if isinstance(content, unicode):
                content = content.encode('utf-8')
            self._enqueue_message(message_id, content, content_type, failure_report='yes', success_report='yes', notify_progress=True)
        return message_id

    def send_composing_indication(self, state, refresh=None, last_active=None, recipients=None):
        if self.direction == 'recvonly':
            raise ChatStreamError('Cannot send message on recvonly stream')
        if state not in ('active', 'idle'):
            raise ValueError('Invalid value for composing indication state')
        message_id = '%x' % random.getrandbits(64)
        content = IsComposingDocument.create(state=State(state), refresh=Refresh(refresh) if refresh is not None else None, last_active=LastActive(last_active) if last_active is not None else None, content_type=ContentType('text'))
        if self.cpim_enabled:
            if recipients is None:
                recipients = [self.remote_identity]
            elif not self.private_messages_allowed and recipients != [self.remote_identity]:
                raise ChatStreamError('The remote end does not support private messages')
            msg = CPIMMessage(content, IsComposingDocument.content_type, sender=self.local_identity, recipients=recipients, timestamp=ISOTimestamp.now())
            self._enqueue_message(message_id, str(msg), 'message/cpim', failure_report='partial', success_report='no')
        else:
            if recipients is not None and recipients != [self.remote_identity]:
                raise ChatStreamError('Private messages are not available, because CPIM wrapper is not used')
            self._enqueue_message(message_id, content, IsComposingDocument.content_type, failure_report='partial', success_report='no', notify_progress=False)
        return message_id

    def set_local_nickname(self, nickname):
        if not self.nickname_allowed:
            raise ChatStreamError('Setting nickname is not supported')
        message_id = '%x' % random.getrandbits(64)
        self._set_local_nickname(nickname, message_id)
        return message_id


# File transfer
#

class ComputeHash: __metaclass__ = MarkerType

class FileSelector(object):
    class __metaclass__(type):
        _name_re = re.compile('name:"([^"]+)"')
        _size_re = re.compile('size:(\d+)')
        _type_re = re.compile('type:([^ ]+)')
        _hash_re = re.compile('hash:([^ ]+)')
        _byte_re = re.compile('..')

    def __init__(self, name=None, type=None, size=None, hash=None, fd=None):
        ## If present, hash should be a sha1 object or a string in the form: sha-1:72:24:5F:E8:65:3D:DA:F3:71:36:2F:86:D4:71:91:3E:E4:A2:CE:2E
        ## According to the specification, only sha1 is supported ATM.
        self.name = name
        self.type = type
        self.size = size
        self.hash = hash
        self.fd = fd

    def _get_hash(self):
        return self.__dict__['hash']

    def _set_hash(self, value):
        if value is None:
            self.__dict__['hash'] = value
        elif isinstance(value, str) and value.startswith('sha1:'):
            self.__dict__['hash'] = value
        elif hasattr(value, 'hexdigest') and hasattr(value, 'name'):
            if value.name != 'sha1':
                raise TypeError("Invalid hash type: '%s'. Only sha1 hashes are supported" % value.name)
            # unexpected as it may be, using a regular expression is the fastest method to do this
            self.__dict__['hash'] = 'sha1:' + ':'.join(self.__class__._byte_re.findall(value.hexdigest().upper()))
        else:
            raise ValueError("Invalid hash value")

    hash = property(_get_hash, _set_hash)
    del _get_hash, _set_hash

    @classmethod
    def parse(cls, string):
        name_match = cls._name_re.search(string)
        size_match = cls._size_re.search(string)
        type_match = cls._type_re.search(string)
        hash_match = cls._hash_re.search(string)
        name = name_match and name_match.group(1)
        size = size_match and int(size_match.group(1))
        type = type_match and type_match.group(1)
        hash = hash_match and hash_match.group(1)
        return cls(name, type, size, hash)

    @classmethod
    def for_file(cls, path, type=None, hash=ComputeHash):
        fd = open(path, 'rb')
        name = os.path.basename(path)
        size = os.fstat(fd.fileno()).st_size
        if type is None:
            mime_type, encoding = mimetypes.guess_type(name)
            if encoding is not None:
                type = 'application/x-%s' % encoding
            elif mime_type is not None:
                type = mime_type
            else:
                type = 'application/octet-stream'
        if hash is ComputeHash:
            sha1 = hashlib.sha1()
            while True:
                content = fd.read(65536)
                if not content:
                    break
                sha1.update(content)
            fd.seek(0)
            # unexpected as it may be, using a regular expression is the fastest method to do this
            hash = 'sha1:' + ':'.join(cls._byte_re.findall(sha1.hexdigest().upper()))
        return cls(name, type, size, hash, fd)

    @property
    def sdp_repr(self):
        items = [('name', self.name and '"%s"' % self.name), ('type', self.type), ('size', self.size), ('hash', self.hash)]
        return ' '.join('%s:%s' % (name, value) for name, value in items if value is not None)


class FileTransferStream(MSRPStreamBase):
    type = 'file-transfer'
    priority = 10
    use_msrp_session = True

    media_type = 'message'
    accept_types = ['*']
    accept_wrapped_types = ['*']

    def __init__(self, file_selector, direction):
        if direction not in ('sendonly', 'recvonly'):
            raise ValueError("direction must be one of 'sendonly' or 'recvonly'")
        super(FileTransferStream, self).__init__(direction=direction)
        self.file_selector = file_selector

    @classmethod
    def new_from_sdp(cls, session, remote_sdp, stream_index):
        remote_stream = remote_sdp.media[stream_index]
        if remote_stream.media != 'message' or 'file-selector' not in remote_stream.attributes:
            raise UnknownStreamError
        expected_transport = 'TCP/TLS/MSRP' if session.account.msrp.transport=='tls' else 'TCP/MSRP'
        if remote_stream.transport != expected_transport:
            raise InvalidStreamError("expected %s transport in file transfer stream, got %s" % (expected_transport, remote_stream.transport))
        if remote_stream.formats != ['*']:
            raise InvalidStreamError("wrong format list specified")
        file_selector = FileSelector.parse(remote_stream.attributes.getfirst('file-selector'))
        if remote_stream.direction == 'sendonly':
            stream = cls(file_selector, 'recvonly')
        elif remote_stream.direction == 'recvonly':
            stream = cls(file_selector, 'sendonly')
        else:
            raise InvalidStreamError("wrong stream direction specified")
        stream.remote_role = remote_stream.attributes.getfirst('setup', 'active')
        return stream

    def initialize(self, session, direction):
        if self.direction == 'sendonly' and self.file_selector.fd is None:
            notification_center = NotificationCenter()
            notification_center.post_notification('MediaStreamDidNotInitialize', sender=self, data=NotificationData(reason='file descriptor not specified'))
            return
        super(FileTransferStream, self).initialize(session, direction)

    def _create_local_media(self, uri_path):
        local_media = super(FileTransferStream, self)._create_local_media(uri_path)
        local_media.attributes.append(SDPAttribute('file-selector', self.file_selector.sdp_repr))
        return local_media

    def _NH_MediaStreamDidStart(self, notification):
        if self.direction == 'sendonly':
            outgoing_file = OutgoingFile(self.file_selector.fd, self.file_selector.size, content_type=self.file_selector.type)
            outgoing_file.headers['Success-Report'] = SuccessReportHeader('yes')
            outgoing_file.headers['Failure-Report'] = FailureReportHeader('yes')
            self.msrp_session.send_file(outgoing_file)

    def _handle_REPORT(self, chunk):
        # in theory, REPORT can come with Byte-Range which would limit the scope of the REPORT to the part of the message.
        notification_center = NotificationCenter()
        data = NotificationData(message_id=chunk.message_id, chunk=chunk, code=chunk.status.code, reason=chunk.status.comment)
        if chunk.status.code == 200:
            # Calculating the number of bytes transferred so far by looking at the Byte-Range of this message
            # only works as long as chunks are delivered in order. -Luci
            data.transferred_bytes = chunk.byte_range[1]
            data.file_size = chunk.byte_range[2]
            notification_center.post_notification('FileTransferStreamDidDeliverChunk', sender=self, data=data)
            if data.transferred_bytes == data.file_size:
                notification_center.post_notification('FileTransferStreamDidFinish', sender=self)
        else:
            notification_center.post_notification('FileTransferStreamDidNotDeliverChunk', sender=self, data=data)

    def _handle_SEND(self, chunk):
        notification_center = NotificationCenter()
        if chunk.size == 0:
            # keep-alive
            self.msrp_session.send_report(chunk, 200, 'OK')
            return
        if self.direction=='sendonly':
            self.msrp_session.send_report(chunk, 413, 'Unwanted Message')
            return
        if chunk.content_type.lower() == 'message/cpim':
            # In order to properly support the CPIM wrapper, msrplib needs to be refactored. -Luci
            self.msrp_session.send_report(chunk, 415, 'Invalid Content-Type')
            self._failure_reason = "CPIM wrapper is not supported"
            notification_center.post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context='reading', reason=self._failure_reason))
            return
        self.msrp_session.send_report(chunk, 200, 'OK')
        # Calculating the number of bytes transferred so far by looking at the Byte-Range of this message
        # only works as long as chunks are delivered in order. -Luci
        ndata = NotificationData(content=chunk.data, content_type=chunk.content_type, transferred_bytes=chunk.byte_range[0]+chunk.size-1, file_size=chunk.byte_range[2])
        notification_center.post_notification('FileTransferStreamGotChunk', sender=self, data=ndata)
        if ndata.transferred_bytes == ndata.file_size:
            notification_center.post_notification('FileTransferStreamDidFinish', sender=self)


# Screen sharing
#

class ScreenSharingHandler(object):
    __metaclass__ = ABCMeta

    implements(IObserver)

    def __init__(self):
        self.incoming_msrp_queue = None
        self.outgoing_msrp_queue = None
        self.msrp_reader_thread = None
        self.msrp_writer_thread = None

    def initialize(self, stream):
        self.incoming_msrp_queue = stream.incoming_queue
        self.outgoing_msrp_queue = stream.outgoing_queue
        NotificationCenter().add_observer(self, sender=stream)

    @abstractproperty
    def type(self):
        raise NotImplementedError

    @abstractmethod
    def _msrp_reader(self):
        raise NotImplementedError

    @abstractmethod
    def _msrp_writer(self):
        raise NotImplementedError

    def handle_notification(self, notification):
        handler = getattr(self, '_NH_%s' % notification.name, None)
        if handler is not None:
            handler(notification)

    def _NH_MediaStreamDidStart(self, notification):
        self.msrp_reader_thread = spawn(self._msrp_reader)
        self.msrp_writer_thread = spawn(self._msrp_writer)

    def _NH_MediaStreamWillEnd(self, notification):
        notification.center.remove_observer(self, sender=notification.sender)
        if self.msrp_reader_thread is not None:
            self.msrp_reader_thread.kill()
            self.msrp_reader_thread = None
        if self.msrp_writer_thread is not None:
            self.msrp_writer_thread.kill()
            self.msrp_writer_thread = None


class ScreenSharingServerHandler(ScreenSharingHandler):
    type = property(lambda self: 'passive')


class ScreenSharingViewerHandler(ScreenSharingHandler):
    type = property(lambda self: 'active')



class InternalVNCViewerHandler(ScreenSharingViewerHandler):
    @run_in_twisted_thread
    def send(self, data):
        self.outgoing_msrp_queue.send(data)

    def _msrp_reader(self):
        notification_center = NotificationCenter()
        while True:
            data = self.incoming_msrp_queue.wait()
            notification_center.post_notification('ScreenSharingStreamGotData', sender=self, data=NotificationData(data=data))

    def _msrp_writer(self):
        pass


class InternalVNCServerHandler(ScreenSharingServerHandler):
    @run_in_twisted_thread
    def send(self, data):
        self.outgoing_msrp_queue.send(data)

    def _msrp_reader(self):
        notification_center = NotificationCenter()
        while True:
            data = self.incoming_msrp_queue.wait()
            notification_center.post_notification('ScreenSharingStreamGotData', sender=self, data=NotificationData(data=data))

    def _msrp_writer(self):
        pass


class ExternalVNCViewerHandler(ScreenSharingViewerHandler):
    address = ('localhost', 0)
    connect_timeout = 5

    def __init__(self):
        super(ExternalVNCViewerHandler, self).__init__()
        self.vnc_starter_thread = None
        self.vnc_socket = GreenSocket(tcp_socket())
        set_reuse_addr(self.vnc_socket)
        self.vnc_socket.settimeout(self.connect_timeout)
        self.vnc_socket.bind(self.address)
        self.vnc_socket.listen(1)
        self.address = self.vnc_socket.getsockname()

    def _msrp_reader(self):
        while True:
            try:
                data = self.incoming_msrp_queue.wait()
                self.vnc_socket.sendall(data)
            except Exception, e:
                self.msrp_reader_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
                NotificationCenter().post_notification('ScreenSharingHandlerDidFail', sender=self, data=NotificationData(context='sending', reason=str(e)))
                break

    def _msrp_writer(self):
        while True:
            try:
                data = self.vnc_socket.recv(2048)
                if not data:
                    raise VNCConnectionError("connection with the VNC viewer was closed")
                self.outgoing_msrp_queue.send(data)
            except Exception, e:
                self.msrp_writer_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
                NotificationCenter().post_notification('ScreenSharingHandlerDidFail', sender=self, data=NotificationData(context='reading', reason=str(e)))
                break

    def _start_vnc_connection(self):
        try:
            sock, addr = self.vnc_socket.accept()
            self.vnc_socket.close()
            self.vnc_socket = sock
            self.vnc_socket.settimeout(None)
        except Exception, e:
            self.vnc_starter_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
            NotificationCenter().post_notification('ScreenSharingHandlerDidFail', sender=self, data=NotificationData(context='connecting', reason=str(e)))
        else:
            self.msrp_reader_thread = spawn(self._msrp_reader)
            self.msrp_writer_thread = spawn(self._msrp_writer)
        finally:
            self.vnc_starter_thread = None

    def _NH_MediaStreamDidStart(self, notification):
        self.vnc_starter_thread = spawn(self._start_vnc_connection)

    def _NH_MediaStreamWillEnd(self, notification):
        if self.vnc_starter_thread is not None:
            self.vnc_starter_thread.kill()
            self.vnc_starter_thread = None
        super(ExternalVNCViewerHandler, self)._NH_MediaStreamWillEnd(notification)
        self.vnc_socket.close()


class ExternalVNCServerHandler(ScreenSharingServerHandler):
    address = ('localhost', 5900)
    connect_timeout = 5

    def __init__(self):
        super(ExternalVNCServerHandler, self).__init__()
        self.vnc_starter_thread = None
        self.vnc_socket = None

    def _msrp_reader(self):
        while True:
            try:
                data = self.incoming_msrp_queue.wait()
                self.vnc_socket.sendall(data)
            except Exception, e:
                self.msrp_reader_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
                NotificationCenter().post_notification('ScreenSharingHandlerDidFail', sender=self, data=NotificationData(context='sending', reason=str(e)))
                break

    def _msrp_writer(self):
        while True:
            try:
                data = self.vnc_socket.recv(2048)
                if not data:
                    raise VNCConnectionError("connection to the VNC server was closed")
                self.outgoing_msrp_queue.send(data)
            except Exception, e:
                self.msrp_writer_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
                NotificationCenter().post_notification('ScreenSharingHandlerDidFail', sender=self, data=NotificationData(context='reading', reason=str(e)))
                break

    def _start_vnc_connection(self):
        try:
            self.vnc_socket = GreenSocket(tcp_socket())
            self.vnc_socket.settimeout(self.connect_timeout)
            self.vnc_socket.connect(self.address)
            self.vnc_socket.settimeout(None)
        except Exception, e:
            self.vnc_starter_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
            NotificationCenter().post_notification('ScreenSharingHandlerDidFail', sender=self, data=NotificationData(context='connecting', reason=str(e)))
        else:
            self.msrp_reader_thread = spawn(self._msrp_reader)
            self.msrp_writer_thread = spawn(self._msrp_writer)
        finally:
            self.vnc_starter_thread = None

    def _NH_MediaStreamDidStart(self, notification):
        self.vnc_starter_thread = spawn(self._start_vnc_connection)

    def _NH_MediaStreamWillEnd(self, notification):
        if self.vnc_starter_thread is not None:
            self.vnc_starter_thread.kill()
            self.vnc_starter_thread = None
        super(ExternalVNCServerHandler, self)._NH_MediaStreamWillEnd(notification)
        if self.vnc_socket is not None:
            self.vnc_socket.close()


class ScreenSharingStream(MSRPStreamBase):
    type = 'screen-sharing'
    priority = 1
    use_msrp_session = False

    media_type = 'application'
    accept_types = ['application/x-rfb']
    accept_wrapped_types = None

    ServerHandler = InternalVNCServerHandler
    ViewerHandler = InternalVNCViewerHandler

    handler = WriteOnceAttribute()

    def __init__(self, mode):
        if mode not in ('viewer', 'server'):
            raise ValueError("mode should be 'viewer' or 'server' not '%s'" % mode)
        super(ScreenSharingStream, self).__init__(direction='sendrecv')
        self.handler = self.ViewerHandler() if mode=='viewer' else self.ServerHandler()
        self.incoming_queue = queue()
        self.outgoing_queue = queue()
        self.msrp_reader_thread = None
        self.msrp_writer_thread = None

    @classmethod
    def new_from_sdp(cls, session, remote_sdp, stream_index):
        remote_stream = remote_sdp.media[stream_index]
        if remote_stream.media != 'application':
            raise UnknownStreamError
        accept_types = remote_stream.attributes.getfirst('accept-types', None)
        if accept_types is None or 'application/x-rfb' not in accept_types.split():
            raise UnknownStreamError
        expected_transport = 'TCP/TLS/MSRP' if session.account.msrp.transport=='tls' else 'TCP/MSRP'
        if remote_stream.transport != expected_transport:
            raise InvalidStreamError("expected %s transport in chat stream, got %s" % (expected_transport, remote_stream.transport))
        if remote_stream.formats != ['*']:
            raise InvalidStreamError("wrong format list specified")
        remote_rfbsetup = remote_stream.attributes.getfirst('rfbsetup', 'active')
        if remote_rfbsetup == 'active':
            stream = cls(mode='server')
        elif remote_rfbsetup == 'passive':
            stream = cls(mode='viewer')
        else:
            raise InvalidStreamError("unknown rfbsetup attribute in the remote screen sharing stream")
        stream.remote_role = remote_stream.attributes.getfirst('setup', 'active')
        return stream

    def _create_local_media(self, uri_path):
        local_media = super(ScreenSharingStream, self)._create_local_media(uri_path)
        local_media.attributes.append(SDPAttribute('rfbsetup', self.handler.type))
        return local_media

    def _msrp_reader(self):
        while True:
            try:
                # it should be read_chunk(0) to read as much as available, but it doesn't work
                # as it sends 1-2 bytes more than provided by the app to the other side. -Dan
                chunk = self.msrp.read_chunk(None) # 0 means to return as much data as was read
                if chunk.method in (None, 'REPORT'):
                    continue
                elif chunk.method == 'SEND':
                    if chunk.content_type in self.accept_types:
                        self.incoming_queue.send(chunk.data)
                        response = make_response(chunk, 200, 'OK')
                        report = make_report(chunk, 200, 'OK')
                    else:
                        response = make_response(chunk, 415, 'Invalid Content-Type')
                        report = None
                else:
                    response = make_response(chunk, 501, 'Unknown method')
                    report = None
                if response is not None:
                    self.msrp.write_chunk(response)
                if report is not None:
                    self.msrp.write_chunk(report)
            except Exception, e:
                self.msrp_reader_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
                if self.shutting_down and isinstance(e, ConnectionDone):
                    break
                self._failure_reason = str(e)
                NotificationCenter().post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context='reading', reason=self._failure_reason))
                break

    def _msrp_writer(self):
        while True:
            try:
                data = self.outgoing_queue.wait()
                chunk = self.msrp.make_chunk(data=data)
                chunk.add_header(SuccessReportHeader('no'))
                chunk.add_header(FailureReportHeader('partial'))
                chunk.add_header(ContentTypeHeader('application/x-rfb'))
                self.msrp.write_chunk(chunk)
            except Exception, e:
                self.msrp_writer_thread = None # avoid issues caused by the notification handler killing this greenlet during post_notification
                if self.shutting_down and isinstance(e, ConnectionDone):
                    break
                self._failure_reason = str(e)
                NotificationCenter().post_notification('MediaStreamDidFail', sender=self, data=NotificationData(context='sending', reason=self._failure_reason))
                break

    def _NH_MediaStreamDidInitialize(self, notification):
        notification.center.add_observer(self, sender=self.handler)
        self.handler.initialize(self)

    def _NH_MediaStreamDidStart(self, notification):
        self.msrp_reader_thread = spawn(self._msrp_reader)
        self.msrp_writer_thread = spawn(self._msrp_writer)

    def _NH_MediaStreamWillEnd(self, notification):
        notification.center.remove_observer(self, sender=self.handler)
        if self.msrp_reader_thread is not None:
            self.msrp_reader_thread.kill()
            self.msrp_reader_thread = None
        if self.msrp_writer_thread is not None:
            self.msrp_writer_thread.kill()
            self.msrp_writer_thread = None

    def _NH_ScreenSharingHandlerDidFail(self, notification):
        self._failure_reason = notification.data.reason
        notification.center.post_notification('MediaStreamDidFail', sender=self, data=notification.data)


# temporary solution. to be replaced later by a better logging system in msrplib -Dan
class NotificationProxyLogger(object):
    def __init__(self):
        from application import log
        self.level = log.level
        self.stripped_data_transactions = set()
        self.text_transactions = set()
        self.transaction_data = {}
        self.notification_center = NotificationCenter()
        self.log_settings = SIPSimpleSettings().logs

    def report_out(self, data, transport, new_chunk=True):
        pass

    def report_in(self, data, transport, new_chunk=False, packet_done=False):
        pass

    def received_new_chunk(self, data, transport, chunk):
        content_type = chunk.content_type.split('/')[0].lower() if chunk.content_type else None
        if chunk.method != 'SEND' or (chunk.content_type and content_type in ('text', 'message')):
            self.text_transactions.add(chunk.transaction_id)
        self.transaction_data[chunk.transaction_id] = data

    def received_chunk_data(self, data, transport, transaction_id):
        if transaction_id in self.text_transactions:
            self.transaction_data[transaction_id] += data
        elif transaction_id not in self.stripped_data_transactions:
            self.transaction_data[transaction_id] += '<stripped data>'
            self.stripped_data_transactions.add(transaction_id)

    def received_chunk_end(self, data, transport, transaction_id):
        chunk = self.transaction_data.pop(transaction_id) + data
        self.stripped_data_transactions.discard(transaction_id)
        self.text_transactions.discard(transaction_id)
        if self.log_settings.trace_msrp:
            notification_data = NotificationData(direction='incoming', local_address=transport.getHost(), remote_address=transport.getPeer(), data=chunk)
            self.notification_center.post_notification('MSRPTransportTrace', sender=transport, data=notification_data)

    def sent_new_chunk(self, data, transport, chunk):
        content_type = chunk.content_type.split('/')[0].lower() if chunk.content_type else None
        if chunk.method != 'SEND' or (chunk.content_type and content_type in ('text', 'message')):
            self.text_transactions.add(chunk.transaction_id)
        self.transaction_data[chunk.transaction_id] = data

    def sent_chunk_data(self, data, transport, transaction_id):
        if transaction_id in self.text_transactions:
            self.transaction_data[transaction_id] += data
        elif transaction_id not in self.stripped_data_transactions:
            self.transaction_data[transaction_id] += '<stripped data>'
            self.stripped_data_transactions.add(transaction_id)

    def sent_chunk_end(self, data, transport, transaction_id):
        chunk = self.transaction_data.pop(transaction_id) + data
        self.stripped_data_transactions.discard(transaction_id)
        self.text_transactions.discard(transaction_id)
        if self.log_settings.trace_msrp:
            notification_data = NotificationData(direction='outgoing', local_address=transport.getHost(), remote_address=transport.getPeer(), data=chunk)
            self.notification_center.post_notification('MSRPTransportTrace', sender=transport, data=notification_data)

    def debug(self, message, **context):
        pass

    def info(self, message, **context):
        if self.log_settings.trace_msrp:
            self.notification_center.post_notification('MSRPLibraryLog', data=NotificationData(message=message, level=self.level.INFO))
    msg = info

    def warn(self, message, **context):
        if self.log_settings.trace_msrp:
            self.notification_center.post_notification('MSRPLibraryLog', data=NotificationData(message=message, level=self.level.WARNING))

    def error(self, message, **context):
        if self.log_settings.trace_msrp:
            self.notification_center.post_notification('MSRPLibraryLog', data=NotificationData(message=message, level=self.level.ERROR))
    err = error

    def fatal(self, message, **context):
        if self.log_settings.trace_msrp:
            self.notification_center.post_notification('MSRPLibraryLog', data=NotificationData(message=message, level=self.level.CRITICAL))

