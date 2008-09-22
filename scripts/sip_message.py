#!/usr/bin/env python

import sys
import re
import traceback
import os
import signal
import random
from thread import start_new_thread, allocate_lock
from Queue import Queue
from optparse import OptionParser, OptionValueError
import dns.resolver
from application.configuration import *
from application.process import process
from pypjua import *

re_host_port = re.compile("^(?P<host>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(:(?P<port>\d+))?$")
class SIPProxyAddress(tuple):
    def __new__(typ, value):
        match = re_host_port.search(value)
        if match is None:
            raise ValueError("invalid IP address/port: %r" % value)
        if match.group("port") is None:
            port = 5060
        else:
            port = match.group("port")
            if port > 65535:
                raise ValueError("port is out of range: %d" % port)
        return match.group("host"), port


class AccountConfig(ConfigSection):
    _datatypes = {"username": str, "domain": str, "password": str, "display_name": str, "outbound_proxy": SIPProxyAddress}
    username = None
    domain = None
    password = None
    display_name = None
    outbound_proxy = None, None


process._system_config_directory = os.path.expanduser("~")
configuration = ConfigFile("pypjua.ini")
configuration.read_settings("Account", AccountConfig)

queue = Queue()
packet_count = 0
start_time = None
user_quit = True
lock = allocate_lock()

def event_handler(event_name, **kwargs):
    global start_time, packet_count, queue, pjsip_logging
    if event_name == "siptrace":
        if start_time is None:
            start_time = kwargs["timestamp"]
        packet_count += 1
        if kwargs["received"]:
            direction = "RECEIVED"
        else:
            direction = "SENDING"
        buf = ["%s: Packet %d, +%s" % (direction, packet_count, (kwargs["timestamp"] - start_time))]
        buf.append("%(timestamp)s: %(source_ip)s:%(source_port)d --> %(destination_ip)s:%(destination_port)d" % kwargs)
        buf.append(kwargs["data"])
        queue.put(("print", "\n".join(buf)))
    elif event_name != "log":
        queue.put(("pypjua_event", (event_name, kwargs)))
    elif pjsip_logging:
        queue.put(("print", "%(timestamp)s (%(level)d) %(sender)14s: %(message)s" % kwargs))

def read_queue(e, username, domain, password, display_name, proxy_ip, proxy_port, target_username, target_domain, do_siptrace, message, pjsip_logging):
    global user_quit, lock, queue
    lock.acquire()
    printed = False
    sent = False
    msg_buf = []
    try:
        if proxy_ip is None:
            # for now assume 1 SRV record and more than one A record
            srv_answers = dns.resolver.query("_sip._udp.%s" % domain, "SRV")
            a_answers = dns.resolver.query(str(srv_answers[0].target), "A")
            route = Route(random.choice(a_answers).address, srv_answers[0].port)
        else:
            route = Route(proxy_ip, proxy_port)
        credentials = Credentials(SIPURI(user=username, host=domain, display=display_name), password)
        if target_username is None:
            reg = Registration(credentials, route=route)
            print 'Registering for SIP address "%s" at proxy %s:%d and waiting for MESSAGE request' % (credentials.uri, route.host, route.port)
            reg.register()
        else:
            to_uri = SIPURI(user=target_username, host=target_domain)
            if message is None:
                print "Press Ctrl+D on an empty line to end input and send the MESSAGE request."
            else:
                msg_buf.append(message)
                queue.put(("eof", None))
        while True:
            command, data = queue.get()
            if command == "print":
                print data
            if command == "pypjua_event":
                event_name, args = data
                if event_name == "Registration_state":
                    if args["state"] == "registered":
                        if not printed:
                            print "REGISTER was succesfull"
                            print "Contact: %s (expires in %d seconds)" % (args["contact_uri"], args["expires"])
                            if len(args["contact_uri_list"]) > 1:
                                print "Other registered contacts:\n%s" % "\n".join(["%s (expires in %d seconds)" % contact_tup for contact_tup in args["contact_uri_list"] if contact_tup[0] != args["contact_uri"]])
                            print "Press Ctrl+D to stop the program."
                            printed = True
                    elif args["state"] == "unregistered":
                        if args["code"] / 100 != 2:
                            print "Unregistered: %(code)d %(reason)s" % args
                        user_quit = False
                        command = "quit"
                elif event_name == "Invitation_state":
                    if args["state"] == "INCOMING":
                        args["obj"].end()
                elif event_name == "message":
                    print 'Received MESSAGE from "%(from_uri)s", Content-Type: %(content_type)s/%(content_subtype)s' % args
                    print args["body"]
                elif event_name == "message_response":
                    if args["code"] / 100 != 2:
                        print "Could not deliver MESSAGE: %(code)d %(reason)s" % args
                    else:
                        print "MESSAGE was accepted by remote party."
                    user_quit = False
                    command = "quit"
            if command == "user_input":
                if not sent:
                    msg_buf.append(data)
            if command == "eof":
                if target_username is None:
                    reg.unregister()
                elif not sent:
                    sent = True
                    print 'Sending MESSAGE from "%s" to "%s" using proxy %s:%d' % (credentials.uri, to_uri, route.host, route.port)
                    send_message(credentials, SIPURI(user=target_username, host=target_domain), "text", "plain", "\n".join(msg_buf), route)
            if command == "quit":
                break
    except:
        user_quit = False
        traceback.print_exc()
    finally:
        e.stop()
        if not user_quit:
            os.kill(os.getpid(), signal.SIGINT)
        lock.release()

def do_message(**kwargs):
    global user_quit, lock, queue, pjsip_logging
    print "Using configuration file %s" % process.config_file("pypjua.ini")
    pjsip_logging = kwargs["pjsip_logging"]
    ctrl_d_pressed = False
    e = Engine(event_handler, do_siptrace=kwargs["do_siptrace"], auto_sound=False)
    e.start()
    start_new_thread(read_queue, (e,), kwargs)
    try:
        while True:
            try:
                msg = raw_input()
                queue.put(("user_input", msg))
            except EOFError:
                if not ctrl_d_pressed:
                    queue.put(("eof", None))
                    ctrl_d_pressed = True
    except KeyboardInterrupt:
        if user_quit:
            print "Ctrl+C pressed, exiting instantly!"
            queue.put(("quit", True))
        lock.acquire()
        return

def parse_host_port(option, opt_str, value, parser, host_name, port_name, default_port):
    match = re_host_port.match(value)
    if match is None:
        raise OptionValueError("Could not parse supplied address: %s" % value)
    setattr(parser.values, host_name, match.group("host"))
    if match.group("port") is None:
        setattr(parser.values, port_name, default_port)
    else:
        setattr(parser.values, port_name, int(match.group("port")))

def parse_options():
    retval = {}
    description = "This example script will either REGISTER using the specified credentials and sit idle waiting for an incoming MESSAGE request, or attempt to send a MESSAGE request to the specified target. In outgoing mode the program will read the contents of the messages to be sent from standard input, Ctrl+D signalling EOF as usual. In listen mode the program will quit when Ctrl+D is pressed."
    usage = "%prog [options] [target-user@target-domain.com]"
    default_options = dict(proxy_ip=AccountConfig.outbound_proxy[0], proxy_port=AccountConfig.outbound_proxy[1], username=AccountConfig.username, password=AccountConfig.password, domain=AccountConfig.domain, display_name=AccountConfig.display_name, do_siptrace=False, message=None, pjsip_logging=False)
    parser = OptionParser(usage=usage, description=description)
    parser.print_usage = parser.print_help
    parser.set_defaults(**default_options)
    parser.add_option("-u", "--username", type="string", dest="username", help="Username to use for the local account. This overrides the setting from the config file.")
    parser.add_option("-d", "--domain", type="string", dest="domain", help="SIP domain to use for the local account. This overrides the setting from the config file.")
    parser.add_option("-p", "--password", type="string", dest="password", help="Password to use to authenticate the local account. This overrides the setting from the config file.")
    parser.add_option("-n", "--display-name", type="string", dest="display_name", help="Display name to use for the local account. This overrides the setting from the config file.")
    parser.add_option("-o", "--outbound-proxy", type="string", action="callback", callback=lambda option, opt_str, value, parser: parse_host_port(option, opt_str, value, parser, "proxy_ip", "proxy_port", 5060), help="Outbound SIP proxy to use. By default a lookup is performed based on SRV and A records. This overrides the setting from the config file.", metavar="IP[:PORT]")
    parser.add_option("-s", "--trace-sip", action="store_true", dest="do_siptrace", help="Dump the raw contents of incoming and outgoing SIP messages (disabled by default).")
    parser.add_option("-m", "--message", type="string", dest="message", help="Contents of the message to send. This disables reading the message from standard input.")
    parser.add_option("-l", "--log-pjsip", action="store_true", dest="pjsip_logging", help="Print PJSIP logging output (disabled by default).")
    options, args = parser.parse_args()
    if args:
        try:
            retval["target_username"], retval["target_domain"] = args[0].split("@")
        except ValueError:
            retval["target_username"], retval["target_domain"] = args[0], options.domain
    else:
        retval["target_username"], retval["target_domain"] = None, None
    if not all([options.username, options.domain, options.password]):
        raise RuntimeError("No complete set of SIP credentials specified in config file and on commandline.")
    for attr in default_options:
        retval[attr] = getattr(options, attr)
    return retval

def main():
    do_message(**parse_options())

if __name__ == "__main__":
    main()