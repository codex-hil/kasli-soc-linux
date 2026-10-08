// SPDX-License-Identifier: BSD-2-Clause
// Upstream LiteX JEDEC initialization/leveling + uncached Linux diagnostics.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <generated/csr.h>
#include <generated/soc.h>
#include <liblitedram/sdram.h>
#include <libbase/memtest.h>

volatile uint8_t *pl_csr;
volatile uint32_t *pl_ram;
static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}
void cdelay(int cycles) {
    /* BIOS delays are PL clock cycles, not Cortex-A9 instruction cycles. */
    uint64_t end = now_ns() + (uint64_t)cycles * 10;
    while (now_ns() < end) __asm__ volatile("nop");
}
static uint32_t timer_sample;
void timer0_en_write(unsigned int v) { (void)v; }
void timer0_reload_write(unsigned int v) { (void)v; }
void timer0_load_write(unsigned int v) { (void)v; }
void timer0_update_value_write(unsigned int v) { timer_sample = 0xffffffffU-(uint32_t)(now_ns()/10); }
uint32_t timer0_value_read(void) { return timer_sample; }
static void *map(int fd, size_t bytes, off_t offset) {
    void *p=mmap(NULL, bytes, PROT_READ|PROT_WRITE, MAP_SHARED, fd, offset);
    if (p==MAP_FAILED) { perror("mmap"); exit(1); }
    return p;
}
static int bist(uint32_t base, unsigned random) {
    uint32_t bytes=0x20000000, end=base+bytes;
    /* BIST address fields are modulo physical capacity: top end wraps to 0. */
    sdram_generator_reset_write(1); sdram_checker_reset_write(1);
    sdram_generator_base_write(base); sdram_generator_end_write(end);
    sdram_generator_length_write(bytes); sdram_generator_random_write(random);
    sdram_checker_base_write(base); sdram_checker_end_write(end);
    sdram_checker_length_write(bytes); sdram_checker_random_write(random);
    sdram_generator_start_write(1);
    uint64_t limit=now_ns()+30000000000ULL;
    while (!sdram_generator_done_read()) {
        if(now_ns()>limit) { fprintf(stderr,"BIST generator timeout\n"); return 0; }
        usleep(1000);
    }
    sdram_checker_start_write(1);
    limit=now_ns()+30000000000ULL;
    while (!sdram_checker_done_read()) {
        if(now_ns()>limit) { fprintf(stderr,"BIST checker timeout\n"); return 0; }
        usleep(1000);
    }
    unsigned errors=sdram_checker_errors_read();
    printf("BIST base=%08x bytes=%u random=%u write_ticks=%u read_ticks=%u errors=%u\n",
        base,bytes,random,sdram_generator_ticks_read(),sdram_checker_ticks_read(),errors);
    return errors==0;
}
static int address_test(int fd) {
    volatile uint32_t *locations[30]; void *pages[30]; uint32_t expected[30]; int n=0;
    /* Include zero: a stuck address line maps its walking-one address here. */
    pages[n]=map(fd,4096,0x80000000ULL);
    locations[n]=(volatile uint32_t *)pages[n];
    expected[n]=0x136ac59fU; *locations[n]=expected[n]; n++;
    for(int bit=2;bit<30;bit++) {
        uint32_t offset=1U<<bit;
        pages[n]=map(fd,4096,0x80000000ULL+(offset&~4095U));
        locations[n]=(volatile uint32_t *)((uint8_t *)pages[n]+(offset&4095));
        expected[n]=0x136ac59fU^offset;
        *locations[n]=expected[n]; n++;
    }
    pages[n]=map(fd,4096,0xbffff000ULL);
    locations[n]=(volatile uint32_t *)((uint8_t *)pages[n]+4092);
    expected[n]=0xbaadf00d; *locations[n]=expected[n]; n++;
    __sync_synchronize();
    int ok=1;
    for(int i=0;i<n;i++) {
        uint32_t got=*locations[i];
        if(got!=expected[i]) { fprintf(stderr,"Address alias: %08x != %08x\n",got,expected[i]); ok=0; }
        munmap(pages[i],4096);
    }
    printf("GP1 address test: %d locations across 1 GiB: %s\n",n,ok?"PASS":"FAIL");
    return ok;
}
int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    int fd=open("/dev/mem",O_RDWR|O_SYNC);
    if(fd<0) { perror("/dev/mem"); return 1; }
    pl_csr=map(fd,65536,0x40000000);
    if(ddr_status_signature_read()!=0x504c4444 || probe_signature_read()!=0x4b534f43) {
        fprintf(stderr,"Wrong PL DDR bitstream signature\n"); return 1;
    }
    uint64_t timeout=now_ns()+2000000000ULL;
    while(ddr_status_ready_read()!=3) {
        if(now_ns()>timeout) { fprintf(stderr,"MMCM/IDELAYCTRL not ready\n"); return 1; }
        usleep(1000);
    }
    pl_ram=map(fd,16*1024*1024,0x80000000);
    if(!sdram_init()) { fprintf(stderr,"FAIL: upstream SDRAM initialization/memtest\n"); return 1; }
    if(!address_test(fd)) return 1;
    for(unsigned pass=0;pass<3;pass++)
        for(unsigned half=0;half<2;half++)
            if(!bist(half*0x20000000U,pass==0?0:1)) return 1;
    munmap((void *)pl_ram,16*1024*1024); munmap((void *)pl_csr,65536); close(fd);
    puts("PASS: PL SODIMM init/leveling, GP1 smoke/address test, 3 whole-1-GiB BIST passes");
    return 0;
}
