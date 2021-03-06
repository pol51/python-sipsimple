# Copyright (C) 2008-2011 AG Projects. See LICENSE for details.
#

# This module is partially broken. It breaks the core assumption of the
# payloads infrastructure, that an element qname is unique inside a given
# application. Fortunately, the elements with duplicate qnames are used
# as child elements for other elements, which are not affected by the
# problem as each element keeps it's own qname mapping for its children
# qnames. The problem only affects different elements with the same qname
# that are used in list elements, as currently the list element uses the
# application's qname mapping to find the classes and that mapping is
# broken when multiple elements with the same qname are defined.
# In other words, this module works, but the application qname mapping
# that is generated by it is broken.
#
# -Dan

"""
User Agent Capability Extension handling according to RFC5196

This module provides an extension to PIDF to describe a user-agent
capabilities in the PIDF documents.
"""


__all__ = ['namespace',
           'Audio',
           'Application',
           'Data',
           'Control',
           'Video',
           'Video',
           'Text',
           'Message',
           'Type',
           'Automata',
           'Class',
           'Duplex',
           'Description',
           'EventPackages',
           'Priority',
           'Methods',
           'Extensions',
           'Scheme',
           'Schemes',
           'Actor',
           'IsFocus',
           'Languages',
           'Language',
           'ServiceCapabilities',
           'Mobility',
           'DeviceCapabilities',
           'ServiceCapabilitiesExtension',
           'EventPackagesExtension',
           'PriorityExtension',
           'MethodsExtension',
           'ExtensionsExtension',
           'DeviceCapabilitiesExtension',
           'MobilityExtension',
           # Extensions
           'FileTransfer',
           'ScreenSharingServer',
           'ScreenSharingClient']


from sipsimple.payloads import XMLStringElement, XMLLocalizedStringElement, XMLBooleanElement, XMLElement, XMLEmptyElement
from sipsimple.payloads import XMLElementChild, XMLListElement, XMLStringListElement, XMLAttribute, XMLEmptyElementRegistryType
from sipsimple.payloads.pidf import PIDFDocument, ServiceExtension, Service, DeviceExtension, Device


namespace = "urn:ietf:params:xml:ns:pidf:caps"
PIDFDocument.register_namespace(namespace, prefix='caps', schema='caps.xsd')



# Marker mixins
class EventPackagesExtension(object): pass
class PriorityExtension(object): pass
class MethodsExtension(object): pass
class ExtensionsExtension(object): pass
class MobilityExtension(object): pass
class DeviceCapabilitiesExtension(object): pass
class ServiceCapabilitiesExtension(object): pass


class ContentTypeValue(str):
    def __new__(cls, value):
        if len(value.split('/')) != 2:
            raise ValueError("illegal value for Content-Type: %s" % value)
        return str.__new__(cls, value)


class Audio(XMLBooleanElement):
    _xml_tag = 'audio'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Application(XMLBooleanElement):
    _xml_tag = 'application'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Data(XMLBooleanElement):
    _xml_tag = 'data'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Control(XMLBooleanElement):
    _xml_tag = 'control'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Video(XMLBooleanElement):
    _xml_tag = 'video'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Text(XMLBooleanElement):
    _xml_tag = 'text'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Message(XMLBooleanElement):
    _xml_tag = 'message'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Automata(XMLBooleanElement):
    _xml_tag = 'automata'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class Type(XMLStringElement):
    _xml_tag = 'type'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_value_type = ContentTypeValue


class ClassRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('business', 'personal')


class ClassSupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = ClassRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class ClassNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = ClassRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Class(XMLElement):
    _xml_tag = 'class'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    supported = XMLElementChild('supported', type=ClassSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=ClassNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class DuplexRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('full', 'half', 'receive-only', 'send-only')


class DuplexSupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = DuplexRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class DuplexNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = DuplexRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Duplex(XMLElement):
    _xml_tag = 'duplex'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    supported = XMLElementChild('supported', type=DuplexSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=DuplexNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class EventRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('conference', 'dialog', 'kpml', 'message-summary', 'poc-settings',
             'presence', 'reg', 'refer', 'Siemens-RTP-Stats', 'spirits-INDPs',
             'spirits-user-prof', 'winfo')


class EventSupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = EventRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class EventNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = EventRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class EventPackages(XMLElement):
    _xml_tag = 'event-packages'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = EventPackagesExtension

    supported = XMLElementChild('supported', type=EventSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=EventNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class PriorityLowerthan(XMLEmptyElement):
    _xml_tag = 'lowerthan'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    maxvalue = XMLAttribute('maxvalue', type=int, required=True, test_equal=True)

    def __init__(self, maxvalue):
        XMLEmptyElement.__init__(self)
        self.maxvalue = maxvalue


class PriorityHigherthan(XMLEmptyElement):
    _xml_tag = 'higherthan'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    minvalue = XMLAttribute('minvalue', type=int, required=True, test_equal=True)

    def __init__(self, minvalue):
        XMLEmptyElement.__init__(self)
        self.minvalue = minvalue


class PriorityEquals(XMLEmptyElement):
    _xml_tag = 'equals'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    value = XMLAttribute('value', type=int, required=True, test_equal=True)

    def __init__(self, value):
        XMLEmptyElement.__init__(self)
        self.value = value


class PriorityRange(XMLEmptyElement):
    _xml_tag = 'range'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    maxvalue = XMLAttribute('maxvalue', type=int, required=True, test_equal=True)
    minvalue = XMLAttribute('minvalue', type=int, required=True, test_equal=True)

    def __init__(self, maxvalue, minvalue):
        XMLEmptyElement.__init__(self)
        self.maxvalue = maxvalue
        self.minvalue = minvalue


class PrioritySupported(XMLListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_type = (PriorityLowerthan, PriorityHigherthan, PriorityEquals, PriorityRange)

    def __init__(self, supported=[]):
        XMLListElement.__init__(self)
        self.update(supported)


class PriorityNotSupported(XMLListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_type = (PriorityLowerthan, PriorityHigherthan, PriorityEquals, PriorityRange)

    def __init__(self, not_supported=[]):
        XMLListElement.__init__(self)
        self.update(not_supported)


class Priority(XMLElement):
    _xml_tag = 'priority'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = PriorityExtension

    supported = XMLElementChild('supported', type=PrioritySupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=PriorityNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class MethodRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('ACK', 'BYE', 'CANCEL', 'INFO', 'INVITE', 'MESSAGE',
             'NOTIFY', 'OPTIONS', 'PRACK', 'PUBLISH', 'REFER',
             'REGISTER', 'SUBSCRIBE', 'UPDATE')


class MethodSupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = MethodRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class MethodNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = MethodRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Methods(XMLElement):
    _xml_tag = 'methods'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = MethodsExtension

    supported = XMLElementChild('supported', type=MethodSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=MethodNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class ExtensionRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('rel100', 'early-session', 'eventlist', 'from-change', 'gruu',
             'histinfo', 'join', 'norefsub', 'path', 'precondition', 'pref',
             'privacy', 'recipient-list-invite', 'recipient-list-subscribe',
             'replaces', 'resource-priority', 'sdp-anat', 'sec-agree',
             'tdialog', 'timer')


class ExtensionSupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = ExtensionRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class ExtensionNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = ExtensionRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Extensions(XMLElement):
    _xml_tag = 'extensions'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = ExtensionsExtension

    supported = XMLElementChild('supported', type=ExtensionSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=ExtensionNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class Scheme(XMLStringElement):
    _xml_tag = 's'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class SchemeSupported(XMLListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_type = Scheme

    def __init__(self, supported=[]):
        XMLListElement.__init__(self)
        self.update(supported)


class SchemeNotSupported(XMLListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_type = Scheme

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Schemes(XMLElement):
    _xml_tag = 'schemes'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    supported = XMLElementChild('supported', type=SchemeSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=SchemeNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class ActorRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('principal', 'attendant', 'msg-taker', 'information')


class ActorSupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = ActorRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class ActorNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = ActorRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Actor(XMLElement):
    _xml_tag = 'actor'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    supported = XMLElementChild('supported', type=ActorSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=ActorNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class Language(XMLStringElement):
    _xml_tag = 'l'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class LanguageSupported(XMLListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_type = Language

    def __init__(self, supported=[]):
        XMLListElement.__init__(self)
        self.update(supported)

    def __iter__(self):
        return (unicode(item) for item in super(LanguageSupported, self).__iter__())

    def add(self, item):
        if isinstance(item, basestring):
            item = Language(item)
        super(LanguageSupported, self).add(item)

    def remove(self, item):
        if isinstance(item, basestring):
            try:
                item = (entry for entry in super(LanguageSupported, self).__iter__() if entry == item).next()
            except StopIteration:
                raise KeyError(item)
        super(LanguageSupported, self).remove(item)


class LanguageNotSupported(XMLListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_type = Language

    def __init__(self, not_supported=[]):
        XMLListElement.__init__(self)
        self.update(not_supported)

    def __iter__(self):
        return (unicode(item) for item in super(LanguageNotSupported, self).__iter__())

    def add(self, item):
        if isinstance(item, basestring):
            item = Language(item)
        super(LanguageNotSupported, self).add(item)

    def remove(self, item):
        if isinstance(item, basestring):
            try:
                item = (entry for entry in super(LanguageNotSupported, self).__iter__() if entry == item).next()
            except StopIteration:
                raise KeyError(item)
        super(LanguageNotSupported, self).remove(item)


class Languages(XMLElement):
    _xml_tag = 'languages'
    _xml_namespace = namespace
    _xml_document = PIDFDocument

    supported = XMLElementChild('supported', type=LanguageSupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=LanguageNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported
        self.not_supported = not_supported


class Description(XMLLocalizedStringElement):
    _xml_tag = 'description'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class IsFocus(XMLBooleanElement):
    _xml_tag = 'isfocus'
    _xml_namespace = namespace
    _xml_document = PIDFDocument


class ServiceCapabilities(XMLListElement, ServiceExtension):
    _xml_tag = 'servcaps'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = ServiceCapabilitiesExtension
    _xml_item_type = Description
    _xml_children_order = {Actor.qname: 0,
                           Application.qname: 1,
                           Audio.qname: 2,
                           Automata.qname: 3,
                           Class.qname: 4,
                           Control.qname: 5,
                           Data.qname: 6,
                           Description.qname: 7,
                           Duplex.qname: 8,
                           EventPackages.qname: 9,
                           Extensions.qname: 10,
                           IsFocus.qname: 11,
                           Message.qname: 12,
                           Methods.qname: 13,
                           Languages.qname: 14,
                           Priority.qname: 15,
                           Schemes.qname: 16,
                           Text.qname: 17,
                           Type.qname: 18,
                           Video.qname: 19,
                           None: 20}

    audio = XMLElementChild('audio', type=Audio, required=False, test_equal=True)
    application = XMLElementChild('application', type=Application, required=False, test_equal=True)
    data = XMLElementChild('data', type=Data, required=False, test_equal=True)
    control = XMLElementChild('control', type=Control, required=False, test_equal=True)
    video = XMLElementChild('video', type=Video, required=False, test_equal=True)
    text = XMLElementChild('text', type=Text, required=False, test_equal=True)
    message = XMLElementChild('message', type=Message, required=False, test_equal=True)
    mime_type = XMLElementChild('mime_type', type=Type, required=False, test_equal=True)
    automata = XMLElementChild('automata', type=Automata, required=False, test_equal=True)
    communication_class = XMLElementChild('communication_class', type=Class, required=False, test_equal=True)
    duplex = XMLElementChild('duplex', type=Duplex, required=False, test_equal=True)
    event_packages = XMLElementChild('event_packages', type=EventPackages, required=False, test_equal=True)
    priority = XMLElementChild('priority', type=Priority, required=False, test_equal=True)
    methods = XMLElementChild('methods', type=Methods, required=False, test_equal=True)
    extensions = XMLElementChild('extensions', type=Extensions, required=False, test_equal=True)
    schemes = XMLElementChild('schemes', type=Schemes, required=False, test_equal=True)
    actor = XMLElementChild('actor', type=Actor, required=False, test_equal=True)
    is_focus = XMLElementChild('is_focus', type=IsFocus, required=False, test_equal=True)
    languages = XMLElementChild('languages', type=Languages, required=False, test_equal=True)

    def __init__(self, audio=None, application=None, data=None, control=None, video=None, text=None, message=None, mime_type=None, automata=None, communication_class=None, duplex=None, event_packages=None, priority=None, methods=None, extensions=None, schemes=None, actor=None, is_focus=None, languages=None, descriptions=[]):
        XMLListElement.__init__(self)
        self.audio = audio
        self.application = application
        self.data = data
        self.control = control
        self.video = video
        self.text = text
        self.message = message
        self.mime_type = mime_type
        self.automata = automata
        self.communication_class = communication_class
        self.duplex = duplex
        self.event_packages = event_packages
        self.priority = priority
        self.methods = methods
        self.extensions = extensions
        self.schemes = schemes
        self.actor = actor
        self.is_focus = is_focus
        self.languages = languages
        self.update(descriptions)

Service.register_extension('capabilities', type=ServiceCapabilities)


class MobilityRegistry(object):
    __metaclass__ = XMLEmptyElementRegistryType

    _xml_namespace = namespace
    _xml_document = PIDFDocument

    names = ('fixed', 'mobile')


class MobilitySupported(XMLStringListElement):
    _xml_tag = 'supported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = MobilityRegistry

    def __init__(self, supported=[]):
        XMLStringListElement.__init__(self)
        self.update(supported)


class MobilityNotSupported(XMLStringListElement):
    _xml_tag = 'notsupported'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_item_registry = MobilityRegistry

    def __init__(self, not_supported=[]):
        XMLStringListElement.__init__(self)
        self.update(not_supported)


class Mobility(XMLElement):
    _xml_tag = 'mobility'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = MobilityExtension

    supported = XMLElementChild('supported', type=MobilitySupported, required=False, test_equal=True)
    not_supported = XMLElementChild('not_supported', type=MobilityNotSupported, required=False, test_equal=True)

    def __init__(self, supported=None, not_supported=None):
        XMLElement.__init__(self)
        self.supported = supported()
        self.not_supported = not_supported


class DeviceCapabilities(XMLListElement, DeviceExtension):
    _xml_tag = 'devcaps'
    _xml_namespace = namespace
    _xml_document = PIDFDocument
    _xml_extension_type = DeviceCapabilitiesExtension
    _xml_item_type = Description

    mobility = XMLElementChild('mobility', type=Mobility, required=False, test_equal=True)

    def __init__(self, mobility=None, descriptions=[]):
        XMLListElement.__init__(self)
        self.mobility = mobility
        self.update(descriptions)

    def __repr__(self):
        return "%s(%r, %r)" % (self.__class__.__name__, self.mobility, list(self))

Device.register_extension('capabilities', type=DeviceCapabilities)


#
# Extensions
#

agp_caps_namespace = 'urn:ag-projects:xml:ns:pidf:caps'
PIDFDocument.register_namespace(agp_caps_namespace, prefix='agp-caps')

class FileTransfer(XMLBooleanElement, ServiceCapabilitiesExtension):
    _xml_tag = 'file-transfer'
    _xml_namespace = agp_caps_namespace
    _xml_document = PIDFDocument

class ScreenSharingServer(XMLBooleanElement, ServiceCapabilitiesExtension):
    _xml_tag = 'screen-sharing-server'
    _xml_namespace = agp_caps_namespace
    _xml_document = PIDFDocument

class ScreenSharingClient(XMLBooleanElement, ServiceCapabilitiesExtension):
    _xml_tag = 'screen-sharing-client'
    _xml_namespace = agp_caps_namespace
    _xml_document = PIDFDocument

ServiceCapabilities.register_extension('file_transfer', type=FileTransfer)
ServiceCapabilities.register_extension('screen_sharing_server', type=ScreenSharingServer)
ServiceCapabilities.register_extension('screen_sharing_client', type=ScreenSharingClient)


