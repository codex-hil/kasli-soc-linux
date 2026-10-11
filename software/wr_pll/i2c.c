/* SPDX-License-Identifier: GPL-2.0-or-later
 * Bounded open-drain transactions; register offsets supplied by matched CSR map.
 */
#include <stdint.h>
#include <time.h>
#include <errno.h>
struct bus { volatile uint32_t *w, *r, *counter; };
static uint64_t now(void) {
 struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
 return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;
}
static int lines(struct bus *b, int scl, int sda) {
 *b->w=scl|((!sda)<<1)|(sda<<2);
 if(scl && !(*b->r&2)) { uint64_t end=now()+100000000;
  while(!(*b->r&2)) if(now()>end) return ETIMEDOUT;
 }
 if(b->counter) {
  /* 150 ticks: 1.5 us at 100 MHz, 1.8 us at 83 1/3 MHz.
   * Caller enables this only for those clocks. Unsigned subtraction handles wrap. */
  uint32_t start=*b->counter;
  unsigned polls=0;uint64_t deadline=0;
  while((uint32_t)(*b->counter-start)<150) {
   if(++polls>=1024) {
    if(!deadline) deadline=now()+100000000;
    else if(now()>deadline) return ETIMEDOUT;
   }
  }
 } else { uint64_t end=now()+1500; while(now()<end) {} }
 return 0;
}
#define TRY(x) do { int e=(x); if(e) return e; } while(0)
static int start(struct bus*b) { TRY(lines(b,1,1));TRY(lines(b,1,0));return lines(b,0,0); }
static int stop(struct bus*b) {
 /* Release SDA and SCL even when stretch/timer failure prevents a clean STOP. */
 int first=lines(b,0,0);int second=lines(b,1,0);int last=lines(b,1,1);
 return first?first:second?second:last;
}
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
 struct bus b={(volatile uint32_t*)((uint8_t*)base+wo),(volatile uint32_t*)((uint8_t*)base+ro),0};
 int e=transaction(&b,read,reg,data,n);int finish=stop(&b);return e?e:finish;
}
int wr_i2c_timed(void *base,unsigned wo,unsigned ro,unsigned co,int read,uint8_t reg,uint8_t*data,unsigned n) {
 if((wo|ro|co)&3 || wo>=65536 || ro>=65536 || co>=65536 || !n || n>16) return EINVAL;
 struct bus b={(volatile uint32_t*)((uint8_t*)base+wo),(volatile uint32_t*)((uint8_t*)base+ro),
  (volatile uint32_t*)((uint8_t*)base+co)};
 int e=transaction(&b,read,reg,data,n);int finish=stop(&b);return e?e:finish;
}
