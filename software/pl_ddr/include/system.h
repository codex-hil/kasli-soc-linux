/* SPDX-License-Identifier: BSD-2-Clause — Linux userspace adaptation. */
#ifndef PL_DDR_SYSTEM_H
#define PL_DDR_SYSTEM_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
extern volatile uint8_t *pl_csr;
extern volatile uint32_t *pl_ram;
#define MAIN_RAM_BASE 0x80000000L
#define MAIN_RAM_SIZE 0x40000000L
#define MAIN_RAM_BASE_VA ((uintptr_t)pl_ram)
#define CSR_ACCESSORS_DEFINED
static inline void csr_write_simple(unsigned long v, unsigned long a) {
    __asm__ volatile("dmb sy" ::: "memory");
    *(volatile uint32_t *)(pl_csr + a - 0x40000000UL) = v;
    __asm__ volatile("dmb sy" ::: "memory");
}
static inline unsigned long csr_read_simple(unsigned long a) {
    __asm__ volatile("dmb sy" ::: "memory");
    unsigned long v = *(volatile uint32_t *)(pl_csr + a - 0x40000000UL);
    __asm__ volatile("dmb sy" ::: "memory");
    return v;
}
/* O_SYNC /dev/mem mappings are uncached; barriers remain necessary. */
static inline void flush_cpu_dcache_range(void *p, unsigned long n) { __sync_synchronize(); }
static inline void flush_l2_cache(void) { __sync_synchronize(); }
void cdelay(int cycles);
void timer0_en_write(unsigned int value);
void timer0_reload_write(unsigned int value);
void timer0_load_write(unsigned int value);
void timer0_update_value_write(unsigned int value);
uint32_t timer0_value_read(void);
#endif
