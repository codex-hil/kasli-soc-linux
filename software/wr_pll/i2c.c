/* SPDX-License-Identifier: GPL-2.0-or-later
 * Bounded open-drain transactions; register offsets supplied by matched CSR map.
 */
#include <stdint.h>
#include <time.h>
#include <errno.h>
struct bus { volatile uint32_t *w, *r; };
static uint64_t now(void) {
 struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
 return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;
}
static int lines(struct bus *b, int scl, int sda) {
 *b->w=scl|((!sda)<<1)|(sda<<2);
 if(scl) { uint64_t end=now()+100000000;
  while(!(*b->r&2)) if(now()>end) return ETIMEDOUT;
 }
 uint64_t end=now()+1500; while(now()<end) {}
 return 0;
}
#define TRY(x) do { int e=(x); if(e) return e; } while(0)
static int start(struct bus*b) { TRY(lines(b,1,1));TRY(lines(b,1,0));return lines(b,0,0); }
static int stop(struct bus*b) { TRY(lines(b,0,0));TRY(lines(b,1,0));return lines(b,1,1); }
static int send(struct bus*b,uint8_t v) {
 for(int i=7;i>=0;i--) { int d=(v>>i)&1;TRY(lines(b,0,d));TRY(lines(b,1,d));TRY(lines(b,0,d)); }
 TRY(lines(b,0,1));TRY(lines(b,1,1));int ack=!(*b->r&1);TRY(lines(b,0,1));return ack?0:ENXIO;
}
static int recv(struct bus*b,uint8_t*v,int last) {
 *v=0;for(int i=0;i<8;i++) {TRY(lines(b,0,1));TRY(lines(b,1,1));*v=(*v<<1)|(*b->r&1);TRY(lines(b,0,1));}
 TRY(lines(b,0,last));TRY(lines(b,1,last));return lines(b,0,last);
}
static int transaction(struct bus*b,int read,uint8_t reg,uint8_t*data,unsigned n) {
 TRY(start(b));TRY(send(b,0xaa));TRY(send(b,reg));
 if(read) { TRY(start(b));TRY(send(b,0xab));for(unsigned i=0;i<n;i++) TRY(recv(b,&data[i],i+1==n)); }
 else for(unsigned i=0;i<n;i++) TRY(send(b,data[i]));
 return 0;
}
int wr_i2c(void *base,unsigned wo,unsigned ro,int read,uint8_t reg,uint8_t*data,unsigned n) {
 if((wo|ro)&3 || wo>=65536 || ro>=65536 || !n || n>16) return EINVAL;
 struct bus b={(volatile uint32_t*)((uint8_t*)base+wo),(volatile uint32_t*)((uint8_t*)base+ro)};
 int e=transaction(&b,read,reg,data,n);int finish=stop(&b);return e?e:finish;
}
