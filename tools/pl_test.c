/* Static userspace CSR test for reference root filesystems without Python.
 * Cross-build: arm-linux-gcc -static -O2 -Wall -Wextra tools/pl_test.c -o pl-test
 * Run as root: ./pl-test [iterations]
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static double seconds(struct timespec t) { return t.tv_sec + t.tv_nsec * 1e-9; }

int main(int argc, char **argv)
{
    unsigned long iterations = 10000;
    if (argc > 2) return 2;
    if (argc == 2) {
        char *end;
        errno = 0;
        iterations = strtoul(argv[1], &end, 10);
        if (errno || *end || !iterations || iterations > 10000000) return 2;
    }
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return 1; }
    volatile uint32_t *base = mmap(NULL, 4096, PROT_READ | PROT_WRITE,
                                   MAP_SHARED, fd, 0x40000000);
    close(fd);
    if (base == MAP_FAILED) { perror("mmap"); return 1; }
    volatile uint32_t *scratch = base + 0x800 / 4;
    volatile uint32_t *counter = base + 0x804 / 4;
    if (base[0x808 / 4] != 0x4b534f43) {
        fprintf(stderr, "FAIL signature: %08x\n", base[0x808 / 4]);
        munmap((void *)base, 4096); return 1;
    }
    uint32_t saved = *scratch, random = 0x735a219b;
    int failed = 0;
    for (unsigned long i = 0; i < iterations; i++) {
        random ^= random << 13; random ^= random >> 17; random ^= random << 5;
        uint32_t value = i < 32 ? UINT32_C(1) << i : random;
        if (i == 32) value = 0;
        if (i == 33) value = UINT32_MAX;
        if (i == 34) value = 0xaaaaaaaa;
        if (i == 35) value = 0x55555555;
        *scratch = value;
        __sync_synchronize();
        uint32_t actual = *scratch;
        if (actual != value) {
            fprintf(stderr, "FAIL iteration %lu: wrote %08x read %08x\n", i, value, actual);
            failed = 1; break;
        }
    }
    *scratch = saved;
    __sync_synchronize();
    if (*scratch != saved) { fprintf(stderr, "FAIL restoring scratch\n"); failed = 1; }
    struct timespec start, finish, delay = {0, 100000000};
    clock_gettime(CLOCK_MONOTONIC, &start);
    uint32_t first = *counter;
    while (nanosleep(&delay, &delay) && errno == EINTR) {}
    uint32_t last = *counter;
    clock_gettime(CLOCK_MONOTONIC, &finish);
    double frequency = (uint32_t)(last - first) / (seconds(finish) - seconds(start));
    if (frequency < 95000000 || frequency > 105000000) {
        fprintf(stderr, "FAIL counter frequency %.0f Hz\n", frequency); failed = 1;
    }
    if (!failed) printf("PASS signature, %lu CSR transactions, scratch restored, counter %.0f Hz\n",
                        iterations, frequency);
    munmap((void *)base, 4096);
    return failed;
}
