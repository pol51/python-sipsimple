from msrplib.connect import MSRPRelaySettings
from msrplib.protocol import URI

class MSRPIMSession:

    def __init__(self, outgoing,
                 relay=None,
                 from_=None,
                 accept_types=['message/cpim'],
                 accept_wrapped_types=['*']):
        """Initialize MSRPIMSession object.

        * 'outgoing' (bool) - whether you are an active endpoint or not;
        * 'relay' (MSRPRelaySettings) - if None, no relay is used;
        * 'from_' (SIPURI) - what to put in 'From' CPIM header;
        * 'accept_types' (list of strings) - to put in SDP media;
          MSRP transport will reject incoming chunks with an invalid media type;
        * 'accept_wrapped_types' (list of strings) - to put in SDP media;
          is not enforced by the transport.
        """
        self.outgoing = outgoing
        self.relay = None
        self.accept_types = accept_types
        self.accept_wrapped_types = accept_wrapped_types
        self._initialize()

    def _initialize(self, local_uri=None):
        """Initialize the MSRP connection; connect to the relay if necessary.
        When done, fire MSRPIMSessionDidInitialize (with 'sdpmedia' attribute,
        containing the appropriate 'SDPMedia' instance)

        * 'local_uri' -  URI instance, if provided passed to msrplib;
          allows customization of connection parameters; can be changed by
          msrplib to reflect the actual connection settings used; automatically
          generated by default.
        """
        raise NotImplementedError

    def cleanup(self):
        """Call me if initialize() was called but it's impossible to call start().
        This will close the connection or an opened port started by initialize().
        If start() was called, calling cleanup() is unnecessary.
        """
        raise NotImplementedError

    def start(self, remote_media):
        """Complete the MSRP connection establishment; this includes binding
        MSRP session.

        When done, fire MSRPIMSessionDidStart. At this point each incoming message
        is posted as a notification, MSRPIMSessionGotMessage, with the following
        attributes:
         * cpim_headers (dict)
         * msrp_headers (dict)
         * cpim_content (str) - the actual string that the remote user has typed
        """
        raise NotImplementedError

    def send_msrp_message(self, message, content_type):
        """Send raw MSRP message. For IM prefer send_message.
        """
        raise NotImplementedError

    def send_message(self,
                     message,
                     to,
                     content_type='text/plain',
                     dt=None):
        """Wrap message in Message/CPIM wrapper and send it to the other party.
        If called before the connection was established, the messages will be
        queued until MSRPIMSessionDidStart notification.

        * 'message' - str or unicode instance, content of the message;
        * 'to' - SIPURI instance, "To" header of CPIM wrapper;
        * 'content_type' - str instance, Content-Type of wrapped message;
          (Content-Type of MSRP message is always Message/CPIM in that case)
        * dt - datetime.datetime instance, "DateTime" header of CPIM wrapper;
          if None, datetime.now() is used.

        Return Message-ID (str), unique string identifying the message.

        The following headers are attached to each MSRP chunk:
        Failure-Report: partial
        Success-Report: yes

        For each send_message() call, MSRPIMSessionGotConfirmation will be issued
        upon receiving Success-Report/Failure-Report/Error transaction response.

        MSRPIMSessionGotConfirmation has the following attributes:

        * message_id (str) - Message-ID for which notification has been received.
        * succeeded (bool)
        * error (Exception subclass)
        """
        raise NotImplementedError

