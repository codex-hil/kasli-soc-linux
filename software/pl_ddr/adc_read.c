// SPDX-License-Identifier: BSD-2-Clause
// Read a completed ADC buffer through uncached GP1 and verify every 64-bit tick.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc < 5 || argc > 6) {
        fprintf(stderr,"Usage: %s card base_byte_offset samples seq|14bit_pattern [output.bin]\n",argv[0]); return 2;
    }
    unsigned card=strtoul(argv[1],NULL,0);
    uint64_t base=strtoull(argv[2],NULL,0), count=strtoull(argv[3],NULL,0);
    int sequence=!strcmp(argv[4],"seq");
    unsigned pattern=sequence?0:strtoul(argv[4],NULL,0);
    if (card<1 || card>2 || !count || count>0x7ffffff || (base&63) ||
        base+count*8>0x40000000 || pattern>16383) return 2;
    int fd=open("/dev/mem",O_RDONLY|O_SYNC);
    if (fd<0) { perror("/dev/mem"); return 1; }
    uint64_t aligned=base&~4095ULL, displacement=base-aligned;
    size_t size=(size_t)(displacement+count*8);
    void *mapping=mmap(NULL,size,PROT_READ,MAP_SHARED,fd,0x80000000ULL+aligned);
    if(mapping==MAP_FAILED) { perror("mmap"); close(fd); return 1; }
    volatile uint32_t *words=(volatile uint32_t *)((uint8_t *)mapping+displacement);
    FILE *output=argc==6?fopen(argv[5],"wb"):NULL;
    if(argc==6 && !output) { perror("output"); return 1; }
    uint64_t errors=0;
    uint32_t block[2048];size_t used=0;
    for(uint32_t i=0;i<count;i++) {
        uint32_t lo=words[2*i], hi=words[2*i+1];
        uint32_t expected_lo=sequence?i:((pattern<<2)|((pattern<<2)<<16));
        uint32_t expected_hi=sequence?(i^(0xadc00000U+card)):expected_lo;
        if(lo!=expected_lo || hi!=expected_hi) {
            if(errors<8) fprintf(stderr,"card=%u sample=%u got=%08x:%08x expected=%08x:%08x\n",
                card,i,hi,lo,expected_hi,expected_lo);
            errors++;
        }
        if(output) {
            block[used++]=lo;block[used++]=hi;
            if(used==2048 || i+1==count) {
                if(fwrite(block,sizeof(uint32_t),used,output)!=used) { perror("write"); return 1; }
                used=0;
            }
        }
    }
    int failed=output && fclose(output);
    munmap(mapping,size);close(fd);
    printf("card=%u samples=%"PRIu64" bytes=%"PRIu64" errors=%"PRIu64" result=%s\n",
        card,count,count*8,errors,errors||failed?"FAIL":"PASS");
    return errors||failed?1:0;
}
