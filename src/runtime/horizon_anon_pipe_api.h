/* LGPL-2.1-or-later. Native synchronous anonymous-pipe API. */
#ifndef HORIZON_ANON_PIPE_API_H
#define HORIZON_ANON_PIPE_API_H
struct horizon_anon_pipe_info {
    unsigned access,options,capacity,available,writer,connected,read_open,write_open;
};
int horizon_anon_pipe_io(unsigned handle,int writer,void *data,unsigned size,
                         unsigned *status,unsigned *done,unsigned *options);
int horizon_anon_pipe_info(unsigned handle,struct horizon_anon_pipe_info *out);
int horizon_anon_pipe_peek(unsigned handle,void *data,unsigned size,
                           unsigned *status,unsigned *done);
#endif
