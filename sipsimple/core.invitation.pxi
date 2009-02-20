# main class

cdef class Invitation:
    cdef pjsip_inv_session *c_obj
    cdef pjsip_dialog *c_dlg
    cdef Credentials c_credentials
    cdef SIPURI c_caller_uri
    cdef SIPURI c_callee_uri
    cdef Route c_route
    cdef readonly object state
    cdef SDPSession c_local_sdp_proposed
    cdef int c_sdp_neg_status
    cdef int c_has_active_sdp

    def __cinit__(self, *args, route=None):
        cdef PJSIPUA ua = c_get_ua()
        self.state = "NULL"
        self.c_sdp_neg_status = -1
        self.c_has_active_sdp = 0
        if len(args) != 0:
            if None in args[:2]:
                raise TypeError("Positional arguments cannot be None")
            try:
                self.c_credentials, self.c_callee_uri = args[:2]
            except ValueError:
                raise TypeError("Expected at least 2 positional arguments")
            if self.c_credentials.uri is None:
                raise SIPCoreError("No SIP URI set on credentials")
            self.c_credentials = self.c_credentials.copy()
            if self.c_credentials.password is not None:
                self.c_credentials._to_c()
            self.c_caller_uri = self.c_credentials.uri
            if route is not None:
                self.c_route = route.copy()
                self.c_route._to_c(ua)

    cdef int _init_incoming(self, PJSIPUA ua, pjsip_rx_data *rdata, unsigned int inv_options) except -1:
        cdef pjsip_tx_data *tdata
        cdef PJSTR contact_uri
        cdef int status
        try:
            contact_uri = PJSTR(c_make_SIPURI(rdata.msg_info.msg.line.req.uri, 0)._as_str(1))
            status = pjsip_dlg_create_uas(pjsip_ua_instance(), rdata, &contact_uri.pj_str, &self.c_dlg)
            if status != 0:
                raise PJSIPError("Could not create dialog for new INTIVE session", status)
            status = pjsip_inv_create_uas(self.c_dlg, rdata, NULL, inv_options, &self.c_obj)
            if status != 0:
                raise PJSIPError("Could not create new INTIVE session", status)
            status = pjsip_inv_initial_answer(self.c_obj, rdata, 100, NULL, NULL, &tdata)
            if status != 0:
                raise PJSIPError("Could not create initial (unused) response to INTIVE", status)
            pjsip_tx_data_dec_ref(tdata)
            self.c_obj.mod_data[ua.c_module.id] = <void *> self
            self._cb_state(ua, "INCOMING", rdata)
        except:
            if self.c_obj != NULL:
                pjsip_inv_terminate(self.c_obj, 500, 0)
            elif self.c_dlg != NULL:
                pjsip_dlg_terminate(self.c_dlg)
            self.c_obj = NULL
            self.c_dlg = NULL
            raise
        self.c_caller_uri = c_make_SIPURI(rdata.msg_info.from_hdr.uri, 1)
        self.c_callee_uri = c_make_SIPURI(rdata.msg_info.to_hdr.uri, 1)
        return 0

    cdef PJSIPUA _check_ua(self):
        cdef PJSIPUA ua
        try:
            ua = c_get_ua()
            return ua
        except:
            self.state = "DISCONNECTED"
            self.c_obj = NULL
            self.c_dlg = NULL

    cdef int _do_dealloc(self) except -1:
        cdef PJSIPUA ua
        try:
            ua = c_get_ua()
        except SIPCoreError:
            return 0
        if self.c_obj != NULL:
            self.c_obj.mod_data[ua.c_module.id] = NULL
            if self.state != "DISCONNECTING":
                pjsip_inv_terminate(self.c_obj, 481, 0)
            self.c_obj = NULL
        return 0

    def __dealloc__(self):
        self._do_dealloc()

    cdef int _fail(self, PJSIPUA ua) except -1:
        ua.c_handle_exception(0)
        self.c_obj.mod_data[ua.c_module.id] = NULL
        if self.state != "DISCONNECTED":
            self.state = "DISCONNECTED"
            # Set prev_state to DISCONNECTED toindicate that we caused the disconnect
            c_add_event("SCInvitationChangedState", dict(obj=self, prev_state="DISCONNECTING", state="DISCONNECTED", code=0, reason="Internal exception occured"))
        # calling do_dealloc from within a callback makes PJSIP crash
        # post_handlers will be executed after pjsip_endpt_handle_events returns
        c_add_post_handler(cb_Invitation_fail_post, self)

    property caller_uri:

        def __get__(self):
            if self.c_caller_uri is None:
                return None
            else:
                return self.c_caller_uri.copy()

    property callee_uri:

        def __get__(self):
            if self.c_callee_uri is None:
                return None
            else:
                return self.c_callee_uri.copy()

    property local_uri:

        def __get__(self):
            if self.c_caller_uri is None:
                return None
            if self.c_credentials is None:
                return self.c_callee_uri.copy()
            else:
                return self.c_caller_uri.copy()

    property remote_uri:

        def __get__(self):
            if self.c_caller_uri is None:
                return None
            if self.c_credentials is None:
                return self.c_caller_uri.copy()
            else:
                return self.c_callee_uri.copy()

    property credentials:

        def __get__(self):
            if self.c_credentials is None:
                return None
            else:
                return self.c_credentials.copy()

    property route:

        def __get__(self):
            if self.c_route is None:
                return None
            else:
                return self.c_route.copy()

    property is_outgoing:

        def __get__(self):
            return self.c_credentials is not None

    def get_active_local_sdp(self):
        cdef pjmedia_sdp_session_ptr_const sdp
        self._check_ua()
        if self.c_obj != NULL and self.c_has_active_sdp:
            pjmedia_sdp_neg_get_active_local(self.c_obj.neg, &sdp)
            return c_make_SDPSession(sdp)
        else:
            return None

    def get_active_remote_sdp(self):
        cdef pjmedia_sdp_session_ptr_const sdp
        self._check_ua()
        if self.c_obj != NULL and self.c_has_active_sdp:
            pjmedia_sdp_neg_get_active_remote(self.c_obj.neg, &sdp)
            return c_make_SDPSession(sdp)
        else:
            return None

    def get_offered_remote_sdp(self):
        cdef pjmedia_sdp_session_ptr_const sdp
        self._check_ua()
        if self.c_obj != NULL and pjmedia_sdp_neg_get_state(self.c_obj.neg) in [PJMEDIA_SDP_NEG_STATE_REMOTE_OFFER, PJMEDIA_SDP_NEG_STATE_WAIT_NEGO]:
            pjmedia_sdp_neg_get_neg_remote(self.c_obj.neg, &sdp)
            return c_make_SDPSession(sdp)
        else:
            return None

    def get_offered_local_sdp(self):
        cdef pjmedia_sdp_session_ptr_const sdp
        self._check_ua()
        if self.c_obj != NULL and pjmedia_sdp_neg_get_state(self.c_obj.neg) in [PJMEDIA_SDP_NEG_STATE_LOCAL_OFFER, PJMEDIA_SDP_NEG_STATE_WAIT_NEGO]:
            pjmedia_sdp_neg_get_neg_local(self.c_obj.neg, &sdp)
            return c_make_SDPSession(sdp)
        else:
            return self.c_local_sdp_proposed

    def set_offered_local_sdp(self, local_sdp):
        cdef pjmedia_sdp_neg_state neg_state = PJMEDIA_SDP_NEG_STATE_NULL
        self._check_ua()
        if self.c_obj != NULL:
            neg_state = pjmedia_sdp_neg_get_state(self.c_obj.neg)
        if neg_state in [PJMEDIA_SDP_NEG_STATE_NULL, PJMEDIA_SDP_NEG_STATE_REMOTE_OFFER, PJMEDIA_SDP_NEG_STATE_DONE]:
            self.c_local_sdp_proposed = local_sdp
        else:
            raise SIPCoreError("Cannot set offered local SDP in this state")

    cdef int _cb_state(self, PJSIPUA ua, object state, pjsip_rx_data *rdata) except -1:
        cdef pjsip_tx_data *tdata
        cdef int status
        cdef dict event_dict
        if state == "CALLING" and state == self.state:
            return 0
        if state == "CONFIRMED":
            if self.state == "CONNECTING" and self.c_sdp_neg_status != 0:
                self.disconnect(488)
                return 0
        if self.c_obj.cancelling and state == "DISCONNECTED":
            # Hack to indicate that we caused the disconnect
            self.state = "DISCONNECTING"
        event_dict = dict(obj=self, prev_state=self.state, state=state)
        self.state = state
        if rdata != NULL:
            c_rdata_info_to_dict(rdata, event_dict)
        if state == "DISCONNECTED":
            if not self.c_obj.cancelling and rdata == NULL and self.c_obj.cause > 0:
                event_dict["code"] = self.c_obj.cause
                event_dict["reason"] = pj_str_to_str(self.c_obj.cause_text)
            self.c_obj.mod_data[ua.c_module.id] = NULL
            self.c_obj = NULL
        elif state == "REINVITED":
            status = pjsip_inv_initial_answer(self.c_obj, rdata, 100, NULL, NULL, &tdata)
            if status != 0:
                raise PJSIPError("Could not create initial (unused) response to INTIVE", status)
            pjsip_tx_data_dec_ref(tdata)
        c_add_event("SCInvitationChangedState", event_dict)
        return 0

    cdef int _cb_sdp_done(self, PJSIPUA ua, int status) except -1:
        cdef dict event_dict
        cdef pjmedia_sdp_session_ptr_const local_sdp
        cdef pjmedia_sdp_session_ptr_const remote_sdp
        self.c_sdp_neg_status = status
        self.c_local_sdp_proposed = None
        if status == 0:
            self.c_has_active_sdp = 1
        if self.state in ["DISCONNECTING", "DISCONNECTED"]:
            return 0
        event_dict = dict(obj=self, succeeded=status == 0)
        if status == 0:
            pjmedia_sdp_neg_get_active_local(self.c_obj.neg, &local_sdp)
            event_dict["local_sdp"] = c_make_SDPSession(local_sdp)
            pjmedia_sdp_neg_get_active_remote(self.c_obj.neg, &remote_sdp)
            event_dict["remote_sdp"] = c_make_SDPSession(remote_sdp)
        else:
            event_dict["error"] = pj_status_to_str(status)
        c_add_event("SCInvitationGotSDPUpdate", event_dict)
        if self.state == "REINVITED":
            self._cb_state(ua, "CONFIRMED", NULL)
        elif self.state in ["INCOMING", "EARLY"] and status != 0:
            self.disconnect(488)
        return 0

    cdef int _send_msg(self, PJSIPUA ua, pjsip_tx_data *tdata, dict extra_headers) except -1:
        cdef int status
        cdef object name, value
        cdef GenericStringHeader header
        cdef list c_extra_headers = [GenericStringHeader(name, value) for name, value in extra_headers.iteritems()]
        pjsip_msg_add_hdr(tdata.msg, <pjsip_hdr *> pjsip_hdr_clone(tdata.pool, &ua.c_user_agent_hdr.c_obj))
        for header in c_extra_headers:
            pjsip_msg_add_hdr(tdata.msg, <pjsip_hdr *> pjsip_hdr_clone(tdata.pool, &header.c_obj))
        status = pjsip_inv_send_msg(self.c_obj, tdata)
        if status != 0:
            pjsip_tx_data_dec_ref(tdata)
            raise PJSIPError("Could not send message in context of INVITE session", status)
        return 0

    def send_invite(self, dict extra_headers=None):
        cdef pjsip_tx_data *tdata
        cdef object transport
        cdef PJSTR caller_uri
        cdef PJSTR callee_uri
        cdef PJSTR callee_target
        cdef PJSTR contact_uri
        cdef pjmedia_sdp_session *local_sdp = NULL
        cdef int status
        cdef PJSIPUA ua = c_get_ua()
        if self.state != "NULL":
            raise SIPCoreError("Can only transition to the CALLING state from the NULL state")
        if self.c_local_sdp_proposed is None:
            raise SIPCoreError("Local SDP has not been set")
        caller_uri = PJSTR(self.c_caller_uri._as_str(0))
        callee_uri = PJSTR(self.c_callee_uri._as_str(0))
        callee_target = PJSTR(self.c_callee_uri._as_str(1))
        if self.c_route is not None:
            transport = self.c_route.transport
        contact_uri = ua.c_create_contact_uri(self.c_credentials.token, transport)
        try:
            status = pjsip_dlg_create_uac(pjsip_ua_instance(), &caller_uri.pj_str, &contact_uri.pj_str, &callee_uri.pj_str, &callee_target.pj_str, &self.c_dlg)
            if status != 0:
                raise PJSIPError("Could not create dialog for outgoing INVITE session", status)
            self.c_local_sdp_proposed._to_c()
            local_sdp = &self.c_local_sdp_proposed.c_obj
            status = pjsip_inv_create_uac(self.c_dlg, local_sdp, 0, &self.c_obj)
            if status != 0:
                raise PJSIPError("Could not create outgoing INVITE session", status)
            self.c_obj.mod_data[ua.c_module.id] = <void *> self
            if self.c_credentials.password is not None:
                status = pjsip_auth_clt_set_credentials(&self.c_dlg.auth_sess, 1, &self.c_credentials.c_obj)
                if status != 0:
                    raise PJSIPError("Could not set credentials for INVITE session", status)
            if self.c_route is not None:
                status = pjsip_dlg_set_route_set(self.c_dlg, &self.c_route.c_route_set)
                if status != 0:
                    raise PJSIPError("Could not set route for INVITE session", status)
            status = pjsip_inv_invite(self.c_obj, &tdata)
            if status != 0:
                raise PJSIPError("Could not create INVITE message", status)
            self._send_msg(ua, tdata, extra_headers or {})
        except:
            if self.c_obj != NULL:
                pjsip_inv_terminate(self.c_obj, 500, 0)
                self.c_obj = NULL
            elif self.c_dlg != NULL:
                pjsip_dlg_terminate(self.c_dlg)
                self.c_dlg = NULL
            raise

    def respond_to_invite_provisionally(self, int response_code=180, dict extra_headers=None):
        cdef PJSIPUA ua = self._check_ua()
        if self.state != "INCOMING":
            raise SIPCoreError("Can only transition to the EARLY state from the INCOMING state")
        if response_code / 100 != 1:
            raise SIPCoreError("Not a provisional response: %d" % response_code)
        self._send_response(ua, response_code, extra_headers)

    def accept_invite(self, dict extra_headers=None):
        cdef PJSIPUA ua = self._check_ua()
        if self.state not in ["INCOMING", "EARLY"]:
            raise SIPCoreError("Can only transition to the EARLY state from the INCOMING or EARLY states")
        try:
            self._send_response(ua, 200, extra_headers)
        except PJSIPError, e:
            if not pj_status_to_def(e.status).startswith("PJMEDIA_SDPNEG"):
                raise

    cdef int _send_response(self, PJSIPUA ua, int response_code, dict extra_headers) except -1:
        cdef pjsip_tx_data *tdata
        cdef int status
        cdef pjmedia_sdp_session *local_sdp = NULL
        if response_code / 100 == 2:
            if self.c_local_sdp_proposed is None:
                raise SIPCoreError("Local SDP has not been set")
            self.c_local_sdp_proposed._to_c()
            local_sdp = &self.c_local_sdp_proposed.c_obj
        status = pjsip_inv_answer(self.c_obj, response_code, NULL, local_sdp, &tdata)
        if status != 0:
                raise PJSIPError("Could not create %d reply to INVITE" % response_code, status)
        self._send_msg(ua, tdata, extra_headers or {})
        return 0

    def disconnect(self, int response_code=486, dict extra_headers=None):
        cdef pjsip_tx_data *tdata
        cdef int status
        cdef PJSIPUA ua = self._check_ua()
        if self.state == "DISCONNECTED":
            return
        if self.state == "DISCONNECTING":
            raise SIPCoreError("INVITE session is already DISCONNECTING")
        if self.c_obj == NULL:
            raise SIPCoreError("INVITE session is not active")
        if response_code / 100 < 3:
            raise SIPCoreError("Not a non-2xx final response: %d" % response_code)
        if response_code == 487:
            raise SIPCoreError("487 response can only be used following a CANCEL request")
        if self.state == "INCOMING":
            status = pjsip_inv_answer(self.c_obj, response_code, NULL, NULL, &tdata)
        else:
            status = pjsip_inv_end_session(self.c_obj, response_code, NULL, &tdata)
        if status != 0:
            raise PJSIPError("Could not create message to end INVITE session", status)
        self._cb_state(ua, "DISCONNECTING", NULL)
        if tdata != NULL:
            self._send_msg(ua, tdata, extra_headers or {})

    def respond_to_reinvite(self, int response_code=200, dict extra_headers=None):
        cdef PJSIPUA ua = self._check_ua()
        if self.state != "REINVITED":
            raise SIPCoreError("Can only send a response to a re-INVITE in the REINVITED state")
        self._send_response(ua, response_code, extra_headers)

    def send_reinvite(self, dict extra_headers=None):
        cdef pjsip_tx_data *tdata
        cdef int status
        cdef pjmedia_sdp_session *local_sdp = NULL
        cdef PJSIPUA ua = self._check_ua()
        if self.state != "CONFIRMED":
            raise SIPCoreError("Cannot send re-INVITE in CONFIRMED state")
        if self.c_local_sdp_proposed is not None:
            self.c_local_sdp_proposed._to_c()
            local_sdp = &self.c_local_sdp_proposed.c_obj
        status = pjsip_inv_reinvite(self.c_obj, NULL, local_sdp, &tdata)
        if status != 0:
            raise PJSIPError("Could not create re-INVITE message", status)
        self._send_msg(ua, tdata, extra_headers or {})
        self._cb_state(ua, "REINVITING", NULL)

# callback functions

cdef void cb_Invitation_cb_state(pjsip_inv_session *inv, pjsip_event *e) with gil:
    cdef Invitation invitation
    cdef object state
    cdef pjsip_rx_data *rdata = NULL
    cdef pjsip_tx_data *tdata = NULL
    cdef PJSIPUA ua
    try:
        ua = c_get_ua()
    except:
        return
    try:
        if inv.state == PJSIP_INV_STATE_INCOMING:
            return
        if inv.mod_data[ua.c_module.id] != NULL:
            invitation = <object> inv.mod_data[ua.c_module.id]
            state = pjsip_inv_state_name(inv.state)
            if state == "DISCONNCTD":
                state = "DISCONNECTED"
            if e != NULL:
                if e.type == PJSIP_EVENT_TSX_STATE and e.body.tsx_state.type == PJSIP_EVENT_TX_MSG:
                    tdata = e.body.tsx_state.src.tdata
                    if tdata.msg.type == PJSIP_RESPONSE_MSG and tdata.msg.line.status.code == 487 \
                            and state == "DISCONNECTED" and invitation.state in ["INCOMING", "EARLY"]:
                        return
                elif e.type == PJSIP_EVENT_RX_MSG:
                    rdata = e.body.rx_msg.rdata
                elif e.type == PJSIP_EVENT_TSX_STATE and e.body.tsx_state.type == PJSIP_EVENT_RX_MSG:
                    if inv.state != PJSIP_INV_STATE_CONFIRMED or e.body.tsx_state.src.rdata.msg_info.msg.type == PJSIP_REQUEST_MSG:
                        rdata = e.body.tsx_state.src.rdata
            try:
                invitation._cb_state(ua, state, rdata)
            except:
                invitation._fail(ua)
    except:
        ua.c_handle_exception(1)

cdef void cb_Invitation_cb_sdp_done(pjsip_inv_session *inv, int status) with gil:
    cdef Invitation invitation
    cdef PJSIPUA ua
    try:
        ua = c_get_ua()
    except:
        return
    try:
        if inv.mod_data[ua.c_module.id] != NULL:
            invitation = <object> inv.mod_data[ua.c_module.id]
            try:
                invitation._cb_sdp_done(ua, status)
            except:
                invitation._fail(ua)
    except:
        ua.c_handle_exception(1)

cdef void cb_Invitation_cb_rx_reinvite(pjsip_inv_session *inv, pjmedia_sdp_session_ptr_const offer, pjsip_rx_data *rdata) with gil:
    cdef Invitation invitation
    cdef PJSIPUA ua
    try:
        ua = c_get_ua()
    except:
        return
    try:
        if inv.mod_data[ua.c_module.id] != NULL:
            invitation = <object> inv.mod_data[ua.c_module.id]
            try:
                invitation._cb_state(ua, "REINVITED", rdata)
            except:
                invitation._fail(ua)
    except:
        ua.c_handle_exception(1)

cdef void cb_Invitation_cb_tsx_state_changed(pjsip_inv_session *inv, pjsip_transaction *tsx, pjsip_event *e) with gil:
    cdef Invitation invitation
    cdef pjsip_rx_data *rdata = NULL
    cdef PJSIPUA ua
    try:
        ua = c_get_ua()
    except:
        return
    try:
        if tsx == NULL or e == NULL:
            return
        if e.type == PJSIP_EVENT_TSX_STATE and e.body.tsx_state.type == PJSIP_EVENT_RX_MSG:
            rdata = e.body.tsx_state.src.rdata
        if rdata != NULL and inv.mod_data[ua.c_module.id] != NULL:
            invitation = <object> inv.mod_data[ua.c_module.id]
            if tsx.state == PJSIP_TSX_STATE_TERMINATED and invitation.state == "REINVITING":
                try:
                    invitation._cb_state(ua, "CONFIRMED", rdata)
                except:
                    invitation._fail(ua)
            elif invitation.state in ["INCOMING", "EARLY"] \
                    and invitation.c_credentials is None \
                    and rdata.msg_info.msg.type == PJSIP_REQUEST_MSG \
                    and rdata.msg_info.msg.line.req.method.id == PJSIP_CANCEL_METHOD:
                try:
                    invitation._cb_state(ua, "DISCONNECTED", rdata)
                except:
                    invitation._fail(ua)
    except:
        ua.c_handle_exception(1)

cdef void cb_new_Invitation(pjsip_inv_session *inv, pjsip_event *e) with gil:
    # As far as I can tell this is never actually called!
    pass

cdef int cb_Invitation_fail_post(object obj) except -1:
    cdef Invitation invitation = obj
    invitation._do_dealloc()

# globals

cdef pjsip_inv_callback _inv_cb
_inv_cb.on_state_changed = cb_Invitation_cb_state
_inv_cb.on_media_update = cb_Invitation_cb_sdp_done
_inv_cb.on_rx_reinvite = cb_Invitation_cb_rx_reinvite
_inv_cb.on_tsx_state_changed = cb_Invitation_cb_tsx_state_changed
_inv_cb.on_new_session = cb_new_Invitation