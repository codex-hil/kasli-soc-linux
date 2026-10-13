/* Included only in a build-local liblitedram diagnostic copy. */
extern int sdram_lab_timed_out(void);
int sdram_lab_dqs_sweep(void) {
    unsigned tested = 0, best_errors = ~0U;
    int result = 0;
    sdram_software_control_on();
    sdram_leveling_action(4, 0, write_rst_dqs_delay);
    for (unsigned dqs = 0; dqs < 32; dqs++) {
        sdram_leveling_action(4, 0, read_rst_dq_bitslip);
        for (unsigned slip = 0; slip < 8; slip++) {
            sdram_leveling_action(4, 0, read_rst_dq_delay);
            for (unsigned delay = 0; delay < 32; delay++) {
                if (sdram_lab_timed_out()) { result = -1; goto done; }
                unsigned errors = run_test_pattern_seeds(4, 0, 1);
                tested++;
                if (errors < best_errors) best_errors = errors;
                if (!errors && !run_test_pattern(4, 0)) {
                    printf("DQS_SWEEP candidate dqs_offset=%u read_slip_offset=%u read_delay=%u seeds=3 tested=%u\n",
                        dqs, slip, delay, tested);
                    result = 1;
                    goto done;
                }
                sdram_leveling_action(4, 0, read_inc_dq_delay);
            }
            sdram_leveling_action(4, 0, read_inc_dq_bitslip);
        }
        printf("DQS_SWEEP progress dqs_offset=%u tested=%u best_errors=%u\n",dqs,tested,best_errors);
        sdram_leveling_action(4, 0, write_inc_dqs_delay);
    }
done:
    sdram_software_control_off();
    printf("DQS_SWEEP result=%d tested=%u best_errors=%u (diagnostic only; does not qualify DDR)\n",
        result,tested,best_errors);
    return result;
}
