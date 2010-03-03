# Copyright (C) 2008-2010 AG Projects. See LICENSE for details.
#

cdef extern from *:
    ctypedef char *char_ptr_const "const char *"
    enum:
        PJ_SVN_REV "PJ_SVN_REVISION"

# system imports

cdef extern from "stdlib.h":
    void *malloc(int size)
    void free(void *ptr)

cdef extern from "string.h":
    void *memcpy(void *s1, void *s2, int n)

cdef extern from "sys/errno.h":
    enum:
        EADDRINUSE
        EBADF
        EADDRNOTAVAIL

# Python C imports

cdef extern from "Python.h":
    void Py_INCREF(object obj)
    void Py_DECREF(object obj)
    object PyString_FromStringAndSize(char *v, int len)
    char* PyString_AsString(object string) except NULL
    void* PyLong_AsVoidPtr(object)
    object PyLong_FromVoidPtr(void*)
    double PyFloat_AsDouble(object)
    void PyEval_InitThreads()

cdef extern from "stringobject.h":
    ctypedef class __builtin__.str [object PyStringObject]:
        pass

cdef extern from "dictobject.h":
    ctypedef class __builtin__.dict [object PyDictObject]:
        pass

cdef extern from "listobject.h":
    ctypedef class __builtin__.list [object PyListObject]:
        pass

# PJSIP imports

cdef extern from "pjlib.h":

    # constants
    enum:
        PJ_ERR_MSG_SIZE
    enum:
        PJ_ERRNO_START_SYS
        PJ_EBUG
        PJ_ETOOMANY
    enum:
        PJ_MAX_OBJ_NAME

    # init / shutdown
    int pj_init() nogil
    void pj_shutdown() nogil

    # version
    char *pj_get_version() nogil

    # string
    struct pj_str_t:
        char *ptr
        int slen

    # errors
    pj_str_t pj_strerror(int statcode, char *buf, int bufsize) nogil

    # logging
    enum:
        PJ_LOG_MAX_LEVEL
    enum pj_log_decoration:
        PJ_LOG_HAS_YEAR
        PJ_LOG_HAS_MONTH
        PJ_LOG_HAS_DAY_OF_MON
        PJ_LOG_HAS_TIME
        PJ_LOG_HAS_MICRO_SEC
        PJ_LOG_HAS_SENDER
    void pj_log_set_decor(int decor) nogil
    int pj_log_get_level() nogil
    void pj_log_set_level(int level) nogil
    void pj_log_set_log_func(void func(int level, char_ptr_const data, int len)) nogil

    # memory management
    struct pj_pool_t
    struct pj_pool_factory_policy:
        pass
    pj_pool_factory_policy pj_pool_factory_default_policy
    struct pj_pool_factory:
        pass
    struct pj_caching_pool:
        pj_pool_factory factory
    void pj_caching_pool_init(pj_caching_pool *ch_pool, pj_pool_factory_policy *policy, int max_capacity) nogil
    void pj_caching_pool_destroy(pj_caching_pool *ch_pool) nogil
    void *pj_pool_alloc(pj_pool_t *pool, int size) nogil
    pj_pool_t *pj_pool_create_on_buf(char *name, void *buf, int size) nogil
    pj_str_t *pj_strdup2_with_null(pj_pool_t *pool, pj_str_t *dst, char *src) nogil

    # threads
    enum:
        PJ_THREAD_DESC_SIZE
    struct pj_mutex_t
    struct pj_rwmutex_t
    struct pj_thread_t
    int pj_mutex_create_simple(pj_pool_t *pool, char *name, pj_mutex_t **mutex) nogil
    int pj_mutex_create_recursive(pj_pool_t *pool, char *name, pj_mutex_t **mutex) nogil
    int pj_mutex_lock(pj_mutex_t *mutex) nogil
    int pj_mutex_unlock(pj_mutex_t *mutex) nogil
    int pj_mutex_destroy(pj_mutex_t *mutex) nogil
    int pj_rwmutex_create(pj_pool_t *pool, char *name, pj_rwmutex_t **mutex) nogil
    int pj_rwmutex_lock_read(pj_rwmutex_t *mutex) nogil
    int pj_rwmutex_lock_write(pj_rwmutex_t *mutex) nogil
    int pj_rwmutex_unlock_read(pj_rwmutex_t *mutex) nogil
    int pj_rwmutex_unlock_write(pj_rwmutex_t *mutex) nogil
    int pj_rwmutex_destroy(pj_rwmutex_t *mutex) nogil  
    int pj_thread_is_registered() nogil
    int pj_thread_register(char *thread_name, long *thread_desc, pj_thread_t **thread) nogil

    # sockets
    enum:
        PJ_INET6_ADDRSTRLEN
    struct pj_ioqueue_t
    struct pj_addr_hdr:
        unsigned int sa_family
    struct pj_sockaddr:
        pj_addr_hdr addr
    struct pj_sockaddr_in:
        pass
    int pj_AF_INET() nogil
    int pj_AF_INET6() nogil
    int pj_sockaddr_in_init(pj_sockaddr_in *addr, pj_str_t *cp, int port) nogil
    int pj_sockaddr_get_port(pj_sockaddr *addr) nogil
    char *pj_sockaddr_print(pj_sockaddr *addr, char *buf, int size, unsigned int flags) nogil
    int pj_sockaddr_has_addr(pj_sockaddr *addr) nogil
    int pj_sockaddr_init(int af, pj_sockaddr *addr, pj_str_t *cp, unsigned int port) nogil
    int pj_inet_pton(int af, pj_str_t *src, void *dst) nogil

    # dns
    struct pj_dns_resolver

    # time
    struct pj_time_val:
        long sec
        long msec
    void pj_gettimeofday(pj_time_val *tv) nogil

    # timers
    struct pj_timer_heap_t
    struct pj_timer_entry:
        void *user_data
        int id
    pj_timer_entry *pj_timer_entry_init(pj_timer_entry *entry, int id, void *user_data,
                                        void cb(pj_timer_heap_t *timer_heap, pj_timer_entry *entry) with gil) nogil

    # lists
    struct pj_list:
        void *prev
        void *next
    void pj_list_init(pj_list *node) nogil
    void pj_list_insert_after(pj_list *pos, pj_list *node) nogil

    # random
    void pj_srand(unsigned int seed) nogil

    # maths
    struct pj_math_stat:
        int n
        int max
        int min
        int last
        int mean

cdef extern from "pjlib-util.h":

    # init
    int pjlib_util_init() nogil

cdef extern from "pjnath.h":

    # init
    int pjnath_init() nogil

    # STUN
    enum:
        PJ_STUN_PORT
    struct pj_stun_config:
        pass
    struct pj_stun_sock_cfg:
        pj_sockaddr bound_addr
    void pj_stun_config_init(pj_stun_config *cfg, pj_pool_factory *factory, unsigned int options,
                             pj_ioqueue_t *ioqueue, pj_timer_heap_t *timer_heap) nogil

    # NAT detection
    struct pj_stun_nat_detect_result:
        int status
        char *status_text
        char *nat_type_name
    ctypedef pj_stun_nat_detect_result *pj_stun_nat_detect_result_ptr_const "const pj_stun_nat_detect_result *"
    int pj_stun_detect_nat_type(pj_sockaddr_in *server, pj_stun_config *stun_cfg, void *user_data,
                                void pj_stun_nat_detect_cb(void *user_data,
                                                           pj_stun_nat_detect_result_ptr_const res) with gil) nogil

    # ICE
    struct pj_ice_strans_cfg_stun:
        pj_stun_sock_cfg cfg
        pj_str_t server
        unsigned int port
    struct pj_ice_strans_cfg:
        int af
        pj_stun_config stun_cfg
        pj_ice_strans_cfg_stun stun
    enum pj_ice_strans_op:
        PJ_ICE_STRANS_OP_INIT
        PJ_ICE_STRANS_OP_NEGOTIATION
    void pj_ice_strans_cfg_default(pj_ice_strans_cfg *cfg) nogil

cdef extern from "pjmedia.h":

    # constants
    enum:
        PJMEDIA_ENOSNDREC
        PJMEDIA_ENOSNDPLAY

    # codec manager
    struct pjmedia_codec_mgr
    enum:
        PJMEDIA_CODEC_MGR_MAX_CODECS
    struct pjmedia_codec_info:
        pj_str_t encoding_name
        unsigned int clock_rate
        unsigned int channel_cnt
    int pjmedia_codec_mgr_enum_codecs(pjmedia_codec_mgr *mgr, unsigned int *count,
                                      pjmedia_codec_info *info, unsigned int *prio) nogil
    int pjmedia_codec_mgr_set_codec_priority(pjmedia_codec_mgr *mgr, pj_str_t *codec_id, unsigned int prio) nogil

    # endpoint
    struct pjmedia_endpt
    int pjmedia_endpt_create(pj_pool_factory *pf, pj_ioqueue_t *ioqueue, int worker_cnt, pjmedia_endpt **p_endpt) nogil
    int pjmedia_endpt_destroy(pjmedia_endpt *endpt) nogil
    pj_ioqueue_t *pjmedia_endpt_get_ioqueue(pjmedia_endpt *endpt) nogil
    pjmedia_codec_mgr *pjmedia_endpt_get_codec_mgr(pjmedia_endpt *endpt) nogil

    # codecs
    int pjmedia_codec_g711_init(pjmedia_endpt *endpt) nogil
    int pjmedia_codec_g711_deinit() nogil

    # sound devices
    struct pjmedia_snd_dev_info:
        char *name
        int input_count
        int output_count
    struct pjmedia_snd_stream_info:
        int play_id
        int rec_id
    struct pjmedia_snd_stream
    ctypedef pjmedia_snd_dev_info *pjmedia_snd_dev_info_ptr_const "const pjmedia_snd_dev_info *"
    ctypedef void (*audio_change_callback) (void *user_data)
    enum audio_change_type:
         AUDIO_CHANGE_INPUT = 1
         AUDIO_CHANGE_OUTPUT = 2
    struct pjmedia_audio_change_observer:
         audio_change_callback default_audio_change
         audio_change_callback audio_devices_will_change
         audio_change_callback audio_devices_did_change
    int pjmedia_add_audio_change_observer(pjmedia_audio_change_observer *audio_change_observer)    
    int pjmedia_del_audio_change_observer(pjmedia_audio_change_observer *audio_change_observer)    
    int pjmedia_snd_get_dev_count() nogil
    pjmedia_snd_dev_info_ptr_const pjmedia_snd_get_dev_info(int index) nogil
    int pjmedia_snd_stream_get_info(pjmedia_snd_stream *strm, pjmedia_snd_stream_info *pi) nogil

    # sound port
    struct pjmedia_port
    struct pjmedia_snd_port
    int pjmedia_snd_port_create(pj_pool_t *pool, int rec_id, int play_id, unsigned int clock_rate,
                                unsigned int channel_count, unsigned int samples_per_frame,
                                unsigned int bits_per_sample, unsigned int options, pjmedia_snd_port **p_port) nogil
    int pjmedia_snd_port_create_rec(pj_pool_t *pool, int index, unsigned int clock_rate, unsigned int channel_count,
                                    unsigned int samples_per_frame, unsigned int bits_per_sample, unsigned int options,
                                    pjmedia_snd_port **p_port) nogil
    int pjmedia_snd_port_create_player(pj_pool_t *pool, unsigned int index, unsigned int clock_rate,
                                       unsigned int channel_count, unsigned int samples_per_frame,
                                       unsigned int bits_per_sample, unsigned int options, pjmedia_snd_port **p_port) nogil
    int pjmedia_snd_port_connect(pjmedia_snd_port *snd_port, pjmedia_port *port) nogil
    int pjmedia_snd_port_disconnect(pjmedia_snd_port *snd_port) nogil
    int pjmedia_snd_port_set_ec(pjmedia_snd_port *snd_port, pj_pool_t *pool, unsigned int tail_ms, int options) nogil
    int pjmedia_snd_port_destroy(pjmedia_snd_port *snd_port) nogil
    pjmedia_snd_stream *pjmedia_snd_port_get_snd_stream(pjmedia_snd_port *snd_port) nogil
    int pjmedia_null_port_create(pj_pool_t *pool, unsigned int sampling_rate, unsigned int channel_count,
                                 unsigned int samples_per_frame, unsigned int bits_per_sample, pjmedia_port **p_port) nogil

    # master port
    struct pjmedia_master_port
    int pjmedia_master_port_create(pj_pool_t *pool, pjmedia_port *u_port, pjmedia_port *d_port,
                                   unsigned int options, pjmedia_master_port **p_m) nogil
    int pjmedia_master_port_start(pjmedia_master_port *m) nogil
    int pjmedia_master_port_destroy(pjmedia_master_port *m, int destroy_ports) nogil

    # conference bridge
    enum pjmedia_conf_option:
        PJMEDIA_CONF_NO_DEVICE
    struct pjmedia_conf
    int pjmedia_conf_create(pj_pool_t *pool, int max_slots, int sampling_rate, int channel_count,
                            int samples_per_frame, int bits_per_sample, int options, pjmedia_conf **p_conf) nogil
    int pjmedia_conf_destroy(pjmedia_conf *conf) nogil
    pjmedia_port *pjmedia_conf_get_master_port(pjmedia_conf *conf) nogil
    int pjmedia_conf_add_port(pjmedia_conf *conf, pj_pool_t *pool, pjmedia_port *strm_port,
                              pj_str_t *name, unsigned int *p_slot) nogil
    int pjmedia_conf_remove_port(pjmedia_conf *conf, unsigned int slot) nogil
    int pjmedia_conf_connect_port(pjmedia_conf *conf, unsigned int src_slot, unsigned int sink_slot, int level) nogil
    int pjmedia_conf_disconnect_port(pjmedia_conf *conf, unsigned int src_slot, unsigned int sink_slot) nogil
    int pjmedia_conf_adjust_rx_level(pjmedia_conf *conf, unsigned slot, int adj_level) nogil
    int pjmedia_conf_adjust_tx_level(pjmedia_conf *conf, unsigned slot, int adj_level) nogil

    # sdp
    enum:
        PJMEDIA_MAX_SDP_FMT
    enum:
        PJMEDIA_MAX_SDP_ATTR
    enum:
        PJMEDIA_MAX_SDP_MEDIA
    struct pjmedia_sdp_attr:
        pj_str_t name
        pj_str_t value
    struct pjmedia_sdp_conn:
        pj_str_t net_type
        pj_str_t addr_type
        pj_str_t addr
    struct pjmedia_sdp_media_desc:
        pj_str_t media
        unsigned int port
        unsigned int port_count
        pj_str_t transport
        unsigned int fmt_count
        pj_str_t fmt[PJMEDIA_MAX_SDP_FMT]
    struct pjmedia_sdp_media:
        pjmedia_sdp_media_desc desc
        pj_str_t info
        pjmedia_sdp_conn *conn
        unsigned int attr_count
        pjmedia_sdp_attr *attr[PJMEDIA_MAX_SDP_ATTR]
    struct pjmedia_sdp_session_origin:
        pj_str_t user
        unsigned int id
        unsigned int version
        pj_str_t net_type
        pj_str_t addr_type
        pj_str_t addr
    struct pjmedia_sdp_session_time:
        unsigned int start
        unsigned int stop
    struct pjmedia_sdp_session:
        pjmedia_sdp_session_origin origin
        pj_str_t name
        pj_str_t info
        pjmedia_sdp_conn *conn
        pjmedia_sdp_session_time time
        unsigned int attr_count
        pjmedia_sdp_attr *attr[PJMEDIA_MAX_SDP_ATTR]
        unsigned int media_count
        pjmedia_sdp_media *media[PJMEDIA_MAX_SDP_MEDIA]
    ctypedef pjmedia_sdp_session *pjmedia_sdp_session_ptr_const "const pjmedia_sdp_session *"
    pjmedia_sdp_media *pjmedia_sdp_media_clone(pj_pool_t *pool, pjmedia_sdp_media *rhs) nogil

    # sdp negotiation

    enum pjmedia_sdp_neg_state:
        PJMEDIA_SDP_NEG_STATE_NULL
        PJMEDIA_SDP_NEG_STATE_LOCAL_OFFER
        PJMEDIA_SDP_NEG_STATE_REMOTE_OFFER
        PJMEDIA_SDP_NEG_STATE_WAIT_NEGO
        PJMEDIA_SDP_NEG_STATE_DONE
    struct pjmedia_sdp_neg
    int pjmedia_sdp_neg_get_neg_remote(pjmedia_sdp_neg *neg, pjmedia_sdp_session_ptr_const *remote) nogil
    int pjmedia_sdp_neg_get_neg_local(pjmedia_sdp_neg *neg, pjmedia_sdp_session_ptr_const *local) nogil
    int pjmedia_sdp_neg_get_active_remote(pjmedia_sdp_neg *neg, pjmedia_sdp_session_ptr_const *remote) nogil
    int pjmedia_sdp_neg_get_active_local(pjmedia_sdp_neg *neg, pjmedia_sdp_session_ptr_const *local) nogil
    int pjmedia_sdp_neg_cancel_offer(pjmedia_sdp_neg *neg) nogil
    int pjmedia_sdp_neg_cancel_remote_offer(pjmedia_sdp_neg *neg) nogil
    pjmedia_sdp_neg_state pjmedia_sdp_neg_get_state(pjmedia_sdp_neg *neg) nogil
    char *pjmedia_sdp_neg_state_str(pjmedia_sdp_neg_state state) nogil

    # transport
    enum pjmedia_transport_type:
        PJMEDIA_TRANSPORT_TYPE_ICE
    struct pjmedia_sock_info:
        pj_sockaddr rtp_addr_name
    struct pjmedia_transport:
        char *name
        pjmedia_transport_type type
    enum pjmedia_transport_type:
        PJMEDIA_TRANSPORT_TYPE_SRTP
    struct pjmedia_transport_specific_info:
        pjmedia_transport_type type
        char *buffer
    struct pjmedia_transport_info:
        pjmedia_sock_info sock_info
        pj_sockaddr src_rtp_name
        int specific_info_cnt
        pjmedia_transport_specific_info *spc_info
    struct pjmedia_srtp_info:
        int active
    void pjmedia_transport_info_init(pjmedia_transport_info *info) nogil
    int pjmedia_transport_udp_create3(pjmedia_endpt *endpt, int af, char *name, pj_str_t *addr, int port,
                                      unsigned int options, pjmedia_transport **p_tp) nogil
    int pjmedia_transport_get_info(pjmedia_transport *tp, pjmedia_transport_info *info) nogil
    int pjmedia_transport_close(pjmedia_transport *tp) nogil
    int pjmedia_transport_media_create(pjmedia_transport *tp, pj_pool_t *sdp_pool, unsigned int options,
                                       pjmedia_sdp_session *rem_sdp, unsigned int media_index) nogil
    int pjmedia_transport_encode_sdp(pjmedia_transport *tp, pj_pool_t *sdp_pool, pjmedia_sdp_session *sdp,
                                     pjmedia_sdp_session *rem_sdp, unsigned int media_index) nogil
    int pjmedia_transport_media_start(pjmedia_transport *tp, pj_pool_t *tmp_pool, pjmedia_sdp_session *sdp_local,
                                      pjmedia_sdp_session *sdp_remote, unsigned int media_index) nogil
    int pjmedia_transport_media_stop(pjmedia_transport *tp) nogil
    int pjmedia_endpt_create_sdp(pjmedia_endpt *endpt, pj_pool_t *pool, unsigned int stream_cnt,
                                 pjmedia_sock_info *sock_info, pjmedia_sdp_session **p_sdp) nogil

    # SRTP
    enum pjmedia_srtp_use:
        PJMEDIA_SRTP_MANDATORY
    struct pjmedia_srtp_setting:
        pjmedia_srtp_use use
    void pjmedia_srtp_setting_default(pjmedia_srtp_setting *opt) nogil
    int pjmedia_transport_srtp_create(pjmedia_endpt *endpt, pjmedia_transport *tp,
                                      pjmedia_srtp_setting *opt, pjmedia_transport **p_tp) nogil

    # ICE
    struct pjmedia_ice_cb:
        void on_ice_complete(pjmedia_transport *tp, pj_ice_strans_op op, int status) with gil
    int pjmedia_ice_create2(pjmedia_endpt *endpt, char *name, unsigned int comp_cnt, pj_ice_strans_cfg *cfg,
                            pjmedia_ice_cb *cb, unsigned int options, pjmedia_transport **p_tp) nogil

    # stream
    enum pjmedia_dir:
        PJMEDIA_DIR_ENCODING
        PJMEDIA_DIR_DECODING
    struct pjmedia_codec_param_setting:
        unsigned int vad
    struct pjmedia_codec_param:
        pjmedia_codec_param_setting setting
    struct pjmedia_stream_info:
        pjmedia_codec_info fmt
        pjmedia_codec_param *param
        unsigned int tx_event_pt
        
    struct pjmedia_rtcp_stream_stat_loss_type:
        unsigned int burst
        unsigned int random
    struct pjmedia_rtcp_stream_stat:
        unsigned int pkt
        unsigned int bytes
        unsigned int discard
        unsigned int loss
        unsigned int reorder
        unsigned int dup
        pj_math_stat loss_period
        pjmedia_rtcp_stream_stat_loss_type loss_type
        pj_math_stat jitter
    struct pjmedia_rtcp_stat:
        pjmedia_rtcp_stream_stat tx
        pjmedia_rtcp_stream_stat rx
        pj_math_stat rtt
    struct pjmedia_stream
    int pjmedia_stream_info_from_sdp(pjmedia_stream_info *si, pj_pool_t *pool, pjmedia_endpt *endpt,
                                     pjmedia_sdp_session *local, pjmedia_sdp_session *remote, unsigned int stream_idx) nogil
    int pjmedia_stream_create(pjmedia_endpt *endpt, pj_pool_t *pool, pjmedia_stream_info *info,
                              pjmedia_transport *tp, void *user_data, pjmedia_stream **p_stream) nogil
    int pjmedia_stream_destroy(pjmedia_stream *stream) nogil
    int pjmedia_stream_get_port(pjmedia_stream *stream, pjmedia_port **p_port) nogil
    int pjmedia_stream_start(pjmedia_stream *stream) nogil
    int pjmedia_stream_dial_dtmf(pjmedia_stream *stream, pj_str_t *ascii_digit) nogil
    int pjmedia_stream_set_dtmf_callback(pjmedia_stream *stream,
                                         void cb(pjmedia_stream *stream, void *user_data, int digit) with gil,
                                         void *user_data) nogil
    int pjmedia_stream_pause(pjmedia_stream *stream, pjmedia_dir dir) nogil
    int pjmedia_stream_resume(pjmedia_stream *stream, pjmedia_dir dir) nogil
    int pjmedia_stream_get_stat(pjmedia_stream *stream, pjmedia_rtcp_stat *stat) nogil

    # wav player
    enum:
        PJMEDIA_FILE_NO_LOOP
    int pjmedia_port_destroy(pjmedia_port *port) nogil
    int pjmedia_wav_player_port_create(pj_pool_t *pool, char *filename, unsigned int ptime, unsigned int flags,
                                       unsigned int buff_size, pjmedia_port **p_port) nogil
    int pjmedia_wav_player_set_eof_cb(pjmedia_port *port, void *user_data,
                                      int cb(pjmedia_port *port, void *usr_data) with gil) nogil
    int pjmedia_wav_player_port_set_pos(pjmedia_port *port, unsigned int offset) nogil

    # wav recorder
    enum pjmedia_file_writer_option:
        PJMEDIA_FILE_WRITE_PCM
    int pjmedia_wav_writer_port_create(pj_pool_t *pool, char *filename, unsigned int clock_rate,
                                       unsigned int channel_count, unsigned int samples_per_frame,
                                       unsigned int bits_per_sample, unsigned int flags, int buff_size,
                                       pjmedia_port **p_port) nogil

    # tone generator
    enum:
        PJMEDIA_TONEGEN_MAX_DIGITS
    struct pjmedia_tone_desc:
        short freq1
        short freq2
        short on_msec
        short off_msec
        short volume
        short flags
    struct pjmedia_tone_digit:
        char digit
        short on_msec
        short off_msec
        short volume
    int pjmedia_tonegen_create(pj_pool_t *pool, unsigned int clock_rate, unsigned int channel_count,
                               unsigned int samples_per_frame, unsigned int bits_per_sample,
                               unsigned int options, pjmedia_port **p_port) nogil
    int pjmedia_tonegen_play(pjmedia_port *tonegen, unsigned int count, pjmedia_tone_desc *tones, unsigned int options) nogil
    int pjmedia_tonegen_play_digits(pjmedia_port *tonegen, unsigned int count,
                                    pjmedia_tone_digit *digits, unsigned int options) nogil
    int pjmedia_tonegen_stop(pjmedia_port *tonegen) nogil
    int pjmedia_tonegen_is_busy(pjmedia_port *tonegen) nogil

cdef extern from "pjmedia-codec.h":

    # codecs
    enum:
        PJMEDIA_SPEEX_NO_UWB
        PJMEDIA_SPEEX_NO_WB
    int pjmedia_codec_gsm_init(pjmedia_endpt *endpt) nogil
    int pjmedia_codec_gsm_deinit() nogil
    int pjmedia_codec_g722_init(pjmedia_endpt *endpt) nogil
    int pjmedia_codec_g722_deinit() nogil
    int pjmedia_codec_ilbc_init(pjmedia_endpt *endpt, int mode) nogil
    int pjmedia_codec_ilbc_deinit() nogil
    int pjmedia_codec_speex_init(pjmedia_endpt *endpt, int options, int quality, int complexity) nogil
    int pjmedia_codec_speex_deinit() nogil

cdef extern from "pjsip.h":

    # messages
    enum pjsip_status_code:
        PJSIP_SC_TSX_TIMEOUT
        PJSIP_SC_TSX_TRANSPORT_ERROR
        PJSIP_TLS_EUNKNOWN
        PJSIP_TLS_EINVMETHOD
        PJSIP_TLS_ECACERT
        PJSIP_TLS_ECERTFILE
        PJSIP_TLS_EKEYFILE
        PJSIP_TLS_ECIPHER
        PJSIP_TLS_ECTX
    struct pjsip_transport
    enum pjsip_uri_context_e:
        PJSIP_URI_IN_CONTACT_HDR
    struct pjsip_param:
        pj_str_t name
        pj_str_t value
    struct pjsip_uri
    struct pjsip_sip_uri:
        pj_str_t user
        pj_str_t passwd
        pj_str_t host
        int port
        pj_str_t user_param
        pj_str_t method_param
        pj_str_t transport_param
        int ttl_param
        int lr_param
        pj_str_t maddr_param
        pjsip_param other_param
        pjsip_param header_param
    struct pjsip_name_addr:
        pj_str_t display
        pjsip_uri *uri
    struct pjsip_media_type:
        pj_str_t type
        pj_str_t subtype
        pj_str_t param
    enum pjsip_method_e:
        PJSIP_CANCEL_METHOD
        PJSIP_OTHER_METHOD
    struct pjsip_method:
        pjsip_method_e id
        pj_str_t name
    struct pjsip_host_port:
        pj_str_t host
        int port
    enum pjsip_hdr_e:
        PJSIP_H_VIA
        PJSIP_H_CALL_ID
        PJSIP_H_CSEQ
        PJSIP_H_EXPIRES
        PJSIP_H_FROM
    struct pjsip_hdr:
        pjsip_hdr_e type
        pj_str_t name
    ctypedef pjsip_hdr *pjsip_hdr_ptr_const "const pjsip_hdr*"
    struct pjsip_generic_array_hdr:
        unsigned int count
        pj_str_t *values
    struct pjsip_generic_string_hdr:
        pj_str_t name
        pj_str_t hvalue
    struct pjsip_cid_hdr:
        pj_str_t id
    struct pjsip_contact_hdr:
        int star
        pjsip_uri *uri
        int q1000
        int expires
        pjsip_param other_param
    struct pjsip_clen_hdr:
        int len
    struct pjsip_ctype_hdr:
        pjsip_media_type media
    struct pjsip_cseq_hdr:
        int cseq
        pjsip_method method
    struct pjsip_generic_int_hdr:
        int ivalue
    ctypedef pjsip_generic_int_hdr pjsip_expires_hdr
    struct pjsip_fromto_hdr:
        pjsip_uri *uri
        pj_str_t tag
        pjsip_param other_param
    struct pjsip_routing_hdr:
        pjsip_name_addr name_addr
        pjsip_param other_param
    ctypedef pjsip_routing_hdr pjsip_route_hdr
    struct pjsip_retry_after_hdr:
        int ivalue
        pjsip_param param
        pj_str_t comment
    struct pjsip_via_hdr:
        pj_str_t transport
        pjsip_host_port sent_by
        int ttl_param
        int rport_param
        pj_str_t maddr_param
        pj_str_t recvd_param
        pj_str_t branch_param
        pjsip_param other_param
        pj_str_t comment
    enum:
        PJSIP_MAX_ACCEPT_COUNT
    struct pjsip_msg_body:
        pjsip_media_type content_type
        void *data
        unsigned int len
    struct pjsip_request_line:
        pjsip_method method
        pjsip_uri *uri
    struct pjsip_status_line:
        int code
        pj_str_t reason
    union pjsip_msg_line:
        pjsip_request_line req
        pjsip_status_line status
    enum pjsip_msg_type_e:
        PJSIP_REQUEST_MSG
        PJSIP_RESPONSE_MSG
    struct pjsip_msg:
        pjsip_msg_type_e type
        pjsip_msg_line line
        pjsip_hdr hdr
        pjsip_msg_body *body
    struct pjsip_buffer:
        char *start
        char *cur
    struct pjsip_tx_data_tp_info:
        char *dst_name
        int dst_port
        pjsip_transport *transport
    struct pjsip_tx_data:
        pjsip_msg *msg
        pj_pool_t *pool
        pjsip_buffer buf
        pjsip_tx_data_tp_info tp_info
    struct pjsip_rx_data_tp_info:
        pj_pool_t *pool
        pjsip_transport *transport
    struct pjsip_rx_data_pkt_info:
        pj_time_val timestamp
        char *packet
        int len
        char *src_name
        int src_port
    struct pjsip_rx_data_msg_info:
        pjsip_msg *msg
        pjsip_fromto_hdr *from_hdr "from"
        pjsip_fromto_hdr *to_hdr "to"
        pjsip_via_hdr *via
    struct pjsip_rx_data:
        pjsip_rx_data_pkt_info pkt_info
        pjsip_rx_data_tp_info tp_info
        pjsip_rx_data_msg_info msg_info
    void *pjsip_hdr_clone(pj_pool_t *pool, void *hdr) nogil
    void pjsip_msg_add_hdr(pjsip_msg *msg, pjsip_hdr *hdr) nogil
    void *pjsip_msg_find_hdr(pjsip_msg *msg, pjsip_hdr_e type, void *start) nogil
    void *pjsip_msg_find_hdr_by_name(pjsip_msg *msg, pj_str_t *name, void *start) nogil
    pjsip_generic_string_hdr *pjsip_generic_string_hdr_create(pj_pool_t *pool, pj_str_t *hname, pj_str_t *hvalue) nogil
    pjsip_contact_hdr *pjsip_contact_hdr_create(pj_pool_t *pool) nogil
    pjsip_expires_hdr *pjsip_expires_hdr_create(pj_pool_t *pool, int value) nogil
    pjsip_msg_body *pjsip_msg_body_create(pj_pool_t *pool, pj_str_t *type, pj_str_t *subtype, pj_str_t *text) nogil
    pjsip_route_hdr *pjsip_route_hdr_init(pj_pool_t *pool, void *mem) nogil
    void pjsip_sip_uri_init(pjsip_sip_uri *url, int secure) nogil
    int pjsip_tx_data_dec_ref(pjsip_tx_data *tdata) nogil
    void pjsip_tx_data_add_ref(pjsip_tx_data *tdata) nogil
    pj_str_t *pjsip_uri_get_scheme(pjsip_uri *uri) nogil
    void *pjsip_uri_get_uri(pjsip_uri *uri) nogil
    int pjsip_uri_print(pjsip_uri_context_e context, void *uri, char *buf, unsigned int size) nogil
    int PJSIP_URI_SCHEME_IS_SIP(pjsip_sip_uri *uri) nogil
    enum:
        PJSIP_PARSE_URI_AS_NAMEADDR
    pjsip_uri *pjsip_parse_uri(pj_pool_t *pool, char *buf, unsigned int size, unsigned int options) nogil
    void pjsip_method_init_np(pjsip_method *m, pj_str_t *str) nogil
    pj_str_t *pjsip_get_status_text(int status_code) nogil

    # module
    enum pjsip_module_priority:
        PJSIP_MOD_PRIORITY_APPLICATION
        PJSIP_MOD_PRIORITY_DIALOG_USAGE
        PJSIP_MOD_PRIORITY_TRANSPORT_LAYER
    struct pjsip_event
    struct pjsip_transaction
    struct pjsip_module:
        pj_str_t name
        int id
        int priority
        int on_rx_request(pjsip_rx_data *rdata) with gil
        int on_rx_response(pjsip_rx_data *rdata) with gil
        int on_tx_request(pjsip_tx_data *tdata) with gil
        int on_tx_response(pjsip_tx_data *tdata) with gil
        void on_tsx_state(pjsip_transaction *tsx, pjsip_event *event) with gil

    # endpoint
    struct pjsip_endpoint
    int pjsip_endpt_create(pj_pool_factory *pf, char *name, pjsip_endpoint **endpt) nogil
    void pjsip_endpt_destroy(pjsip_endpoint *endpt) nogil
    pj_pool_t *pjsip_endpt_create_pool(pjsip_endpoint *endpt, char *pool_name, int initial, int increment) nogil
    void pjsip_endpt_release_pool(pjsip_endpoint *endpt, pj_pool_t *pool) nogil
    int pjsip_endpt_handle_events(pjsip_endpoint *endpt, pj_time_val *max_timeout) nogil
    int pjsip_endpt_register_module(pjsip_endpoint *endpt, pjsip_module *module) nogil
    int pjsip_endpt_schedule_timer(pjsip_endpoint *endpt, pj_timer_entry *entry, pj_time_val *delay) nogil
    void pjsip_endpt_cancel_timer(pjsip_endpoint *endpt, pj_timer_entry *entry) nogil
    enum:
        PJSIP_H_ACCEPT
        PJSIP_H_ALLOW
        PJSIP_H_SUPPORTED
    pjsip_hdr_ptr_const pjsip_endpt_get_capability(pjsip_endpoint *endpt, int htype, pj_str_t *hname) nogil
    int pjsip_endpt_add_capability(pjsip_endpoint *endpt, pjsip_module *mod, int htype,
                                   pj_str_t *hname, unsigned count, pj_str_t *tags) nogil
    int pjsip_endpt_create_response(pjsip_endpoint *endpt, pjsip_rx_data *rdata,
                                    int st_code, pj_str_t *st_text, pjsip_tx_data **p_tdata) nogil
    int pjsip_endpt_send_response2(pjsip_endpoint *endpt, pjsip_rx_data *rdata,
                                   pjsip_tx_data *tdata, void *token, void *cb) nogil
    int pjsip_endpt_create_request(pjsip_endpoint *endpt, pjsip_method *method, pj_str_t *target, pj_str_t *frm,
                                   pj_str_t *to, pj_str_t *contact, pj_str_t *call_id,
                                   int cseq,pj_str_t *text, pjsip_tx_data **p_tdata) nogil
    pj_timer_heap_t *pjsip_endpt_get_timer_heap(pjsip_endpoint *endpt) nogil
    int pjsip_endpt_create_resolver(pjsip_endpoint *endpt, pj_dns_resolver **p_resv) nogil
    int pjsip_endpt_set_resolver(pjsip_endpoint *endpt, pj_dns_resolver *resv) nogil

    # transports
    enum pjsip_ssl_method:
        PJSIP_SSL_UNSPECIFIED_METHOD
        PJSIP_TLSV1_METHOD
        PJSIP_SSLV2_METHOD
        PJSIP_SSLV3_METHOD
        PJSIP_SSLV23_METHOD
    struct pjsip_transport:
        char *type_name
        pjsip_host_port local_name
    struct pjsip_tpfactory:
        pjsip_host_port addr_name
        int destroy(pjsip_tpfactory *factory) nogil
    struct pjsip_tls_setting:
        pj_str_t ca_list_file
        pj_str_t cert_file
        pj_str_t privkey_file
        int method
        int verify_server
        pj_time_val timeout
    enum pjsip_tpselector_type:
        PJSIP_TPSELECTOR_TRANSPORT
    union pjsip_tpselector_u:
        pjsip_transport *transport
    struct pjsip_tpselector:
        pjsip_tpselector_type type
        pjsip_tpselector_u u
    int pjsip_transport_shutdown(pjsip_transport *tp) nogil
    int pjsip_udp_transport_start(pjsip_endpoint *endpt, pj_sockaddr_in *local, pjsip_host_port *a_name,
                                  unsigned int async_cnt, pjsip_transport **p_transport) nogil
    int pjsip_tcp_transport_start2(pjsip_endpoint *endpt, pj_sockaddr_in *local, pjsip_host_port *a_name,
                                   unsigned int async_cnt, pjsip_tpfactory **p_tpfactory) nogil
    int pjsip_tls_transport_start(pjsip_endpoint *endpt, pjsip_tls_setting *opt, pj_sockaddr_in *local,
                                  pjsip_host_port *a_name, unsigned async_cnt, pjsip_tpfactory **p_factory) nogil
    void pjsip_tls_setting_default(pjsip_tls_setting *tls_opt) nogil
    int pjsip_transport_shutdown(pjsip_transport *tp) nogil

    # transaction layer
    enum pjsip_role_e:
        PJSIP_ROLE_UAC
        PJSIP_ROLE_UAS
    enum pjsip_tsx_state_e:
        PJSIP_TSX_STATE_PROCEEDING
        PJSIP_TSX_STATE_COMPLETED
        PJSIP_TSX_STATE_TERMINATED
    struct pjsip_transaction:
        int status_code
        pj_str_t status_text
        pjsip_role_e role
        pjsip_tx_data *last_tx
        pjsip_tsx_state_e state
        void **mod_data
        pjsip_method method
    int pjsip_tsx_layer_init_module(pjsip_endpoint *endpt) nogil
    int pjsip_tsx_create_key(pj_pool_t *pool, pj_str_t *key, pjsip_role_e role,
                             pjsip_method *method, pjsip_rx_data *rdata) nogil
    pjsip_transaction *pjsip_tsx_layer_find_tsx(pj_str_t *key, int lock) nogil
    int pjsip_tsx_create_uac(pjsip_module *tsx_user, pjsip_tx_data *tdata, pjsip_transaction **p_tsx) nogil
    int pjsip_tsx_terminate(pjsip_transaction *tsx, int code) nogil
    int pjsip_tsx_send_msg(pjsip_transaction *tsx, pjsip_tx_data *tdata) nogil
    pjsip_transaction *pjsip_rdata_get_tsx(pjsip_rx_data *rdata) nogil
    int pjsip_tsx_create_uas(pjsip_module *tsx_user, pjsip_rx_data *rdata, pjsip_transaction **p_tsx) nogil
    void pjsip_tsx_recv_msg(pjsip_transaction *tsx, pjsip_rx_data *rdata) nogil

    # event
    enum pjsip_event_id_e:
        PJSIP_EVENT_TSX_STATE
        PJSIP_EVENT_RX_MSG
        PJSIP_EVENT_TX_MSG
        PJSIP_EVENT_TRANSPORT_ERROR
        PJSIP_EVENT_TIMER
    union pjsip_event_body_tsx_state_src:
        pjsip_rx_data *rdata
        pjsip_tx_data *tdata
    struct pjsip_event_body_tsx_state:
        pjsip_event_body_tsx_state_src src
        pjsip_transaction *tsx
        pjsip_event_id_e type
    struct pjsip_event_body_rx_msg:
        pjsip_rx_data *rdata
    union pjsip_event_body:
        pjsip_event_body_tsx_state tsx_state
        pjsip_event_body_rx_msg rx_msg
    struct pjsip_event:
        pjsip_event_id_e type
        pjsip_event_body body
    int pjsip_endpt_send_request(pjsip_endpoint *endpt, pjsip_tx_data *tdata, int timeout,
                                 void *token, void cb(void *token, pjsip_event *e) with gil) nogil

    # auth
    enum:
        PJSIP_EFAILEDCREDENTIAL
    enum pjsip_cred_data_type:
        PJSIP_CRED_DATA_PLAIN_PASSWD
    struct pjsip_cred_info:
        pj_str_t realm
        pj_str_t scheme
        pj_str_t username
        pjsip_cred_data_type data_type
        pj_str_t data
    struct pjsip_auth_clt_sess:
        pass
    int pjsip_auth_clt_init(pjsip_auth_clt_sess *sess, pjsip_endpoint *endpt, pj_pool_t *pool, unsigned int options) nogil
    int pjsip_auth_clt_set_credentials(pjsip_auth_clt_sess *sess, int cred_cnt, pjsip_cred_info *c) nogil
    int pjsip_auth_clt_reinit_req(pjsip_auth_clt_sess *sess, pjsip_rx_data *rdata,
                                  pjsip_tx_data *old_request, pjsip_tx_data **new_request) nogil

    # dialog layer
    ctypedef pjsip_module pjsip_user_agent
    struct pjsip_dlg_party:
        pjsip_contact_hdr *contact
        pjsip_fromto_hdr *info
    struct pjsip_dialog:
        pjsip_auth_clt_sess auth_sess
        pjsip_cid_hdr *call_id
        pj_pool_t *pool
        pjsip_dlg_party local
    struct pjsip_ua_init_param:
        pjsip_dialog *on_dlg_forked(pjsip_dialog *first_set, pjsip_rx_data *res) nogil
    int pjsip_ua_init_module(pjsip_endpoint *endpt, pjsip_ua_init_param *prm) nogil
    pjsip_user_agent *pjsip_ua_instance() nogil
    int pjsip_dlg_create_uac(pjsip_user_agent *ua, pj_str_t *local_uri, pj_str_t *local_contact_uri,
                             pj_str_t *remote_uri, pj_str_t *target, pjsip_dialog **p_dlg) nogil
    int pjsip_dlg_set_route_set(pjsip_dialog *dlg, pjsip_route_hdr *route_set) nogil
    int pjsip_dlg_create_uas(pjsip_user_agent *ua, pjsip_rx_data *rdata, pj_str_t *contact, pjsip_dialog **p_dlg) nogil
    int pjsip_dlg_terminate(pjsip_dialog *dlg) nogil
    int pjsip_dlg_set_transport(pjsip_dialog *dlg, pjsip_tpselector *sel) nogil
    int pjsip_dlg_respond(pjsip_dialog *dlg, pjsip_rx_data *rdata, int st_code,
                          pj_str_t *st_text, pjsip_hdr *hdr_list, pjsip_msg_body *body) nogil
    int pjsip_dlg_create_response(pjsip_dialog *dlg, pjsip_rx_data *rdata,
                                  int st_code, pj_str_t *st_text, pjsip_tx_data **tdata) nogil
    int pjsip_dlg_modify_response(pjsip_dialog *dlg, pjsip_tx_data *tdata, int st_code, pj_str_t *st_text) nogil
    int pjsip_dlg_send_response(pjsip_dialog *dlg, pjsip_transaction *tsx, pjsip_tx_data *tdata) nogil
    void pjsip_dlg_inc_lock(pjsip_dialog *dlg) nogil
    void pjsip_dlg_dec_lock(pjsip_dialog *dlg) nogil

cdef extern from "pjsip-simple/evsub_msg.h":
    struct pjsip_event_hdr:
        pj_str_t event_type
        pj_str_t id_param
        pjsip_param other_param
    struct pjsip_sub_state_hdr:
        pj_str_t sub_state
        pj_str_t reason_param
        int expires_param
        int retry_after
        pjsip_param other_param

cdef extern from "pjsip_simple.h":

    # subscribe / notify
    enum:
        PJSIP_EVSUB_NO_EVENT_ID
    enum pjsip_evsub_state:
        PJSIP_EVSUB_STATE_PENDING
        PJSIP_EVSUB_STATE_ACTIVE
        PJSIP_EVSUB_STATE_TERMINATED
    struct pjsip_evsub
    struct pjsip_evsub_user:
        void on_evsub_state(pjsip_evsub *sub, pjsip_event *event) with gil
        void on_tsx_state(pjsip_evsub *sub, pjsip_transaction *tsx, pjsip_event *event) with gil
        void on_rx_refresh(pjsip_evsub *sub, pjsip_rx_data *rdata, int *p_st_code, pj_str_t **p_st_text,
                           pjsip_hdr *res_hdr, pjsip_msg_body **p_body) with gil
        void on_rx_notify(pjsip_evsub *sub, pjsip_rx_data *rdata, int *p_st_code,
                          pj_str_t **p_st_text,pjsip_hdr *res_hdr, pjsip_msg_body **p_body) with gil
        void on_client_refresh(pjsip_evsub *sub) with gil
        void on_server_timeout(pjsip_evsub *sub) with gil
    int pjsip_evsub_init_module(pjsip_endpoint *endpt) nogil
    int pjsip_evsub_register_pkg(pjsip_module *pkg_mod, pj_str_t *event_name,
                                 unsigned int expires, unsigned int accept_cnt, pj_str_t *accept) nogil
    int pjsip_evsub_create_uac(pjsip_dialog *dlg, pjsip_evsub_user *user_cb,
                               pj_str_t *event, int option, pjsip_evsub **p_evsub) nogil
    int pjsip_evsub_create_uas(pjsip_dialog *dlg, pjsip_evsub_user *user_cb,
                               pjsip_rx_data *rdata, unsigned int option, pjsip_evsub **p_evsub) nogil
    int pjsip_evsub_initiate(pjsip_evsub *sub, void *method, unsigned int expires, pjsip_tx_data **p_tdata) nogil
    int pjsip_evsub_send_request(pjsip_evsub *sub, pjsip_tx_data *tdata) nogil
    int pjsip_evsub_terminate(pjsip_evsub *sub, int notify) nogil
    char *pjsip_evsub_get_state_name(pjsip_evsub *sub) nogil
    void pjsip_evsub_set_mod_data(pjsip_evsub *sub, int mod_id, void *data) nogil
    void *pjsip_evsub_get_mod_data(pjsip_evsub *sub, int mod_id) nogil
    pjsip_hdr *pjsip_evsub_get_allow_events_hdr(pjsip_module *m) nogil
    int pjsip_evsub_notify(pjsip_evsub *sub, pjsip_evsub_state state,
                           pj_str_t *state_str, pj_str_t *reason, pjsip_tx_data **p_tdata) nogil

cdef extern from "pjsip_ua.h":

    # 100rel / PRACK
    int pjsip_100rel_init_module(pjsip_endpoint *endpt) nogil

    # invite sessions
    enum pjsip_inv_option:
        PJSIP_INV_SUPPORT_100REL
        PJSIP_INV_IGNORE_MISSING_ACK
    enum pjsip_inv_state:
        PJSIP_INV_STATE_INCOMING
        PJSIP_INV_STATE_CONFIRMED
    struct pjsip_inv_session:
        pjsip_inv_state state
        void **mod_data
        pjmedia_sdp_neg *neg
        int cause
        pj_str_t cause_text
        int cancelling
        pjsip_transaction *invite_tsx
    struct pjsip_inv_callback:
        void on_state_changed(pjsip_inv_session *inv, pjsip_event *e) with gil
        void on_new_session(pjsip_inv_session *inv, pjsip_event *e) with gil
        void on_tsx_state_changed(pjsip_inv_session *inv, pjsip_transaction *tsx, pjsip_event *e) with gil
        void on_rx_offer(pjsip_inv_session *inv, pjmedia_sdp_session *offer) with gil
        #void on_create_offer(pjsip_inv_session *inv, pjmedia_sdp_session **p_offer)
        void on_media_update(pjsip_inv_session *inv, int status) with gil
        #void on_send_ack(pjsip_inv_session *inv, pjsip_rx_data *rdata)
        void on_rx_reinvite(pjsip_inv_session *inv, pjmedia_sdp_session_ptr_const offer, pjsip_rx_data *rdata) with gil
    int pjsip_inv_usage_init(pjsip_endpoint *endpt, pjsip_inv_callback *cb) nogil
    int pjsip_inv_terminate(pjsip_inv_session *inv, int st_code, int notify) nogil
    int pjsip_inv_end_session(pjsip_inv_session *inv, int st_code, pj_str_t *st_text, pjsip_tx_data **p_tdata) nogil
    int pjsip_inv_cancel_reinvite(pjsip_inv_session *inv, pjsip_tx_data **p_tdata) nogil
    int pjsip_inv_send_msg(pjsip_inv_session *inv, pjsip_tx_data *tdata) nogil
    int pjsip_inv_verify_request(pjsip_rx_data *rdata, unsigned int *options, pjmedia_sdp_session *sdp,
                                 pjsip_dialog *dlg, pjsip_endpoint *endpt, pjsip_tx_data **tdata) nogil
    int pjsip_inv_create_uas(pjsip_dialog *dlg, pjsip_rx_data *rdata, pjmedia_sdp_session *local_sdp,
                             unsigned int options, pjsip_inv_session **p_inv) nogil
    int pjsip_inv_initial_answer(pjsip_inv_session *inv, pjsip_rx_data *rdata, int st_code,
                                 pj_str_t *st_text, pjmedia_sdp_session *sdp, pjsip_tx_data **p_tdata) nogil
    int pjsip_inv_answer(pjsip_inv_session *inv, int st_code, pj_str_t *st_text,
                         pjmedia_sdp_session *local_sdp, pjsip_tx_data **p_tdata) nogil
    int pjsip_inv_create_uac(pjsip_dialog *dlg, pjmedia_sdp_session *local_sdp,
                             unsigned int options, pjsip_inv_session **p_inv) nogil
    int pjsip_inv_invite(pjsip_inv_session *inv, pjsip_tx_data **p_tdata) nogil
    char *pjsip_inv_state_name(pjsip_inv_state state) nogil
    int pjsip_inv_reinvite(pjsip_inv_session *inv, pj_str_t *new_contact,
                           pjmedia_sdp_session *new_offer, pjsip_tx_data **p_tdata) nogil

# declarations

# core.lib

cdef class PJLIB(object)
cdef class PJCachingPool(object)
cdef class PJSIPEndpoint(object)
cdef class PJMEDIAEndpoint(object)

# core.sound

cdef class ConferenceBridge(object)
cdef class ToneGenerator(object)
cdef class RecordingWaveFile(object)
cdef class WaveFile(object)
cdef int cb_play_wav_eof(pjmedia_port *port, void *user_data) with gil

# core.helper

cdef class BaseCredentials(object)
cdef class Credentials(BaseCredentials)
cdef class FrozenCredentials(BaseCredentials)
cdef class BaseSIPURI(object)
cdef class SIPURI(BaseSIPURI)
cdef class FrozenSIPURI(BaseSIPURI)
cdef SIPURI SIPURI_create(pjsip_sip_uri *base_uri)
cdef FrozenSIPURI FrozenSIPURI_create(pjsip_sip_uri *base_uri)

# core.headers

cdef class BaseHeader(object)
cdef class Header(BaseHeader)
cdef class FrozenHeader(BaseHeader)
cdef class BaseContactHeader(object)
cdef class ContactHeader(BaseContactHeader)
cdef class FrozenContactHeader(BaseContactHeader)
cdef class BaseIdentityHeader(object)
cdef class IdentityHeader(BaseIdentityHeader)
cdef class FrozenIdentityHeader(BaseIdentityHeader)
cdef class FromHeader(IdentityHeader)
cdef class FrozenFromHeader(FrozenIdentityHeader)
cdef class ToHeader(IdentityHeader)
cdef class FrozenToHeader(FrozenIdentityHeader)
cdef class RouteHeader(IdentityHeader)
cdef class FrozenRouteHeader(FrozenIdentityHeader)
cdef class RecordRouteHeader(IdentityHeader)
cdef class FrozenRecordRouteHeader(FrozenIdentityHeader)
cdef class BaseRetryAfterHeader(object)
cdef class RetryAfterHeader(BaseRetryAfterHeader)
cdef class FrozenRetryAfterHeader(BaseRetryAfterHeader)
cdef class BaseViaHeader(object)
cdef class ViaHeader(BaseViaHeader)
cdef class FrozenViaHeader(BaseViaHeader)
cdef class BaseWarningHeader(object)
cdef class WarningHeader(BaseWarningHeader)
cdef class FrozenWarningHeader(BaseWarningHeader)
cdef class BaseEventHeader(object)
cdef class EventHeader(BaseEventHeader)
cdef class FrozenEventHeader(BaseEventHeader)
cdef class BaseSubscriptionStateHeader(object)
cdef class SubscriptionStateHeader(BaseSubscriptionStateHeader)
cdef class FrozenSubscriptionStateHeader(BaseSubscriptionStateHeader)

cdef Header Header_create(pjsip_generic_string_hdr *header)
cdef FrozenHeader FrozenHeader_create(pjsip_generic_string_hdr *header)
cdef ContactHeader ContactHeader_create(pjsip_contact_hdr *header)
cdef FrozenContactHeader FrozenContactHeader_create(pjsip_contact_hdr *header)
cdef FromHeader FromHeader_create(pjsip_fromto_hdr *header)
cdef FrozenFromHeader FrozenFromHeader_create(pjsip_fromto_hdr *header)
cdef ToHeader ToHeader_create(pjsip_fromto_hdr *header)
cdef FrozenToHeader FrozenToHeader_create(pjsip_fromto_hdr *header)
cdef RouteHeader RouteHeader_create(pjsip_routing_hdr *header)
cdef FrozenRouteHeader FrozenRouteHeader_create(pjsip_routing_hdr *header)
cdef RecordRouteHeader RecordRouteHeader_create(pjsip_routing_hdr *header)
cdef FrozenRecordRouteHeader FrozenRecordRouteHeader_create(pjsip_routing_hdr *header)
cdef RetryAfterHeader RetryAfterHeader_create(pjsip_retry_after_hdr *header)
cdef FrozenRetryAfterHeader FrozenRetryAfterHeader_create(pjsip_retry_after_hdr *header)
cdef ViaHeader ViaHeader_create(pjsip_via_hdr *header)
cdef FrozenViaHeader FrozenViaHeader_create(pjsip_via_hdr *header)
cdef EventHeader EventHeader_create(pjsip_event_hdr *header)
cdef FrozenEventHeader FrozenEventHeader_create(pjsip_event_hdr *header)
cdef SubscriptionStateHeader SubscriptionStateHeader_create(pjsip_sub_state_hdr *header)
cdef FrozenSubscriptionStateHeader FrozenSubscriptionStateHeader_create(pjsip_sub_state_hdr *header)

# core.util

cdef class frozenlist(object)
cdef class frozendict(object)
cdef class PJSTR(object)
cdef int _str_to_pj_str(object string, pj_str_t *pj_str) except -1
cdef object _pj_str_to_str(pj_str_t pj_str)
cdef object _pj_status_to_str(int status)
cdef object _pj_status_to_def(int status)
cdef dict _pjsip_param_to_dict(pjsip_param *param_list)
cdef int _dict_to_pjsip_param(object params, pjsip_param *param_list, pj_pool_t *pool)
cdef int _pjsip_msg_to_dict(pjsip_msg *msg, dict info_dict) except -1
cdef int _is_valid_ip(int af, object ip) except -1
cdef int _get_ip_version(object ip) except -1
cdef int _add_headers_to_tdata(pjsip_tx_data *tdata, object headers) except -1
cdef int _BaseSIPURI_to_pjsip_sip_uri(BaseSIPURI uri, pjsip_sip_uri *pj_uri, pj_pool_t *pool) except -1
cdef int _BaseRouteHeader_to_pjsip_route_hdr(BaseIdentityHeader header, pjsip_route_hdr *pj_header, pj_pool_t *pool) except -1

# core.ua

cdef class PJSIPThread(object)
cdef class PJSIPUA(object)
cdef class Timer(object)
ctypedef int (*timer_callback)(object, object) except -1 with gil
cdef int _PJSIPUA_cb_rx_request(pjsip_rx_data *rdata) with gil
cdef void _cb_detect_nat_type(void *user_data, pj_stun_nat_detect_result_ptr_const res) with gil
cdef int _cb_trace_rx(pjsip_rx_data *rdata) with gil
cdef int _cb_trace_tx(pjsip_tx_data *tdata) with gil
cdef int _cb_add_user_agent_hdr(pjsip_tx_data *tdata) with gil
cdef int _cb_add_server_hdr(pjsip_tx_data *tdata) with gil
cdef PJSIPUA _get_ua()
cdef int deallocate_weakref(object weak_ref, object timer) except -1 with gil

# core.event

cdef struct _core_event
cdef struct _handler_queue
cdef int _event_queue_append(_core_event *event)
cdef void _cb_log(int level, char_ptr_const data, int len)
cdef int _add_event(object event_name, dict params) except -1
cdef list _get_clear_event_queue()
cdef int _add_handler(int func(object obj) except -1, object obj, _handler_queue *queue) except -1
cdef int _remove_handler(object obj, _handler_queue *queue) except -1
cdef int _process_handler_queue(PJSIPUA ua, _handler_queue *queue) except -1

# core.request

cdef class Request(object)
cdef class IncomingRequest(object)
cdef void _Request_cb_tsx_state(pjsip_transaction *tsx, pjsip_event *event) with gil
cdef void _Request_cb_timer(pj_timer_heap_t *timer_heap, pj_timer_entry *entry) with gil
cdef int _IncomingRequest_dealloc_handler(object obj) except -1

# core.subscription

cdef class Subscription(object)
cdef class IncomingSubscription(object)
cdef void _Subscription_cb_state(pjsip_evsub *sub, pjsip_event *event) with gil
cdef void _Subscription_cb_notify(pjsip_evsub *sub, pjsip_rx_data *rdata, int *p_st_code,
                                    pj_str_t **p_st_text, pjsip_hdr *res_hdr, pjsip_msg_body **p_body) with gil
cdef void _Subscription_cb_refresh(pjsip_evsub *sub) with gil
cdef void _IncomingSubscription_cb_rx_refresh(pjsip_evsub *sub, pjsip_rx_data *rdata,
                                              int *p_st_code, pj_str_t **p_st_text,
                                              pjsip_hdr *res_hdr, pjsip_msg_body **p_body) with gil
cdef void _IncomingSubscription_cb_server_timeout(pjsip_evsub *sub) with gil
cdef void _IncomingSubscription_cb_tsx(pjsip_evsub *sub, pjsip_transaction *tsx, pjsip_event *event) with gil

# core.invitation

cdef class Invitation(object)
cdef void _Invitation_cb_state(pjsip_inv_session *inv, pjsip_event *e) with gil
cdef void _Invitation_cb_sdp_done(pjsip_inv_session *inv, int status) with gil
cdef void _Invitation_cb_rx_reinvite(pjsip_inv_session *inv,
                                     pjmedia_sdp_session_ptr_const offer, pjsip_rx_data *rdata) with gil
cdef void _Invitation_cb_tsx_state_changed(pjsip_inv_session *inv, pjsip_transaction *tsx, pjsip_event *e) with gil
cdef void _Invitation_cb_new(pjsip_inv_session *inv, pjsip_event *e) with gil

# core.sdp

cdef class BaseSDPSession(object)
cdef class SDPSession(BaseSDPSession)
cdef class FrozenSDPSession(BaseSDPSession)
cdef class BaseSDPMediaStream(object)
cdef class SDPMediaStream(BaseSDPMediaStream)
cdef class FrozenSDPMediaStream(BaseSDPMediaStream)
cdef class BaseSDPConnection(object)
cdef class SDPConnection(BaseSDPConnection)
cdef class FrozenSDPConnection(BaseSDPConnection)
cdef class SDPAttributeList(list)
cdef class FrozenSDPAttributeList(frozenlist)
cdef class BaseSDPAttribute(object)
cdef class SDPAttribute(BaseSDPAttribute)
cdef class FrozenSDPAttribute(BaseSDPAttribute)
cdef SDPSession SDPSession_create(pjmedia_sdp_session_ptr_const pj_session)
cdef FrozenSDPSession FrozenSDPSession_create(pjmedia_sdp_session_ptr_const pj_session)
cdef SDPMediaStream SDPMediaStream_create(pjmedia_sdp_media *pj_media)
cdef FrozenSDPMediaStream FrozenSDPMediaStream_create(pjmedia_sdp_media *pj_media)
cdef SDPConnection SDPConnection_create(pjmedia_sdp_conn *pj_conn)
cdef FrozenSDPConnection FrozenSDPConnection_create(pjmedia_sdp_conn *pj_conn)
cdef SDPAttribute SDPAttribute_create(pjmedia_sdp_attr *pj_attr)
cdef FrozenSDPAttribute FrozenSDPAttribute_create(pjmedia_sdp_attr *pj_attr)

# core.mediatransport

cdef class RTPTransport(object)
cdef class AudioTransport(object)
cdef void _RTPTransport_cb_ice_complete(pjmedia_transport *tp, pj_ice_strans_op op, int status) with gil
cdef void _AudioTransport_cb_dtmf(pjmedia_stream *stream, void *user_data, int digit) with gil
cdef dict _pj_math_stat_to_dict(pj_math_stat *stat)
cdef dict _pjmedia_rtcp_stream_stat_to_dict(pjmedia_rtcp_stream_stat *stream_stat)
